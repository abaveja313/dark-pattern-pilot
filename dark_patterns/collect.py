"""Data collection module for the Dark Patterns research study.

Handles trial planning, API calls to models via OpenRouter, and
incremental result persistence.
"""

import json
import os
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import pandas as pd
from openai import OpenAI
from tqdm import tqdm

from dark_patterns.config import (
    CONDITIONS,
    OPENROUTER_BASE_URL,
    REASONING_MODELS,
    get_anchoring_followup,
    get_condition_prompt,
    get_cot_instruction,
    get_detect_prompt,
)
from dark_patterns.schemas import RunManifest, TrialResult
from dark_patterns.utils import encode_image, extract_json_response, extract_score, get_mime_type


def generate_trial_plan(
    models: List[str],
    images: List[str],
    conditions: List[str],
    trials: int,
    task_mode: str,
    cot_mode: str,
    enable_anchoring: bool,
    enable_counterbalancing: bool,
) -> List[Dict[str, Any]]:
    """Generate the full list of trial configurations.

    Each (model, image, condition, trial_number) combo gets a trial.
    task_mode='dual' adds score_first + detect_then_score variants.
    cot_mode='both' adds on + off variants.
    enable_counterbalancing splits trials across Product A and B.
    """
    # Determine task variants
    if task_mode == "dual":
        task_variants = ["score_first", "detect_then_score"]
    else:
        task_variants = ["score_first"]

    # Determine CoT variants
    if cot_mode == "both":
        cot_variants = ["on", "off"]
    else:
        cot_variants = [cot_mode]

    plan = []
    trial_counter = 0

    for model in models:
        for image in images:
            for condition in conditions:
                for trial_num in range(1, trials + 1):
                    for task_variant in task_variants:
                        for cot_var in cot_variants:
                            # Determine target product
                            if enable_counterbalancing:
                                target = "A" if trial_counter % 2 == 0 else "B"
                            else:
                                target = "B"

                            trial_id = (
                                f"{model}_{image}_{condition}_"
                                f"t{trial_num}_{task_variant}_{cot_var}"
                            )

                            plan.append({
                                "trial_id": trial_id,
                                "model": model,
                                "image": image,
                                "condition": condition,
                                "trial_number": trial_num,
                                "task_variant": task_variant,
                                "cot_mode": cot_var,
                                "target_product": target,
                            })
                            trial_counter += 1

    return plan


def create_run_manifest(
    base_dir: str,
    models: List[str],
    conditions: List[str],
    images: List[str],
    trials: int,
    temperature: float,
    task_mode: str,
    cot_mode: str,
    enable_anchoring: bool,
    enable_counterbalancing: bool,
    total_api_calls: int,
) -> RunManifest:
    """Create a RunManifest and save it to runs/YYYYMMDD_HHMMSS/manifest.json."""
    # Get git SHA
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        git_sha = "unknown"

    now = datetime.now()
    run_id = now.strftime("%Y%m%d_%H%M%S")
    timestamp = now.isoformat()

    manifest = RunManifest(
        run_id=run_id,
        git_sha=git_sha,
        models=models,
        conditions=conditions,
        images=images,
        trials=trials,
        temperature=temperature,
        task_mode=task_mode,
        cot_mode=cot_mode,
        enable_anchoring=enable_anchoring,
        enable_counterbalancing=enable_counterbalancing,
        total_api_calls=total_api_calls,
        timestamp=timestamp,
    )

    # Create run directory and save manifest
    run_dir = os.path.join(base_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2)

    return manifest


