"""Tests for dark_patterns.judge module."""

import csv
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from dark_patterns.schemas import TrialResult, JudgeResult
from dark_patterns.judge import (
    JUDGE_RUBRIC,
    build_judge_prompt,
    call_judge,
    detect_self_evaluation,
    run_judge_pipeline,
    run_multi_judge,
    compute_judge_agreement,
    save_judge_results,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trial(**overrides) -> TrialResult:
    """Helper to create a TrialResult with sensible defaults."""
    defaults = dict(
        trial_id="t001",
        model="anthropic/claude-haiku-4.5",
        image="one-tag.png",
        condition="AVERAGE_CONSUMER",
        task_mode="single",
        cot_mode="on",
        target_product="B",
        trial_number=1,
        temperature=1.0,
        score=4,
        raw_response='{"score": 4, "explanation": "Looks good", "identified_tactics": ["social_proof"]}',
        reasoning="The product page shows social proof badges.",
        identified_tactics=["social_proof"],
        parse_method="json",
        anchoring_followup_score=None,
        timestamp="2026-03-03T10:00:00",
    )
    defaults.update(overrides)
    return TrialResult(**defaults)


def _make_image_metadata(**overrides):
    """Helper to create image metadata dict matching screenshots.yaml."""
    defaults = dict(
        file="one-tag.png",
        dark_pattern_type="social_proof",
        subtype="activity_badge",
        sp_element_count=1,
        is_control=False,
        ground_truth_manipulation=True,
        description="Product page with 1 social proof tag",
    )
    defaults.update(overrides)
    return defaults


MOCK_JUDGE_JSON = json.dumps({
    "detection_accuracy": 4,
    "specificity": 3,
    "consumer_harm_reasoning": 4,
    "evidence_grounding": 3,
    "logical_coherence": 5,
    "score_reasoning_alignment": 4,
    "overall_quality": 4,
    "notable_observations": "Good analysis of social proof elements.",
})


def _mock_chat_response(content: str):
    """Build a mock OpenAI-style chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# JUDGE_RUBRIC
# ---------------------------------------------------------------------------

class TestJudgeRubric:
    def test_has_six_dimensions(self):
        assert len(JUDGE_RUBRIC) == 6

    def test_expected_keys(self):
        expected = {
            "detection_accuracy",
            "specificity",
            "consumer_harm_reasoning",
            "evidence_grounding",
            "logical_coherence",
            "score_reasoning_alignment",
        }
        assert set(JUDGE_RUBRIC.keys()) == expected

    def test_values_are_strings(self):
        for v in JUDGE_RUBRIC.values():
            assert isinstance(v, str)
            assert len(v) > 10  # meaningful descriptions


# ---------------------------------------------------------------------------
# build_judge_prompt
# ---------------------------------------------------------------------------

class TestBuildJudgePrompt:
    def test_prompt_is_blind_no_model_name(self):
        trial = _make_trial(model="anthropic/claude-opus-4.6")
        meta = _make_image_metadata()
        prompt = build_judge_prompt(trial, meta)
        assert "claude-opus-4.6" not in prompt
        assert "anthropic" not in prompt

    def test_prompt_contains_ground_truth(self):
        meta = _make_image_metadata(
            dark_pattern_type="social_proof",
            is_control=False,
        )
        prompt = build_judge_prompt(_make_trial(), meta)
        assert "social_proof" in prompt
        assert "control" in prompt.lower() or "is_control" in prompt.lower() or "false" in prompt.lower()

    def test_prompt_contains_rubric_dimensions(self):
        prompt = build_judge_prompt(_make_trial(), _make_image_metadata())
        for dim in JUDGE_RUBRIC:
            assert dim in prompt

    def test_prompt_contains_model_response(self):
        trial = _make_trial(
            raw_response="The page shows urgency tactics.",
            reasoning="I see countdown timers.",
        )
        prompt = build_judge_prompt(trial, _make_image_metadata())
        assert "The page shows urgency tactics." in prompt
        assert "I see countdown timers." in prompt

    def test_prompt_contains_model_score(self):
        trial = _make_trial(score=3)
        prompt = build_judge_prompt(trial, _make_image_metadata())
        assert "3" in prompt

    def test_prompt_requests_json(self):
        prompt = build_judge_prompt(_make_trial(), _make_image_metadata())
        assert "json" in prompt.lower() or "JSON" in prompt

    def test_prompt_contains_image_file(self):
        meta = _make_image_metadata(file="two-tags.png")
        prompt = build_judge_prompt(_make_trial(), meta)
        assert "two-tags.png" in prompt


# ---------------------------------------------------------------------------
# call_judge
# ---------------------------------------------------------------------------

class TestCallJudge:
    @patch("dark_patterns.judge.OpenAI")
    def test_parses_json_into_judge_result(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_chat_response(MOCK_JUDGE_JSON)

        trial = _make_trial()
        meta = _make_image_metadata()
        result = call_judge(trial, meta, judge_model="openai/gpt-5.2")

        assert isinstance(result, JudgeResult)
        assert result.trial_id == "t001"
        assert result.judge_model == "openai/gpt-5.2"
        assert result.detection_accuracy == 4
        assert result.specificity == 3
        assert result.logical_coherence == 5
        assert result.overall_quality == 4

    @patch("dark_patterns.judge.OpenAI")
    def test_handles_markdown_wrapped_json(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        wrapped = f"```json\n{MOCK_JUDGE_JSON}\n```"
        mock_client.chat.completions.create.return_value = _mock_chat_response(wrapped)

        result = call_judge(_make_trial(), _make_image_metadata(), judge_model="openai/gpt-5.2")
        assert isinstance(result, JudgeResult)
        assert result.detection_accuracy == 4

    @patch("dark_patterns.judge.OpenAI")
    def test_returns_none_on_unparseable_response(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_chat_response("I cannot evaluate this.")

        result = call_judge(_make_trial(), _make_image_metadata(), judge_model="openai/gpt-5.2")
        assert result is None

    @patch("dark_patterns.judge.OpenAI")
    def test_sends_correct_model_to_api(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _mock_chat_response(MOCK_JUDGE_JSON)

        call_judge(_make_trial(), _make_image_metadata(), judge_model="google/gemini-3-pro-preview")

        create_call = mock_client.chat.completions.create
        assert create_call.called
        kwargs = create_call.call_args
        assert kwargs[1]["model"] == "google/gemini-3-pro-preview" or kwargs.kwargs["model"] == "google/gemini-3-pro-preview"


# ---------------------------------------------------------------------------
# detect_self_evaluation
# ---------------------------------------------------------------------------

class TestDetectSelfEvaluation:
    def test_same_model_returns_true(self):
        trial = _make_trial(model="anthropic/claude-opus-4.6")
        assert detect_self_evaluation("anthropic/claude-opus-4.6", trial) is True

    def test_different_model_returns_false(self):
        trial = _make_trial(model="anthropic/claude-haiku-4.5")
        assert detect_self_evaluation("openai/gpt-5.2", trial) is False

    def test_same_family_different_variant_returns_true(self):
        trial = _make_trial(model="anthropic/claude-opus-4.6")
        assert detect_self_evaluation("anthropic/claude-haiku-4.5", trial) is True

    def test_google_family(self):
        trial = _make_trial(model="google/gemini-3-pro-preview")
        assert detect_self_evaluation("google/gemini-2.5-flash", trial) is True

    def test_openai_family(self):
        trial = _make_trial(model="openai/gpt-5.2")
        assert detect_self_evaluation("openai/gpt-4o-mini", trial) is True

    def test_cross_family_returns_false(self):
        trial = _make_trial(model="anthropic/claude-opus-4.6")
        assert detect_self_evaluation("google/gemini-3-pro-preview", trial) is False


# ---------------------------------------------------------------------------
# run_judge_pipeline
# ---------------------------------------------------------------------------

class TestRunJudgePipeline:
    def _write_trial_csv(self, path, trials):
        """Write a list of TrialResult dicts to CSV."""
        if not trials:
            return
        fieldnames = list(trials[0].to_dict().keys())
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trials:
                writer.writerow(t.to_dict())

    def _write_manifest(self, path):
        """Write a minimal screenshots manifest."""
        import yaml
        data = {
            "images": [
                _make_image_metadata(file="one-tag.png"),
                _make_image_metadata(file="two-tags.png"),
            ]
        }
        with open(path, "w") as f:
            yaml.dump(data, f)

    @patch("dark_patterns.judge.call_judge")
    def test_calls_judge_for_each_trial(self, mock_call_judge, tmp_path):
        mock_call_judge.return_value = JudgeResult(
            trial_id="t001",
            judge_model="openai/gpt-5.2",
            detection_accuracy=4, specificity=3,
            consumer_harm_reasoning=4, evidence_grounding=3,
            logical_coherence=5, score_reasoning_alignment=4,
            overall_quality=4, notable_observations="Good.",
            timestamp="2026-03-03T10:00:00",
        )

        run_dir = tmp_path / "run_20260303"
        run_dir.mkdir()
        trial1 = _make_trial(trial_id="t001", model="anthropic/claude-haiku-4.5")
        trial2 = _make_trial(trial_id="t002", model="anthropic/claude-haiku-4.5")
        self._write_trial_csv(str(run_dir / "results.csv"), [trial1, trial2])

        manifest_path = str(tmp_path / "screenshots.yaml")
        self._write_manifest(manifest_path)

        results = run_judge_pipeline(
            input_dir=str(run_dir),
            judge_model="openai/gpt-5.2",
            manifest_path=manifest_path,
        )

        assert mock_call_judge.call_count == 2
        assert len(results) == 2

    @patch("dark_patterns.judge.call_judge")
    def test_skips_self_evaluation(self, mock_call_judge, tmp_path):
        run_dir = tmp_path / "run_20260303"
        run_dir.mkdir()
        # Trial from an anthropic model, judged by anthropic model -> self eval
        trial = _make_trial(trial_id="t001", model="anthropic/claude-opus-4.6")
        self._write_trial_csv(str(run_dir / "results.csv"), [trial])

        manifest_path = str(tmp_path / "screenshots.yaml")
        self._write_manifest(manifest_path)

        results = run_judge_pipeline(
            input_dir=str(run_dir),
            judge_model="anthropic/claude-haiku-4.5",
            manifest_path=manifest_path,
        )

        # Should skip because same family (anthropic)
        assert mock_call_judge.call_count == 0
        assert len(results) == 0

    @patch("dark_patterns.judge.call_judge")
    def test_saves_results_to_csv(self, mock_call_judge, tmp_path):
        mock_call_judge.return_value = JudgeResult(
            trial_id="t001",
            judge_model="openai/gpt-5.2",
            detection_accuracy=4, specificity=3,
            consumer_harm_reasoning=4, evidence_grounding=3,
            logical_coherence=5, score_reasoning_alignment=4,
            overall_quality=4, notable_observations="Good.",
            timestamp="2026-03-03T10:00:00",
        )

        run_dir = tmp_path / "run_20260303"
        run_dir.mkdir()
        trial = _make_trial(trial_id="t001", model="google/gemini-3-pro-preview")
        self._write_trial_csv(str(run_dir / "results.csv"), [trial])

        manifest_path = str(tmp_path / "screenshots.yaml")
        self._write_manifest(manifest_path)

        output_dir = tmp_path / "judge_output"
        output_dir.mkdir()

        results = run_judge_pipeline(
            input_dir=str(run_dir),
            judge_model="openai/gpt-5.2",
            manifest_path=manifest_path,
            output_dir=str(output_dir),
        )

        csv_files = list(output_dir.glob("*.csv"))
        assert len(csv_files) >= 1


# ---------------------------------------------------------------------------
# run_multi_judge
# ---------------------------------------------------------------------------

class TestRunMultiJudge:
    @patch("dark_patterns.judge.run_judge_pipeline")
    def test_calls_pipeline_for_each_judge(self, mock_pipeline, tmp_path):
        mock_pipeline.return_value = []

        run_dir = tmp_path / "run_20260303"
        run_dir.mkdir()

        manifest_path = str(tmp_path / "screenshots.yaml")
        import yaml
        with open(manifest_path, "w") as f:
            yaml.dump({"images": [_make_image_metadata()]}, f)

        judges = ["openai/gpt-5.2", "google/gemini-3-pro-preview", "anthropic/claude-opus-4.6"]
        run_multi_judge(
            input_dir=str(run_dir),
            judge_models=judges,
            manifest_path=manifest_path,
        )

        assert mock_pipeline.call_count == 3

    @patch("dark_patterns.judge.run_judge_pipeline")
    def test_uses_default_judges_when_none_specified(self, mock_pipeline, tmp_path):
        mock_pipeline.return_value = []

        run_dir = tmp_path / "run_20260303"
        run_dir.mkdir()

        manifest_path = str(tmp_path / "screenshots.yaml")
        import yaml
        with open(manifest_path, "w") as f:
            yaml.dump({"images": [_make_image_metadata()]}, f)

        run_multi_judge(
            input_dir=str(run_dir),
            manifest_path=manifest_path,
        )

        # Default should be 3 judges
        assert mock_pipeline.call_count == 3


# ---------------------------------------------------------------------------
# compute_judge_agreement
# ---------------------------------------------------------------------------

class TestComputeJudgeAgreement:
    def test_perfect_agreement_alpha_near_one(self):
        """When all judges give identical scores, alpha should be close to 1."""
        results_by_judge = {
            "judge_a": [
                JudgeResult(trial_id="t001", judge_model="judge_a",
                            detection_accuracy=4, specificity=3,
                            consumer_harm_reasoning=4, evidence_grounding=3,
                            logical_coherence=5, score_reasoning_alignment=4,
                            overall_quality=4, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
                JudgeResult(trial_id="t002", judge_model="judge_a",
                            detection_accuracy=2, specificity=1,
                            consumer_harm_reasoning=2, evidence_grounding=1,
                            logical_coherence=3, score_reasoning_alignment=2,
                            overall_quality=2, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
                JudgeResult(trial_id="t003", judge_model="judge_a",
                            detection_accuracy=5, specificity=5,
                            consumer_harm_reasoning=5, evidence_grounding=5,
                            logical_coherence=5, score_reasoning_alignment=5,
                            overall_quality=5, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
            ],
            "judge_b": [
                JudgeResult(trial_id="t001", judge_model="judge_b",
                            detection_accuracy=4, specificity=3,
                            consumer_harm_reasoning=4, evidence_grounding=3,
                            logical_coherence=5, score_reasoning_alignment=4,
                            overall_quality=4, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
                JudgeResult(trial_id="t002", judge_model="judge_b",
                            detection_accuracy=2, specificity=1,
                            consumer_harm_reasoning=2, evidence_grounding=1,
                            logical_coherence=3, score_reasoning_alignment=2,
                            overall_quality=2, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
                JudgeResult(trial_id="t003", judge_model="judge_b",
                            detection_accuracy=5, specificity=5,
                            consumer_harm_reasoning=5, evidence_grounding=5,
                            logical_coherence=5, score_reasoning_alignment=5,
                            overall_quality=5, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
            ],
        }

        alphas = compute_judge_agreement(results_by_judge)
        assert isinstance(alphas, dict)
        for dim in JUDGE_RUBRIC:
            assert dim in alphas
            assert alphas[dim] > 0.9  # perfect agreement -> alpha ~1

    def test_no_agreement_alpha_near_zero_or_negative(self):
        """When judges systematically disagree, alpha should be low."""
        # Judge A gives high scores, Judge B gives inverted scores
        results_by_judge = {
            "judge_a": [
                JudgeResult(trial_id=f"t{i:03d}", judge_model="judge_a",
                            detection_accuracy=5, specificity=5,
                            consumer_harm_reasoning=5, evidence_grounding=5,
                            logical_coherence=5, score_reasoning_alignment=5,
                            overall_quality=5, notable_observations="",
                            timestamp="2026-03-03T10:00:00")
                for i in range(10)
            ],
            "judge_b": [
                JudgeResult(trial_id=f"t{i:03d}", judge_model="judge_b",
                            detection_accuracy=1, specificity=1,
                            consumer_harm_reasoning=1, evidence_grounding=1,
                            logical_coherence=1, score_reasoning_alignment=1,
                            overall_quality=1, notable_observations="",
                            timestamp="2026-03-03T10:00:00")
                for i in range(10)
            ],
        }

        alphas = compute_judge_agreement(results_by_judge)
        for dim in JUDGE_RUBRIC:
            assert alphas[dim] < 0.1

    def test_returns_all_dimensions(self):
        """Agreement dict should have all rubric dimensions."""
        results_by_judge = {
            "judge_a": [
                JudgeResult(trial_id="t001", judge_model="judge_a",
                            detection_accuracy=3, specificity=3,
                            consumer_harm_reasoning=3, evidence_grounding=3,
                            logical_coherence=3, score_reasoning_alignment=3,
                            overall_quality=3, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
            ],
            "judge_b": [
                JudgeResult(trial_id="t001", judge_model="judge_b",
                            detection_accuracy=3, specificity=3,
                            consumer_harm_reasoning=3, evidence_grounding=3,
                            logical_coherence=3, score_reasoning_alignment=3,
                            overall_quality=3, notable_observations="",
                            timestamp="2026-03-03T10:00:00"),
            ],
        }

        alphas = compute_judge_agreement(results_by_judge)
        assert set(alphas.keys()) == set(JUDGE_RUBRIC.keys())


# ---------------------------------------------------------------------------
# save_judge_results
# ---------------------------------------------------------------------------

class TestSaveJudgeResults:
    def test_saves_csv(self, tmp_path):
        results = [
            JudgeResult(
                trial_id="t001",
                judge_model="openai/gpt-5.2",
                detection_accuracy=4, specificity=3,
                consumer_harm_reasoning=4, evidence_grounding=3,
                logical_coherence=5, score_reasoning_alignment=4,
                overall_quality=4, notable_observations="Good.",
                timestamp="2026-03-03T10:00:00",
            ),
            JudgeResult(
                trial_id="t002",
                judge_model="openai/gpt-5.2",
                detection_accuracy=2, specificity=2,
                consumer_harm_reasoning=3, evidence_grounding=2,
                logical_coherence=4, score_reasoning_alignment=3,
                overall_quality=3, notable_observations="OK.",
                timestamp="2026-03-03T10:01:00",
            ),
        ]

        output_dir = str(tmp_path / "judge_output")
        os.makedirs(output_dir, exist_ok=True)
        save_judge_results(results, output_dir)

        csv_files = list(tmp_path.glob("judge_output/*.csv"))
        assert len(csv_files) >= 1

        # Read back and verify content
        with open(csv_files[0], "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["trial_id"] == "t001"
        assert rows[0]["detection_accuracy"] == "4"

    def test_creates_output_directory_if_needed(self, tmp_path):
        results = [
            JudgeResult(
                trial_id="t001",
                judge_model="openai/gpt-5.2",
                detection_accuracy=4, specificity=3,
                consumer_harm_reasoning=4, evidence_grounding=3,
                logical_coherence=5, score_reasoning_alignment=4,
                overall_quality=4, notable_observations="Good.",
                timestamp="2026-03-03T10:00:00",
            ),
        ]

        output_dir = str(tmp_path / "new_dir" / "judge_output")
        save_judge_results(results, output_dir)
        assert os.path.isdir(output_dir)
