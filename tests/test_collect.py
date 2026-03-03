"""Tests for dark_patterns.collect module — written FIRST per TDD."""

import csv
import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest

from dark_patterns.config import CONDITIONS, MODELS, REASONING_MODELS
from dark_patterns.schemas import TrialResult


# ---------------------------------------------------------------------------
# generate_trial_plan
# ---------------------------------------------------------------------------

class TestGenerateTrialPlan:
    """Tests for generate_trial_plan()."""

    def test_single_task_single_cot(self):
        """Basic: 1 model * 1 image * 2 conditions * 2 trials = 4 trials."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=list(CONDITIONS.keys()),
            trials=2,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        assert len(plan) == 1 * 1 * 2 * 2  # 4

    def test_dual_task_doubles_variants(self):
        """dual task_mode adds score_first + detect_then_score variants."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=["AVERAGE_CONSUMER"],
            trials=1,
            task_mode="dual",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        # 1 model * 1 img * 1 cond * 1 trial * 2 variants = 2
        assert len(plan) == 2
        variants = {t["task_variant"] for t in plan}
        assert variants == {"score_first", "detect_then_score"}

    def test_cot_both_doubles(self):
        """cot_mode='both' produces on+off variants."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=["AVERAGE_CONSUMER"],
            trials=1,
            task_mode="single",
            cot_mode="both",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        # 1*1*1*1 * 2 cot variants = 2
        assert len(plan) == 2
        cot_modes = {t["cot_mode"] for t in plan}
        assert cot_modes == {"on", "off"}

    def test_dual_and_cot_both(self):
        """dual * both → 4 variants per base combo."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=["AVERAGE_CONSUMER"],
            trials=1,
            task_mode="dual",
            cot_mode="both",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        assert len(plan) == 4  # 2 task * 2 cot

    def test_counterbalancing_doubles(self):
        """Counterbalancing splits trials across Product A and Product B."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=["AVERAGE_CONSUMER"],
            trials=2,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=True,
        )
        # 1*1*1*2 = 2 trials; counterbalancing assigns half A, half B
        products = [t["target_product"] for t in plan]
        assert "A" in products
        assert "B" in products
        assert len(plan) == 2

    def test_trial_has_required_keys(self):
        """Each trial dict has all required keys."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1"],
            images=["img1.png"],
            conditions=["AVERAGE_CONSUMER"],
            trials=1,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        t = plan[0]
        for key in [
            "trial_id", "model", "image", "condition",
            "trial_number", "task_variant", "cot_mode", "target_product",
        ]:
            assert key in t, f"Missing key: {key}"

    def test_large_plan_count(self):
        """2 models * 3 images * 2 conditions * 5 trials = 60 (single/on)."""
        from dark_patterns.collect import generate_trial_plan

        plan = generate_trial_plan(
            models=["m1", "m2"],
            images=["a.png", "b.png", "c.png"],
            conditions=list(CONDITIONS.keys()),
            trials=5,
            task_mode="single",
            cot_mode="on",
            enable_anchoring=False,
            enable_counterbalancing=False,
        )
        assert len(plan) == 2 * 3 * 2 * 5


# ---------------------------------------------------------------------------
# create_run_manifest
# ---------------------------------------------------------------------------

