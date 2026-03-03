"""Tests for dark_patterns.schemas module."""

import pytest
from dark_patterns.schemas import (
    TrialResult,
    JudgeResult,
    RunManifest,
    validate_trial_result,
    validate_judge_result,
)


class TestTrialResult:
    def test_valid_result(self):
        result = TrialResult(
            trial_id="t001",
            model="anthropic/claude-opus-4.6",
            image="one-tag.png",
            condition="AVERAGE_CONSUMER",
            task_mode="single",
            cot_mode="on",
            target_product="B",
            trial_number=1,
            temperature=1.0,
            score=4,
            raw_response="Score: 4/5",
            reasoning="Thinking about the product...",
            identified_tactics=[],
            parse_method="regex",
            anchoring_followup_score=None,
            timestamp="2026-03-03T10:00:00",
        )
        assert result.score == 4
        assert result.model == "anthropic/claude-opus-4.6"

    def test_score_validation(self):
        with pytest.raises((ValueError, TypeError)):
            TrialResult(
                trial_id="t001",
                model="test/model",
                image="test.png",
                condition="AVERAGE_CONSUMER",
                task_mode="single",
                cot_mode="on",
                target_product="B",
                trial_number=1,
                temperature=1.0,
                score=6,  # out of range
                raw_response="test",
                reasoning=None,
                identified_tactics=[],
                parse_method="regex",
                anchoring_followup_score=None,
                timestamp="2026-03-03T10:00:00",
            )

    def test_none_score_allowed(self):
        result = TrialResult(
            trial_id="t001",
            model="test/model",
            image="test.png",
            condition="AVERAGE_CONSUMER",
            task_mode="single",
            cot_mode="on",
            target_product="B",
            trial_number=1,
            temperature=1.0,
            score=None,
            raw_response="No score found",
            reasoning=None,
            identified_tactics=[],
            parse_method="none",
            anchoring_followup_score=None,
            timestamp="2026-03-03T10:00:00",
        )
        assert result.score is None

    def test_to_dict(self):
        result = TrialResult(
            trial_id="t001",
            model="test/model",
            image="test.png",
            condition="AVERAGE_CONSUMER",
            task_mode="single",
            cot_mode="on",
            target_product="B",
            trial_number=1,
            temperature=1.0,
            score=3,
            raw_response="Score: 3/5",
            reasoning=None,
            identified_tactics=[],
            parse_method="regex",
            anchoring_followup_score=None,
            timestamp="2026-03-03T10:00:00",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["score"] == 3
        assert d["trial_id"] == "t001"


class TestJudgeResult:
    def test_valid_result(self):
        result = JudgeResult(
            trial_id="t001",
            judge_model="anthropic/claude-opus-4.6",
            detection_accuracy=4,
            specificity=3,
            consumer_harm_reasoning=4,
            evidence_grounding=3,
            logical_coherence=5,
            score_reasoning_alignment=4,
            overall_quality=4,
            notable_observations="Good analysis",
            timestamp="2026-03-03T10:00:00",
        )
        assert result.detection_accuracy == 4
        assert result.overall_quality == 4

    def test_dimension_validation(self):
        with pytest.raises((ValueError, TypeError)):
            JudgeResult(
                trial_id="t001",
                judge_model="test/model",
                detection_accuracy=6,  # out of 1-5 range
                specificity=3,
                consumer_harm_reasoning=4,
                evidence_grounding=3,
                logical_coherence=5,
                score_reasoning_alignment=4,
                overall_quality=4,
                notable_observations="",
                timestamp="2026-03-03T10:00:00",
            )

    def test_to_dict(self):
        result = JudgeResult(
            trial_id="t001",
            judge_model="test/model",
            detection_accuracy=4,
            specificity=3,
            consumer_harm_reasoning=4,
            evidence_grounding=3,
            logical_coherence=5,
            score_reasoning_alignment=4,
            overall_quality=4,
            notable_observations="",
            timestamp="2026-03-03T10:00:00",
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["detection_accuracy"] == 4


class TestRunManifest:
    def test_valid_manifest(self):
        manifest = RunManifest(
            run_id="20260303_100000",
            git_sha="abc123",
            models=["test/model"],
            conditions=["AVERAGE_CONSUMER"],
            images=["test.png"],
            trials=5,
            temperature=1.0,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
            total_api_calls=10,
            timestamp="2026-03-03T10:00:00",
        )
        assert manifest.trials == 5
        assert manifest.run_id == "20260303_100000"

    def test_to_dict(self):
        manifest = RunManifest(
            run_id="20260303_100000",
            git_sha="abc123",
            models=["test/model"],
            conditions=["AVERAGE_CONSUMER"],
            images=["test.png"],
            trials=5,
            temperature=1.0,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
            total_api_calls=10,
            timestamp="2026-03-03T10:00:00",
        )
        d = manifest.to_dict()
        assert d["trials"] == 5


class TestValidateTrialResult:
    def test_validates_valid_dict(self):
        data = {
            "trial_id": "t001",
            "model": "test/model",
            "image": "test.png",
            "condition": "AVERAGE_CONSUMER",
            "task_mode": "single",
            "cot_mode": "on",
            "target_product": "B",
            "trial_number": 1,
            "temperature": 1.0,
            "score": 3,
            "raw_response": "Score: 3/5",
            "reasoning": None,
            "identified_tactics": [],
            "parse_method": "regex",
            "anchoring_followup_score": None,
            "timestamp": "2026-03-03T10:00:00",
        }
        result = validate_trial_result(data)
        assert isinstance(result, TrialResult)

    def test_rejects_missing_fields(self):
        with pytest.raises((KeyError, TypeError)):
            validate_trial_result({"trial_id": "t001"})


class TestValidateJudgeResult:
    def test_validates_valid_dict(self):
        data = {
            "trial_id": "t001",
            "judge_model": "test/model",
            "detection_accuracy": 4,
            "specificity": 3,
            "consumer_harm_reasoning": 4,
            "evidence_grounding": 3,
            "logical_coherence": 5,
            "score_reasoning_alignment": 4,
            "overall_quality": 4,
            "notable_observations": "",
            "timestamp": "2026-03-03T10:00:00",
        }
        result = validate_judge_result(data)
        assert isinstance(result, JudgeResult)