def call_model(
    model: str,
    image_path: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Send a single API call to a model via OpenRouter.

    Returns dict with: reasoning, response, score, parse_method, identified_tactics.
    Retries on transient errors with exponential backoff.
    """
    import logging
    import time
    logger = logging.getLogger("dark_patterns")

    client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    )

    # Encode image
    base64_image = encode_image(image_path)
    mime_type = get_mime_type(image_path)

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}",
                    },
                },
                {
                    "type": "text",
                    "text": prompt,
                },
            ],
        }
    ]

    # Build API call kwargs
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Reasoning models get extended reasoning
    is_reasoning = model in REASONING_MODELS
    if is_reasoning:
        kwargs["extra_body"] = {
            "include_reasoning": True,
            "reasoning": {"effort": "medium"},
        }

    # Retry with exponential backoff on transient errors
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(**kwargs)
            break
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                logger.warning(f"API error for {model} (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"API call failed after {max_retries} attempts for {model}: {e}")
                return {
                    "reasoning": None,
                    "response": f"ERROR: {e}",
                    "score": None,
                    "parse_method": "none",
                    "identified_tactics": [],
                }
    message = response.choices[0].message
    content_text = message.content or ""

    # Extract chain-of-thought reasoning from various locations
    reasoning = None
    if is_reasoning:
        # Try message.reasoning_content (Claude, some providers)
        if getattr(message, "reasoning_content", None):
            reasoning = message.reasoning_content
        # Try message.reasoning (some providers)
        elif getattr(message, "reasoning", None):
            reasoning = message.reasoning
        # Try model_extra (OpenRouter extended fields)
        elif hasattr(message, "model_extra") and message.model_extra:
            reasoning = message.model_extra.get("reasoning_content") or message.model_extra.get("reasoning")
        # Try content blocks (Anthropic style)
        if reasoning is None and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    reasoning = block.get("thinking", "")
                    break

    # Parse response: try JSON first, then regex fallback
    parsed = extract_json_response(content_text)
    if parsed is not None:
        score = int(parsed["score"])
        parse_method = "json"
        identified_tactics = parsed.get("identified_tactics", [])
    else:
        score = extract_score(content_text)
        parse_method = "regex" if score is not None else "none"
        identified_tactics = []

    return {
        "reasoning": reasoning,
        "response": content_text,
        "score": score,
        "parse_method": parse_method,
        "identified_tactics": identified_tactics,
    }


def run_single_trial(
    trial_config: Dict[str, Any],
    temperature: float,
    max_tokens: int,
    enable_anchoring: bool,
) -> TrialResult:
    """Execute one trial and return a TrialResult."""
    model = trial_config["model"]
    image = trial_config["image"]
    condition = trial_config["condition"]
    task_variant = trial_config["task_variant"]
    cot_mode = trial_config["cot_mode"]
    target_product = trial_config["target_product"]

    # Build the main scoring prompt
    condition_prompt = get_condition_prompt(condition, target_product)
    cot_instruction = get_cot_instruction(cot_mode)
    full_prompt = f"{condition_prompt}\n\n{cot_instruction}"

    # If detect_then_score, run detection first
    if task_variant == "detect_then_score":
        detect_prompt = get_detect_prompt()
        call_model(
            model=model,
            image_path=image,
            prompt=detect_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Main scoring call
    result = call_model(
        model=model,
        image_path=image,
        prompt=full_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    # Anchoring follow-up
    anchoring_score = None
    if enable_anchoring:
        followup_prompt = get_anchoring_followup()
        followup_result = call_model(
            model=model,
            image_path=image,
            prompt=followup_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        anchoring_score = followup_result["score"]

    return TrialResult(
        trial_id=trial_config["trial_id"],
        model=model,
        image=image,
        condition=condition,
        task_mode=task_variant,
        cot_mode=cot_mode,
        target_product=target_product,
        trial_number=trial_config["trial_number"],
        temperature=temperature,
        score=result["score"],
        raw_response=result["response"],
        reasoning=result["reasoning"],
        identified_tactics=result["identified_tactics"],
        parse_method=result["parse_method"],
        anchoring_followup_score=anchoring_score,
        timestamp=datetime.now().isoformat(),
    )


def save_results(results: List[TrialResult], run_dir: str) -> None:
    """Save list of TrialResults to CSV and markdown report."""
    if not results:
        return

    # CSV
    rows = [r.to_dict() for r in results]
    df = pd.DataFrame(rows)
    csv_path = os.path.join(run_dir, "results.csv")
    df.to_csv(csv_path, index=False)

    # Markdown report
    md_path = os.path.join(run_dir, "report.md")
    with open(md_path, "w") as f:
        f.write("# Experiment Results\n\n")
        f.write(f"**Trials:** {len(results)}\n\n")
        f.write(f"**Models:** {', '.join(sorted(set(r.model for r in results)))}\n\n")
        f.write("## Results\n\n")
        f.write("| trial_id | model | condition | score | parse_method |\n")
        f.write("|----------|-------|-----------|-------|--------------|\n")
        for r in results:
            f.write(f"| {r.trial_id} | {r.model} | {r.condition} | {r.score} | {r.parse_method} |\n")


def load_checkpoint(run_dir: str) -> Set[str]:
    """Load completed trial IDs from an existing run directory."""
    csv_path = os.path.join(run_dir, "results.csv")
    if not os.path.isfile(csv_path):
        return set()
    df = pd.read_csv(csv_path)
    return set(df["trial_id"].tolist())


def run_experiment(
    models: List[str],
    images: List[str],
    conditions: List[str],
    trials: int,
    task_mode: str,
    cot_mode: str,
    enable_anchoring: bool,
    enable_counterbalancing: bool,
    temperature: float,
    max_tokens: int,
    base_dir: str,
    resume_run_id: Optional[str] = None,
) -> List[TrialResult]:
    """Main entry point: plan trials, run them, save incrementally.

    Args:
        resume_run_id: If provided, resume an existing run by skipping
            trials already in its CSV.
    """
    # Generate trial plan
    plan = generate_trial_plan(
        models=models,
        images=images,
        conditions=conditions,
        trials=trials,
        task_mode=task_mode,
        cot_mode=cot_mode,
        enable_anchoring=enable_anchoring,
        enable_counterbalancing=enable_counterbalancing,
    )

    # Create or resume run
    if resume_run_id:
        run_dir = os.path.join(base_dir, resume_run_id)
        completed_ids = load_checkpoint(run_dir)
    else:
        manifest = create_run_manifest(
            base_dir=base_dir,
            models=models,
            conditions=conditions,
            images=images,
            trials=trials,
            temperature=temperature,
            task_mode=task_mode,
            cot_mode=cot_mode,
            enable_anchoring=enable_anchoring,
            enable_counterbalancing=enable_counterbalancing,
            total_api_calls=len(plan),
        )
        run_dir = os.path.join(base_dir, manifest.run_id)
        completed_ids = set()

    # Filter out already-completed trials
    pending = [t for t in plan if t["trial_id"] not in completed_ids]

    # Load existing results if resuming so incremental saves include them
    results: List[TrialResult] = []
    if resume_run_id and completed_ids:
        csv_path = os.path.join(run_dir, "results.csv")
        if os.path.isfile(csv_path):
            existing_df = pd.read_csv(csv_path)
            for _, row in existing_df.iterrows():
                results.append(TrialResult(
                    trial_id=row["trial_id"],
                    model=row["model"],
                    image=row["image"],
                    condition=row["condition"],
                    task_mode=row["task_mode"],
                    cot_mode=row["cot_mode"],
                    target_product=row["target_product"],
                    trial_number=int(row["trial_number"]),
                    temperature=float(row["temperature"]),
                    score=int(row["score"]) if pd.notna(row["score"]) else None,
                    raw_response=row.get("raw_response", ""),
                    reasoning=row.get("reasoning"),
                    identified_tactics=row.get("identified_tactics", []),
                    parse_method=row.get("parse_method", "none"),
                    anchoring_followup_score=(
                        int(row["anchoring_followup_score"])
                        if pd.notna(row.get("anchoring_followup_score"))
                        else None
                    ),
                    timestamp=row.get("timestamp", ""),
                ))

    import logging
    logger = logging.getLogger("dark_patterns")

    for trial_config in tqdm(pending, desc="Running trials", disable=len(pending) == 0):
        try:
            result = run_single_trial(
                trial_config=trial_config,
                temperature=temperature,
                max_tokens=max_tokens,
                enable_anchoring=enable_anchoring,
            )
            results.append(result)

            # Incremental save
            save_results(results, run_dir)
        except Exception as e:
            logger.error(f"Trial {trial_config['trial_id']} failed: {e}")
            continue

    return results