class TestCreateRunManifest:
    """Tests for create_run_manifest()."""

    @patch("dark_patterns.collect.subprocess")
    def test_creates_directory_and_file(self, mock_subprocess):
        from dark_patterns.collect import create_run_manifest

        mock_subprocess.check_output.return_value = b"abc1234\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = create_run_manifest(
                base_dir=tmpdir,
                models=["m1"],
                conditions=["AVERAGE_CONSUMER"],
                images=["img.png"],
                trials=5,
                temperature=1.0,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                total_api_calls=10,
            )
            # Manifest should be saved to a run directory
            run_dir = os.path.join(tmpdir, manifest.run_id)
            manifest_path = os.path.join(run_dir, "manifest.json")
            assert os.path.isdir(run_dir)
            assert os.path.isfile(manifest_path)

            with open(manifest_path) as f:
                data = json.load(f)
            assert data["git_sha"] == "abc1234"
            assert data["models"] == ["m1"]
            assert data["trials"] == 5

    @patch("dark_patterns.collect.subprocess")
    def test_git_sha_fallback(self, mock_subprocess):
        """If git is unavailable, git_sha defaults to 'unknown'."""
        from dark_patterns.collect import create_run_manifest

        mock_subprocess.check_output.side_effect = Exception("no git")
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = create_run_manifest(
                base_dir=tmpdir,
                models=["m1"],
                conditions=["AVERAGE_CONSUMER"],
                images=["img.png"],
                trials=1,
                temperature=1.0,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                total_api_calls=1,
            )
            assert manifest.git_sha == "unknown"


# ---------------------------------------------------------------------------
# call_model
# ---------------------------------------------------------------------------

class TestCallModel:
    """Tests for call_model()."""

    def _make_mock_response(self, content_text, reasoning_content=None):
        """Build a mock OpenAI chat completion response."""
        msg = MagicMock()
        msg.content = content_text
        msg.reasoning_content = reasoning_content
        msg.reasoning = None
        msg.model_extra = {}

        choice = MagicMock()
        choice.message = msg

        response = MagicMock()
        response.choices = [choice]
        return response

    @patch("dark_patterns.collect.encode_image", return_value="AAAA")
    @patch("dark_patterns.collect.OpenAI")
    def test_basic_json_response(self, MockOpenAI, _mock_enc):
        """Parses a clean JSON response with score."""
        from dark_patterns.collect import call_model

        json_str = '{"score": 3, "explanation": "ok", "identified_tactics": ["urgency"]}'
        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(json_str)

        result = call_model(
            model="m1",
            image_path="/fake/img.png",
            prompt="Rate this",
            temperature=1.0,
            max_tokens=4000,
        )
        assert result["score"] == 3
        assert result["parse_method"] == "json"
        assert "urgency" in result["identified_tactics"]

    @patch("dark_patterns.collect.encode_image", return_value="AAAA")
    @patch("dark_patterns.collect.OpenAI")
    def test_regex_fallback(self, MockOpenAI, _mock_enc):
        """Falls back to regex when JSON parsing fails."""
        from dark_patterns.collect import call_model

        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(
            "I would give a score: 4 out of 5."
        )

        result = call_model(
            model="m1",
            image_path="/fake/img.png",
            prompt="Rate this",
            temperature=1.0,
            max_tokens=4000,
        )
        assert result["score"] == 4
        assert result["parse_method"] == "regex"

    @patch("dark_patterns.collect.encode_image", return_value="AAAA")
    @patch("dark_patterns.collect.OpenAI")
    def test_no_parseable_score(self, MockOpenAI, _mock_enc):
        """Returns score=None when nothing is parseable."""
        from dark_patterns.collect import call_model

        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(
            "I cannot evaluate this image."
        )

        result = call_model(
            model="m1",
            image_path="/fake/img.png",
            prompt="Rate this",
            temperature=1.0,
            max_tokens=4000,
        )
        assert result["score"] is None
        assert result["parse_method"] == "none"

    @patch("dark_patterns.collect.encode_image", return_value="AAAA")
    @patch("dark_patterns.collect.OpenAI")
    def test_reasoning_model_params(self, MockOpenAI, _mock_enc):
        """Reasoning models get include_reasoning=True in extra_body."""
        from dark_patterns.collect import call_model

        reasoning_model = REASONING_MODELS[0]
        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(
            '{"score": 2, "explanation": "bad", "identified_tactics": []}',
            reasoning_content="Let me think step by step..."
        )

        result = call_model(
            model=reasoning_model,
            image_path="/fake/img.png",
            prompt="Rate this",
            temperature=1.0,
            max_tokens=4000,
        )

        call_kwargs = client.chat.completions.create.call_args
        assert call_kwargs.kwargs.get("extra_body") is not None
        extra = call_kwargs.kwargs["extra_body"]
        assert extra.get("include_reasoning") is True

    @patch("dark_patterns.collect.encode_image", return_value="AAAA")
    @patch("dark_patterns.collect.OpenAI")
    def test_extracts_reasoning_content(self, MockOpenAI, _mock_enc):
        """Extracts reasoning from message.reasoning_content."""
        from dark_patterns.collect import call_model

        reasoning_model = REASONING_MODELS[0]
        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(
            '{"score": 3, "explanation": "mid", "identified_tactics": []}',
            reasoning_content="Step 1: I notice urgency popups..."
        )

        result = call_model(
            model=reasoning_model,
            image_path="/fake/img.png",
            prompt="Rate this",
            temperature=1.0,
            max_tokens=4000,
        )
        assert result["reasoning"] == "Step 1: I notice urgency popups..."

    @patch("dark_patterns.collect.OpenAI")
    def test_api_call_structure(self, MockOpenAI):
        """Verify the API call includes image content block."""
        from dark_patterns.collect import call_model

        client = MagicMock()
        MockOpenAI.return_value = client
        client.chat.completions.create.return_value = self._make_mock_response(
            '{"score": 3, "explanation": "ok", "identified_tactics": []}'
        )

        # Create a tiny real image to encode
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
            img_path = f.name

        try:
            call_model(
                model="m1",
                image_path=img_path,
                prompt="Rate this",
                temperature=1.0,
                max_tokens=4000,
            )

            call_kwargs = client.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            assert len(messages) == 1
            user_msg = messages[0]
            assert user_msg["role"] == "user"
            # Content should have image_url and text parts
            assert any(p.get("type") == "image_url" for p in user_msg["content"])
            assert any(p.get("type") == "text" for p in user_msg["content"])
        finally:
            os.unlink(img_path)


