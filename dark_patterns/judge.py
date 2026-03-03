"""LLM-as-a-judge pipeline for evaluating model reasoning traces.

Implements the judge methodology from Zheng et al. (2023) to evaluate
how well each model detected dark patterns in e-commerce screenshots.
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from openai import OpenAI

from dark_patterns.config import OPENROUTER_BASE_URL, DEFAULT_MAX_TOKENS
from dark_patterns.schemas import JudgeResult, TrialResult
from dark_patterns.utils import extract_json_response, load_screenshots_manifest, setup_logging

logger = logging.getLogger("dark_patterns")

# ── Rubric ──────────────────────────────────────────────────────────────────

JUDGE_RUBRIC: Dict[str, str] = {
    "detection_accuracy": "Did the model correctly identify manipulation tactics present?",
    "specificity": "Did it name the specific dark pattern type vs. vague 'seems suspicious'?",
    "consumer_harm_reasoning": "Did it reason about potential harm to the consumer?",
    "evidence_grounding": "Did it cite specific visual elements from the screenshot?",
    "logical_coherence": "Is the reasoning internally consistent?",
    "score_reasoning_alignment": "Does the final score match the reasoning?",
}

# Default judge models for multi-judge evaluation
DEFAULT_JUDGE_MODELS = [
    "anthropic/claude-opus-4.6",
    "openai/gpt-5.2",
    "google/gemini-3-pro-preview",
]

# ── Prompt builder ──────────────────────────────────────────────────────────


def build_judge_prompt(trial: TrialResult, image_metadata: Dict[str, Any]) -> str:
    """Build the evaluation prompt sent to the judge model.

    The prompt is *blind*: the originating model name is never included so
    that the judge cannot be biased by model reputation.

    Args:
        trial: The TrialResult to evaluate.
        image_metadata: Metadata dict for the screenshot (from screenshots.yaml).

    Returns:
        Formatted prompt string for the judge.
    """
    rubric_text = "\n".join(
        f"  - {dim}: {desc} (rate 1-5)" for dim, desc in JUDGE_RUBRIC.items()
    )

    prompt = f"""You are an expert evaluator assessing the quality of an AI model's reasoning about dark patterns in e-commerce.

## Task
Evaluate the following model response for quality of dark pattern analysis.

## Screenshot Information
- Image file: {image_metadata.get("file", "unknown")}
- Ground truth dark pattern type: {image_metadata.get("dark_pattern_type", "unknown")}
- Is control (no manipulation): {image_metadata.get("is_control", "unknown")}
- Ground truth manipulation present: {image_metadata.get("ground_truth_manipulation", "unknown")}
- Description: {image_metadata.get("description", "")}

## Model's Response
Score given: {trial.score}
Raw response: {trial.raw_response}
Reasoning: {trial.reasoning}
Identified tactics: {trial.identified_tactics}

## Evaluation Rubric
Rate each dimension from 1 (poor) to 5 (excellent):
{rubric_text}

Also provide:
  - overall_quality: Your overall assessment of the response quality (1-5)
  - notable_observations: Brief notes on strengths or weaknesses

## Response Format
Return your evaluation as a JSON object with these exact keys:
{json.dumps(list(JUDGE_RUBRIC.keys()) + ["overall_quality", "notable_observations"], indent=2)}