# ---------------------------------------------------------------------------
# run_single_trial
# ---------------------------------------------------------------------------

class TestRunSingleTrial:
    """Tests for run_single_trial()."""

    @patch("dark_patterns.collect.call_model")
    def test_single_task_score_first(self, mock_call):
        """Single task, score_first variant: one call_model call."""
        from dark_patterns.collect import run_single_trial

        mock_call.return_value = {
            "reasoning": None,
            "response": '{"score": 3}',
            "score": 3,
            "parse_method": "json",
            "identified_tactics": ["fake urgency"],
        }

        trial_config = {
            "trial_id": "t1",
            "model": "m1",
            "image": "/fake/img.png",
            "condition": "AVERAGE_CONSUMER",
            "trial_number": 1,
            "task_variant": "score_first",
            "cot_mode": "on",
            "target_product": "B",
        }

        result = run_single_trial(
            trial_config=trial_config,
            temperature=1.0,
            max_tokens=4000,
            enable_anchoring=False,
        )
        assert isinstance(result, TrialResult)
        assert result.score == 3
        assert result.trial_id == "t1"
        assert result.task_mode == "score_first"
        assert mock_call.call_count == 1

    @patch("dark_patterns.collect.call_model")
    def test_dual_detect_then_score(self, mock_call):
        """detect_then_score variant: two call_model calls."""
        from dark_patterns.collect import run_single_trial

        mock_call.side_effect = [
            # First call: detection
            {
                "reasoning": None,
                "response": "I see fake urgency and social proof badges.",
                "score": None,
                "parse_method": "none",
                "identified_tactics": [],
            },
            # Second call: scoring
            {
                "reasoning": None,
                "response": '{"score": 2, "explanation": "manipulative", "identified_tactics": ["urgency"]}',
                "score": 2,
                "parse_method": "json",
                "identified_tactics": ["urgency"],
            },
        ]

        trial_config = {
            "trial_id": "t2",
            "model": "m1",
            "image": "/fake/img.png",
            "condition": "AVERAGE_CONSUMER",
            "trial_number": 1,
            "task_variant": "detect_then_score",
            "cot_mode": "on",
            "target_product": "B",
        }

        result = run_single_trial(
            trial_config=trial_config,
            temperature=1.0,
            max_tokens=4000,
            enable_anchoring=False,
        )
        assert result.score == 2
        assert mock_call.call_count == 2

    @patch("dark_patterns.collect.call_model")
    def test_anchoring_followup(self, mock_call):
        """With anchoring enabled, an extra follow-up call is made."""
        from dark_patterns.collect import run_single_trial

        mock_call.side_effect = [
            # Main scoring call
            {
                "reasoning": None,
                "response": '{"score": 2, "explanation": "ok", "identified_tactics": []}',
                "score": 2,
                "parse_method": "json",
                "identified_tactics": [],
            },
            # Anchoring follow-up
            {
                "reasoning": None,
                "response": '{"score": 4, "explanation": "revised up", "identified_tactics": []}',
                "score": 4,
                "parse_method": "json",
                "identified_tactics": [],
            },
        ]

        trial_config = {
            "trial_id": "t3",
            "model": "m1",
            "image": "/fake/img.png",
            "condition": "AVERAGE_CONSUMER",
            "trial_number": 1,
            "task_variant": "score_first",
            "cot_mode": "on",
            "target_product": "B",
        }

        result = run_single_trial(
            trial_config=trial_config,
            temperature=1.0,
            max_tokens=4000,
            enable_anchoring=True,
        )
        assert result.score == 2
        assert result.anchoring_followup_score == 4
        assert mock_call.call_count == 2


# ---------------------------------------------------------------------------
# run_experiment (integration-ish with mocks)
# ---------------------------------------------------------------------------

class TestRunExperiment:
    """Tests for run_experiment()."""

    @patch("dark_patterns.collect.call_model")
    def test_runs_all_trials(self, mock_call):
        """run_experiment iterates through all planned trials."""
        from dark_patterns.collect import run_experiment

        mock_call.return_value = {
            "reasoning": None,
            "response": '{"score": 3, "explanation": "ok", "identified_tactics": []}',
            "score": 3,
            "parse_method": "json",
            "identified_tactics": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_experiment(
                models=["m1"],
                images=["img.png"],
                conditions=["AVERAGE_CONSUMER"],
                trials=2,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                temperature=1.0,
                max_tokens=4000,
                base_dir=tmpdir,
            )
            assert len(results) == 2
            assert all(isinstance(r, TrialResult) for r in results)

    @patch("dark_patterns.collect.call_model")
    def test_resume_skips_completed(self, mock_call):
        """--resume skips trials already in the CSV."""
        from dark_patterns.collect import run_experiment, generate_trial_plan

        mock_call.return_value = {
            "reasoning": None,
            "response": '{"score": 3, "explanation": "ok", "identified_tactics": []}',
            "score": 3,
            "parse_method": "json",
            "identified_tactics": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # First run: do all trials
            results1 = run_experiment(
                models=["m1"],
                images=["img.png"],
                conditions=["AVERAGE_CONSUMER"],
                trials=3,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                temperature=1.0,
                max_tokens=4000,
                base_dir=tmpdir,
            )
            first_call_count = mock_call.call_count
            assert len(results1) == 3

            # Find the run directory
            run_dirs = [
                d for d in os.listdir(tmpdir)
                if os.path.isdir(os.path.join(tmpdir, d))
            ]
            assert len(run_dirs) == 1
            run_id = run_dirs[0]

            # Reset mock
            mock_call.reset_mock()

            # Resume: should skip all 3 existing trials
            results2 = run_experiment(
                models=["m1"],
                images=["img.png"],
                conditions=["AVERAGE_CONSUMER"],
                trials=3,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                temperature=1.0,
                max_tokens=4000,
                base_dir=tmpdir,
                resume_run_id=run_id,
            )
            # No new API calls because all trials were completed
            assert mock_call.call_count == 0

    @patch("dark_patterns.collect.call_model")
    def test_saves_incremental_csv(self, mock_call):
        """Results are saved to CSV after each trial."""
        from dark_patterns.collect import run_experiment

        mock_call.return_value = {
            "reasoning": None,
            "response": '{"score": 3, "explanation": "ok", "identified_tactics": []}',
            "score": 3,
            "parse_method": "json",
            "identified_tactics": [],
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            results = run_experiment(
                models=["m1"],
                images=["img.png"],
                conditions=["AVERAGE_CONSUMER"],
                trials=2,
                task_mode="single",
                cot_mode="on",
                enable_anchoring=False,
                enable_counterbalancing=False,
                temperature=1.0,
                max_tokens=4000,
                base_dir=tmpdir,
            )

            # Find the run directory and CSV
            run_dirs = [
                d for d in os.listdir(tmpdir)
                if os.path.isdir(os.path.join(tmpdir, d))
            ]
            run_dir = os.path.join(tmpdir, run_dirs[0])
            csv_path = os.path.join(run_dir, "results.csv")
            assert os.path.isfile(csv_path)

            df = pd.read_csv(csv_path)
            assert len(df) == 2


# ---------------------------------------------------------------------------
# save_results
# ---------------------------------------------------------------------------

class TestSaveResults:
    """Tests for save_results()."""

    def _make_trial_result(self, trial_id="t1", score=3):
        return TrialResult(
            trial_id=trial_id,
            model="m1",
            image="img.png",
            condition="AVERAGE_CONSUMER",
            task_mode="score_first",
            cot_mode="on",
            target_product="B",
            trial_number=1,
            temperature=1.0,
            score=score,
            raw_response='{"score": 3}',
            reasoning=None,
            identified_tactics=["urgency"],
            parse_method="json",
            anchoring_followup_score=None,
            timestamp="2026-01-01T00:00:00",
        )

    def test_saves_csv(self):
        from dark_patterns.collect import save_results

        results = [self._make_trial_result("t1", 3), self._make_trial_result("t2", 4)]
        with tempfile.TemporaryDirectory() as tmpdir:
            save_results(results, tmpdir)
            csv_path = os.path.join(tmpdir, "results.csv")
            assert os.path.isfile(csv_path)
            df = pd.read_csv(csv_path)
            assert len(df) == 2
            assert list(df["trial_id"]) == ["t1", "t2"]

    def test_saves_markdown(self):
        from dark_patterns.collect import save_results

        results = [self._make_trial_result()]
        with tempfile.TemporaryDirectory() as tmpdir:
            save_results(results, tmpdir)
            md_path = os.path.join(tmpdir, "report.md")
            assert os.path.isfile(md_path)
            with open(md_path) as f:
                content = f.read()
            assert "t1" in content


# ---------------------------------------------------------------------------
# load_checkpoint
# ---------------------------------------------------------------------------

class TestLoadCheckpoint:
    """Tests for load_checkpoint()."""

    def test_loads_existing_csv(self):
        from dark_patterns.collect import load_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "results.csv")
            df = pd.DataFrame([{
                "trial_id": "t1",
                "model": "m1",
                "image": "img.png",
                "condition": "AVERAGE_CONSUMER",
                "task_mode": "score_first",
                "cot_mode": "on",
                "target_product": "B",
                "trial_number": 1,
                "temperature": 1.0,
                "score": 3,
                "raw_response": '{"score": 3}',
                "reasoning": "",
                "identified_tactics": "['urgency']",
                "parse_method": "json",
                "anchoring_followup_score": "",
                "timestamp": "2026-01-01T00:00:00",
            }])
            df.to_csv(csv_path, index=False)

            completed_ids = load_checkpoint(tmpdir)
            assert "t1" in completed_ids

    def test_returns_empty_for_missing(self):
        from dark_patterns.collect import load_checkpoint

        with tempfile.TemporaryDirectory() as tmpdir:
            completed_ids = load_checkpoint(tmpdir)
            assert completed_ids == set()