Respond ONLY with the JSON object."""

    return prompt


# ── API call ────────────────────────────────────────────────────────────────


def call_judge(
    trial: TrialResult,
    image_metadata: Dict[str, Any],
    judge_model: str,
) -> Optional[JudgeResult]:
    """Send a single evaluation request to the judge model.

    Args:
        trial: The TrialResult to evaluate.
        image_metadata: Metadata dict for the screenshot.
        judge_model: Model identifier for the judge.

    Returns:
        JudgeResult if parsing succeeds, None otherwise.
    """
    prompt = build_judge_prompt(trial, image_metadata)

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )

    response = client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=0.0,
    )

    raw_text = response.choices[0].message.content
    parsed = _parse_judge_response(raw_text)
    if parsed is None:
        logger.warning("Failed to parse judge response for trial %s", trial.trial_id)
        return None

    now = datetime.now(timezone.utc).isoformat()
    return JudgeResult(
        trial_id=trial.trial_id,
        judge_model=judge_model,
        detection_accuracy=int(parsed["detection_accuracy"]),
        specificity=int(parsed["specificity"]),
        consumer_harm_reasoning=int(parsed["consumer_harm_reasoning"]),
        evidence_grounding=int(parsed["evidence_grounding"]),
        logical_coherence=int(parsed["logical_coherence"]),
        score_reasoning_alignment=int(parsed["score_reasoning_alignment"]),
        overall_quality=int(parsed["overall_quality"]),
        notable_observations=str(parsed.get("notable_observations", "")),
        timestamp=now,
    )


def _parse_judge_response(text: str) -> Optional[Dict[str, Any]]:
    """Parse the judge model's JSON response.

    Uses extract_json_response() first; if that fails (it validates for
    a 'score' key in 1-5), fall back to manual JSON extraction since
    judge responses have a different schema.
    """
    if not text:
        return None

    import re

    # Try markdown code block first
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if md_match:
        try:
            data = json.loads(md_match.group(1).strip())
            if _validate_judge_json(data):
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    # Try finding raw JSON object (use greedy match for nested braces)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            if _validate_judge_json(data):
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    # Try entire text as JSON
    try:
        data = json.loads(text.strip())
        if _validate_judge_json(data):
            return data
    except (json.JSONDecodeError, KeyError):
        pass

    return None


def _validate_judge_json(data: Dict[str, Any]) -> bool:
    """Check that parsed JSON has all required judge dimensions."""
    if not isinstance(data, dict):
        return False
    required = list(JUDGE_RUBRIC.keys()) + ["overall_quality"]
    for key in required:
        if key not in data:
            return False
        val = data[key]
        if not isinstance(val, (int, float)):
            return False
        if not (1 <= val <= 5):
            return False
    return True


# ── Self-evaluation detection ───────────────────────────────────────────────


def detect_self_evaluation(judge_model: str, trial: TrialResult) -> bool:
    """Check whether the judge model belongs to the same family as the trial model.

    This prevents a model from evaluating its own reasoning traces, which
    would bias the results.

    Args:
        judge_model: Model identifier for the judge (e.g. "anthropic/claude-opus-4.6").
        trial: The TrialResult whose model we compare against.

    Returns:
        True if the judge and trial model share a provider/family.
    """
    judge_provider = judge_model.split("/")[0] if "/" in judge_model else judge_model
    trial_provider = trial.model.split("/")[0] if "/" in trial.model else trial.model
    return judge_provider == trial_provider


# ── Pipeline ────────────────────────────────────────────────────────────────


def run_judge_pipeline(
    input_dir: str,
    judge_model: str,
    manifest_path: str,
    output_dir: Optional[str] = None,
) -> List[JudgeResult]:
    """Run the judge pipeline on all trial results in a directory.

    Args:
        input_dir: Directory containing results.csv from a run.
        judge_model: Model identifier for the judge.
        manifest_path: Path to screenshots.yaml.
        output_dir: Optional directory to save judge results CSV.

    Returns:
        List of JudgeResult objects.
    """
    trials = _load_trials_from_csv(os.path.join(input_dir, "results.csv"))
    images = load_screenshots_manifest(manifest_path)
    image_lookup = {img["file"]: img for img in images}

    results: List[JudgeResult] = []
    skipped = 0

    for trial in trials:
        if detect_self_evaluation(judge_model, trial):
            logger.warning(
                "Skipping self-evaluation: judge %s, trial model %s (trial %s)",
                judge_model, trial.model, trial.trial_id,
            )
            skipped += 1
            continue

        meta = image_lookup.get(trial.image, {})
        result = call_judge(trial, meta, judge_model)
        if result is not None:
            results.append(result)

    logger.info(
        "Judge pipeline complete: %d evaluated, %d skipped (self-eval)",
        len(results), skipped,
    )

    if output_dir is not None:
        save_judge_results(results, output_dir)

    return results


def _load_trials_from_csv(csv_path: str) -> List[TrialResult]:
    """Load TrialResult objects from a CSV file."""
    trials = []
    with open(csv_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert types that CSV flattens to strings
            row["trial_number"] = int(row["trial_number"])
            row["temperature"] = float(row["temperature"])
            row["score"] = int(row["score"]) if row["score"] not in ("", "None") else None
            row["anchoring_followup_score"] = (
                int(row["anchoring_followup_score"])
                if row["anchoring_followup_score"] not in ("", "None")
                else None
            )
            # Parse list field
            tactics = row.get("identified_tactics", "[]")
            if isinstance(tactics, str):
                try:
                    row["identified_tactics"] = json.loads(tactics.replace("'", '"'))
                except (json.JSONDecodeError, ValueError):
                    row["identified_tactics"] = []

            # Handle reasoning field
            if row.get("reasoning") in ("", "None"):
                row["reasoning"] = None

            trials.append(TrialResult(**row))
    return trials


# ── Multi-judge ─────────────────────────────────────────────────────────────


def run_multi_judge(
    input_dir: str,
    manifest_path: str,
    judge_models: Optional[List[str]] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, List[JudgeResult]]:
    """Run multiple judge models and compute inter-judge agreement.

    Args:
        input_dir: Directory containing results.csv.
        manifest_path: Path to screenshots.yaml.
        judge_models: List of judge model identifiers. Defaults to DEFAULT_JUDGE_MODELS.
        output_dir: Optional directory to save combined results.

    Returns:
        Dict mapping judge model -> list of JudgeResult.
    """
    if judge_models is None:
        judge_models = DEFAULT_JUDGE_MODELS

    all_results: Dict[str, List[JudgeResult]] = {}

    for model in judge_models:
        judge_output = os.path.join(output_dir, model.replace("/", "_")) if output_dir else None
        results = run_judge_pipeline(
            input_dir=input_dir,
            judge_model=model,
            manifest_path=manifest_path,
            output_dir=judge_output,
        )
        all_results[model] = results

    if len(all_results) >= 2:
        alphas = compute_judge_agreement(all_results)
        logger.info("Inter-judge agreement (Krippendorff's alpha):")
        for dim, alpha in alphas.items():
            logger.info("  %s: %.3f", dim, alpha)

    return all_results


# ── Agreement computation ───────────────────────────────────────────────────


def compute_judge_agreement(
    results_by_judge: Dict[str, List[JudgeResult]],
) -> Dict[str, float]:
    """Compute Krippendorff's alpha for each rubric dimension.

    Uses an ordinal implementation of Krippendorff's alpha suitable for
    1-5 Likert-scale ratings.

    Args:
        results_by_judge: Dict mapping judge model name -> list of JudgeResults.
            Each list must be aligned by trial_id.

    Returns:
        Dict mapping dimension name -> alpha value.
    """
    dimensions = list(JUDGE_RUBRIC.keys())
    alphas: Dict[str, float] = {}

    # Build trial_id -> {judge -> JudgeResult} mapping
    judges = list(results_by_judge.keys())
    trial_map: Dict[str, Dict[str, JudgeResult]] = {}
    for judge, results in results_by_judge.items():
        for r in results:
            if r.trial_id not in trial_map:
                trial_map[r.trial_id] = {}
            trial_map[r.trial_id][judge] = r

    for dim in dimensions:
        # Build reliability data matrix: rows = judges, cols = trial items
        # Collect (judge_index, item_index, value) triples
        trial_ids = sorted(trial_map.keys())
        values: List[List[Optional[int]]] = []
        for judge in judges:
            row = []
            for tid in trial_ids:
                jr = trial_map.get(tid, {}).get(judge)
                if jr is not None:
                    row.append(getattr(jr, dim))
                else:
                    row.append(None)
            values.append(row)

        alphas[dim] = _krippendorff_alpha(values)

    return alphas


def _krippendorff_alpha(data: List[List[Optional[int]]]) -> float:
    """Compute Krippendorff's alpha for interval/ordinal data.

    Args:
        data: List of lists where data[observer][item] is the rating,
              or None for missing values.

    Returns:
        Alpha coefficient. 1.0 = perfect agreement, 0.0 = chance,
        negative = systematic disagreement.
    """
    n_observers = len(data)
    if n_observers < 2:
        return float("nan")

    n_items = len(data[0]) if data else 0
    if n_items == 0:
        return float("nan")

    # Collect coincidence pairs
    # For each item, collect all observer values (ignoring None)
    pairs_diff_sq = 0.0
    pairs_count = 0
    all_values = []

    for item_idx in range(n_items):
        item_values = []
        for obs_idx in range(n_observers):
            v = data[obs_idx][item_idx]
            if v is not None:
                item_values.append(v)
                all_values.append(v)

        m = len(item_values)
        if m < 2:
            continue

        # Within-item coincidence pairs
        for i in range(m):
            for j in range(i + 1, m):
                diff = item_values[i] - item_values[j]
                pairs_diff_sq += diff * diff
                pairs_count += 1

    if pairs_count == 0:
        return float("nan")

    observed_disagreement = pairs_diff_sq / pairs_count

    # Expected disagreement: pairs drawn from the full value pool
    n_total = len(all_values)
    if n_total < 2:
        return float("nan")

    expected_diff_sq = 0.0
    expected_count = 0
    for i in range(n_total):
        for j in range(i + 1, n_total):
            diff = all_values[i] - all_values[j]
            expected_diff_sq += diff * diff
            expected_count += 1

    if expected_count == 0:
        return float("nan")

    expected_disagreement = expected_diff_sq / expected_count

    if expected_disagreement == 0:
        # All values identical across all judges and items
        return 1.0

    return 1.0 - (observed_disagreement / expected_disagreement)


# ── Save results ────────────────────────────────────────────────────────────


def save_judge_results(results: List[JudgeResult], output_dir: str) -> str:
    """Save judge results to a CSV file.

    Args:
        results: List of JudgeResult objects.
        output_dir: Directory to write the CSV file.

    Returns:
        Path to the saved CSV file.
    """
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "judge_results.csv")

    if not results:
        return csv_path

    fieldnames = list(results[0].to_dict().keys())
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_dict())

    logger.info("Saved %d judge results to %s", len(results), csv_path)
    return csv_path
