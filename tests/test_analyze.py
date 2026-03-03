"""Tests for dark_patterns.analyze module.

Uses synthetic data to verify statistical analysis functions.
TDD: tests written first, then implementation.
"""

import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from dark_patterns.analyze import (
    analyze_anchoring_effect,
    analyze_awareness_action_gap,
    analyze_inter_trial_consistency,
    analyze_position_bias,
    analyze_provider_differences,
    analyze_reasoning_tier,
    compute_descriptive_stats,
    compute_effect_sizes,
    correct_multiple_comparisons,
    fit_mixed_model,
    generate_latex_table,
    generate_summary_report,
    load_results,
    run_analysis,
    test_between_conditions as between_conditions_test,
    test_dose_response as dose_response_test,
    test_within_condition as within_condition_test,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MODELS = [
    "google/gemini-3-pro-preview",
    "anthropic/claude-opus-4.6",
    "openai/gpt-4o-mini",
]

CONDITIONS = ["AVERAGE_CONSUMER", "CONSUMER_ADVOCATE"]

IMAGES = ["one-tag.png", "two-tags.png", "three-tags.png"]

NUM_TRIALS = 5


@pytest.fixture()
def synthetic_df():
    """Generate a realistic synthetic DataFrame for testing.

    Design:
    - 3 models x 2 conditions x 3 images x 5 trials = 90 rows
    - CONSUMER_ADVOCATE scores are ~1 point lower than AVERAGE_CONSUMER
    - Some trials have identified_tactics (especially CONSUMER_ADVOCATE)
    - anchoring_followup_score is slightly higher than score (nudge effect)
    """
    rng = np.random.RandomState(42)
    rows = []
    trial_counter = 0
    for model in MODELS:
        for condition in CONDITIONS:
            for image in IMAGES:
                for trial in range(1, NUM_TRIALS + 1):
                    trial_counter += 1
                    base = 3.5 if condition == "AVERAGE_CONSUMER" else 2.5
                    score = int(np.clip(rng.normal(base, 0.6), 1, 5))
                    # Anchoring nudge adds ~0.5
                    anchor = int(np.clip(score + rng.choice([0, 1, 1]), 1, 5))
                    # CONSUMER_ADVOCATE is more likely to identify tactics
                    if condition == "CONSUMER_ADVOCATE":
                        tactics = ["social_proof", "urgency"] if rng.random() > 0.2 else []
                    else:
                        tactics = ["social_proof"] if rng.random() > 0.7 else []
                    rows.append(
                        {
                            "trial_id": f"trial_{trial_counter:04d}",
                            "model": model,
                            "image": image,
                            "condition": condition,
                            "task_mode": "single",
                            "cot_mode": "on",
                            "target_product": rng.choice(["A", "B"]),
                            "trial_number": trial,
                            "temperature": 1.0,
                            "score": score,
                            "raw_response": "test response",
                            "reasoning": "test reasoning",
                            "identified_tactics": str(tactics),
                            "parse_method": "json",
                            "anchoring_followup_score": anchor,
                            "timestamp": "2026-01-01T00:00:00",
                        }
                    )
    return pd.DataFrame(rows)


@pytest.fixture()
def synthetic_csv(synthetic_df, tmp_path):
    """Write synthetic data to a CSV file and return the path."""
    path = tmp_path / "trial_results.csv"
    synthetic_df.to_csv(path, index=False)
    return str(path)


@pytest.fixture()
def screenshots_manifest(tmp_path):
    """Write a screenshots manifest YAML and return the path."""
    path = tmp_path / "screenshots.yaml"
    path.write_text(
        "images:\n"
        "  - file: one-tag.png\n"
        "    sp_element_count: 1\n"
        "    is_control: false\n"
        "  - file: two-tags.png\n"
        "    sp_element_count: 2\n"
        "    is_control: false\n"
        "  - file: three-tags.png\n"
        "    sp_element_count: 3\n"
        "    is_control: false\n"
    )
    return str(path)


@pytest.fixture()
def dose_response_df(screenshots_manifest):
    """DataFrame with dose-dependent scores (higher sp_count -> higher scores)."""
    rng = np.random.RandomState(99)
    rows = []
    for model in MODELS:
        for image, sp_count in [("one-tag.png", 1), ("two-tags.png", 2), ("three-tags.png", 3)]:
            for trial in range(1, 11):
                # Clear dose-response relationship
                base_score = 1.5 + sp_count * 0.8
                score = int(np.clip(round(rng.normal(base_score, 0.5)), 1, 5))
                rows.append(
                    {
                        "trial_id": f"dr_{model}_{image}_{trial}",
                        "model": model,
                        "image": image,
                        "condition": "AVERAGE_CONSUMER",
                        "task_mode": "single",
                        "cot_mode": "on",
                        "target_product": "B",
                        "trial_number": trial,
                        "score": score,
                        "identified_tactics": "[]",
                        "anchoring_followup_score": score,
                        "timestamp": "2026-01-01T00:00:00",
                    }
                )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: load_results
# ---------------------------------------------------------------------------


class TestLoadResults:
    def test_loads_csv(self, synthetic_csv):
        df = load_results(synthetic_csv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 90

    def test_loads_with_judge_csv(self, synthetic_df, tmp_path):
        trial_path = tmp_path / "trial_results.csv"
        synthetic_df.to_csv(trial_path, index=False)

        judge_rows = []
        for tid in synthetic_df["trial_id"][:5]:
            judge_rows.append(
                {
                    "trial_id": tid,
                    "judge_model": "gpt-5.2",
                    "detection_accuracy": 4,
                    "overall_quality": 3,
                }
            )
        judge_path = tmp_path / "judge_results.csv"
        pd.DataFrame(judge_rows).to_csv(judge_path, index=False)

        df = load_results(str(trial_path), judge_csv=str(judge_path))
        assert "overall_quality" in df.columns

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_results("/nonexistent/results.csv")


# ---------------------------------------------------------------------------
# Tests: compute_descriptive_stats
# ---------------------------------------------------------------------------


class TestComputeDescriptiveStats:
    def test_returns_dataframe(self, synthetic_df):
        result = compute_descriptive_stats(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_contains_expected_columns(self, synthetic_df):
        result = compute_descriptive_stats(synthetic_df)
        for col in ["model", "condition", "mean", "sd", "median", "iqr"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_correct_group_count(self, synthetic_df):
        result = compute_descriptive_stats(synthetic_df)
        # 3 models x 2 conditions = 6 rows
        assert len(result) == 6

    def test_means_are_reasonable(self, synthetic_df):
        result = compute_descriptive_stats(synthetic_df)
        # All means should be between 1 and 5
        assert result["mean"].between(1, 5).all()

    def test_advocate_mean_lower(self, synthetic_df):
        result = compute_descriptive_stats(synthetic_df)
        for model in MODELS:
            m = result[result["model"] == model]
            avg = m[m["condition"] == "AVERAGE_CONSUMER"]["mean"].values[0]
            adv = m[m["condition"] == "CONSUMER_ADVOCATE"]["mean"].values[0]
            assert avg > adv, f"{model}: AVERAGE_CONSUMER mean should exceed CONSUMER_ADVOCATE"


# ---------------------------------------------------------------------------
# Tests: test_within_condition
# ---------------------------------------------------------------------------


class TestWithinCondition:
    def test_returns_dataframe(self, synthetic_df):
        result = within_condition_test(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, synthetic_df):
        result = within_condition_test(synthetic_df)
        for col in ["model", "condition", "test_stat", "p_value", "effect_size"]:
            assert col in result.columns

    def test_one_row_per_model_condition(self, synthetic_df):
        result = within_condition_test(synthetic_df)
        assert len(result) == len(MODELS) * len(CONDITIONS)

    def test_p_values_in_range(self, synthetic_df):
        result = within_condition_test(synthetic_df)
        assert result["p_value"].between(0, 1).all()


# ---------------------------------------------------------------------------
# Tests: test_between_conditions
# ---------------------------------------------------------------------------


class TestBetweenConditions:
    def test_returns_dataframe(self, synthetic_df):
        result = between_conditions_test(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_one_row_per_model(self, synthetic_df):
        result = between_conditions_test(synthetic_df)
        assert len(result) == len(MODELS)

    def test_has_required_columns(self, synthetic_df):
        result = between_conditions_test(synthetic_df)
        for col in ["model", "test_stat", "p_value", "effect_size_cohens_d", "effect_size_rank_biserial"]:
            assert col in result.columns

    def test_detects_significant_difference(self, synthetic_df):
        result = between_conditions_test(synthetic_df)
        # With ~1 point difference engineered in, at least one model should be significant
        assert (result["p_value"] < 0.05).any()


# ---------------------------------------------------------------------------
# Tests: compute_effect_sizes
# ---------------------------------------------------------------------------


class TestComputeEffectSizes:
    def test_returns_dataframe(self, synthetic_df):
        result = compute_effect_sizes(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, synthetic_df):
        result = compute_effect_sizes(synthetic_df)
        for col in ["model", "cohens_d", "ci_lower", "ci_upper"]:
            assert col in result.columns

    def test_cohens_d_positive(self, synthetic_df):
        """Positive d means AVERAGE_CONSUMER > CONSUMER_ADVOCATE (expected)."""
        result = compute_effect_sizes(synthetic_df)
        assert (result["cohens_d"] > 0).all()

    def test_ci_contains_point_estimate(self, synthetic_df):
        result = compute_effect_sizes(synthetic_df)
        for _, row in result.iterrows():
            assert row["ci_lower"] <= row["cohens_d"] <= row["ci_upper"]


# ---------------------------------------------------------------------------
# Tests: correct_multiple_comparisons
# ---------------------------------------------------------------------------


class TestCorrectMultipleComparisons:
    def test_adds_p_adjusted_column(self):
        df = pd.DataFrame({"model": ["a", "b", "c"], "p_value": [0.01, 0.04, 0.06]})
        result = correct_multiple_comparisons(df)
        assert "p_adjusted" in result.columns

    def test_adjusted_geq_original(self):
        df = pd.DataFrame({"model": ["a", "b", "c"], "p_value": [0.01, 0.04, 0.06]})
        result = correct_multiple_comparisons(df)
        assert (result["p_adjusted"] >= result["p_value"] - 1e-10).all()

    def test_adjusted_at_most_one(self):
        df = pd.DataFrame({"model": ["a", "b"], "p_value": [0.5, 0.9]})
        result = correct_multiple_comparisons(df)
        assert (result["p_adjusted"] <= 1.0 + 1e-10).all()

    def test_single_p_value(self):
        df = pd.DataFrame({"model": ["a"], "p_value": [0.03]})
        result = correct_multiple_comparisons(df)
        assert len(result) == 1
        assert "p_adjusted" in result.columns


# ---------------------------------------------------------------------------
# Tests: test_dose_response
# ---------------------------------------------------------------------------


class TestDoseResponse:
    def test_returns_dict(self, dose_response_df, screenshots_manifest):
        result = dose_response_test(dose_response_df, screenshots_manifest)
        assert isinstance(result, dict)
        assert "stat" in result
        assert "p_value" in result

    def test_significant_trend(self, dose_response_df, screenshots_manifest):
        """With engineered dose-response, trend should be significant."""
        result = dose_response_test(dose_response_df, screenshots_manifest)
        assert result["p_value"] < 0.05

    def test_handles_no_manifest_match(self, screenshots_manifest):
        """If images don't match manifest, should handle gracefully."""
        df = pd.DataFrame(
            {
                "model": ["m1"] * 3,
                "image": ["unknown.png"] * 3,
                "score": [3, 3, 3],
                "condition": ["AVERAGE_CONSUMER"] * 3,
            }
        )
        result = dose_response_test(df, screenshots_manifest)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: fit_mixed_model
# ---------------------------------------------------------------------------


class TestFitMixedModel:
    def test_returns_result(self, synthetic_df, screenshots_manifest):
        result = fit_mixed_model(synthetic_df, screenshots_manifest)
        assert result is not None

    def test_has_summary(self, synthetic_df, screenshots_manifest):
        result = fit_mixed_model(synthetic_df, screenshots_manifest)
        summary_str = str(result.summary())
        assert "Covariance" in summary_str or "Mixed" in summary_str or "coef" in summary_str.lower()


# ---------------------------------------------------------------------------
# Tests: analyze_anchoring_effect
# ---------------------------------------------------------------------------


class TestAnalyzeAnchoringEffect:
    def test_returns_dataframe(self, synthetic_df):
        result = analyze_anchoring_effect(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, synthetic_df):
        result = analyze_anchoring_effect(synthetic_df)
        for col in ["model", "mean_shift", "p_value"]:
            assert col in result.columns

    def test_detects_upward_shift(self, synthetic_df):
        """Anchoring followup was engineered to be >= score."""
        result = analyze_anchoring_effect(synthetic_df)
        assert (result["mean_shift"] >= 0).all()

    def test_handles_missing_anchoring(self):
        df = pd.DataFrame(
            {
                "model": ["m1"] * 5,
                "score": [3, 3, 3, 3, 3],
                "anchoring_followup_score": [None, None, None, None, None],
            }
        )
        result = analyze_anchoring_effect(df)
        assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Tests: analyze_awareness_action_gap
# ---------------------------------------------------------------------------


class TestAnalyzeAwarenessActionGap:
    def test_returns_dataframe(self, synthetic_df):
        result = analyze_awareness_action_gap(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, synthetic_df):
        result = analyze_awareness_action_gap(synthetic_df)
        for col in ["model", "gap_percentage"]:
            assert col in result.columns

    def test_gap_percentage_in_range(self, synthetic_df):
        result = analyze_awareness_action_gap(synthetic_df)
        assert result["gap_percentage"].between(0, 100).all()

    def test_known_gap(self):
        """If model detects tactics but gives high score, gap should be nonzero."""
        df = pd.DataFrame(
            {
                "model": ["m1"] * 4,
                "score": [5, 5, 2, 1],
                "identified_tactics": [
                    "['social_proof']",
                    "['urgency']",
                    "['social_proof']",
                    "[]",
                ],
            }
        )
        result = analyze_awareness_action_gap(df)
        # 2 out of 3 trials with tactics have high score -> gap ~66.7%
        assert result["gap_percentage"].iloc[0] > 60


# ---------------------------------------------------------------------------
# Tests: analyze_position_bias
# ---------------------------------------------------------------------------


class TestAnalyzePositionBias:
    def test_returns_dataframe(self, synthetic_df):
        result = analyze_position_bias(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, synthetic_df):
        result = analyze_position_bias(synthetic_df)
        for col in ["model", "mean_A", "mean_B", "p_value"]:
            assert col in result.columns

    def test_balanced_data_no_bias(self):
        """With identical distributions for A and B, no significant bias expected."""
        rng = np.random.RandomState(123)
        rows = []
        for model in ["m1"]:
            for prod in ["A", "B"]:
                for _ in range(30):
                    rows.append(
                        {"model": model, "target_product": prod, "score": rng.choice([3, 3, 4])}
                    )
        df = pd.DataFrame(rows)
        result = analyze_position_bias(df)
        assert result["p_value"].iloc[0] > 0.05


# ---------------------------------------------------------------------------
# Tests: analyze_inter_trial_consistency
# ---------------------------------------------------------------------------


class TestAnalyzeInterTrialConsistency:
    def test_returns_dataframe(self, synthetic_df):
        result = analyze_inter_trial_consistency(synthetic_df)
        assert isinstance(result, pd.DataFrame)

    def test_icc_in_range(self, synthetic_df):
        result = analyze_inter_trial_consistency(synthetic_df)
        if "ICC" in result.columns and len(result) > 0:
            assert result["ICC"].between(-1, 1).all()


# ---------------------------------------------------------------------------
# Tests: analyze_provider_differences
# ---------------------------------------------------------------------------


class TestAnalyzeProviderDifferences:
    def test_returns_dict(self, synthetic_df):
        result = analyze_provider_differences(synthetic_df)
        assert isinstance(result, dict)
        assert "stat" in result
        assert "p_value" in result

    def test_p_value_in_range(self, synthetic_df):
        result = analyze_provider_differences(synthetic_df)
        assert 0 <= result["p_value"] <= 1


# ---------------------------------------------------------------------------
# Tests: analyze_reasoning_tier
# ---------------------------------------------------------------------------


class TestAnalyzeReasoningTier:
    def test_returns_dict(self, synthetic_df):
        result = analyze_reasoning_tier(synthetic_df)
        assert isinstance(result, dict)
        assert "stat" in result
        assert "p_value" in result

    def test_p_value_in_range(self, synthetic_df):
        result = analyze_reasoning_tier(synthetic_df)
        assert 0 <= result["p_value"] <= 1


# ---------------------------------------------------------------------------
# Tests: generate_latex_table
# ---------------------------------------------------------------------------


class TestGenerateLatexTable:
    def test_contains_tabular(self, synthetic_df):
        latex = generate_latex_table(synthetic_df)
        assert "\\begin{tabular}" in latex
        assert "\\end{tabular}" in latex

    def test_contains_model_names(self, synthetic_df):
        latex = generate_latex_table(synthetic_df)
        # At least one short model name should appear
        assert "gemini" in latex.lower() or "claude" in latex.lower() or "gpt" in latex.lower()


# ---------------------------------------------------------------------------
# Tests: generate_summary_report
# ---------------------------------------------------------------------------


class TestGenerateSummaryReport:
    def test_returns_string(self, synthetic_df, screenshots_manifest):
        report = generate_summary_report(synthetic_df, screenshots_manifest)
        assert isinstance(report, str)

    def test_contains_sections(self, synthetic_df, screenshots_manifest):
        report = generate_summary_report(synthetic_df, screenshots_manifest)
        assert "Descriptive" in report or "descriptive" in report
        assert "Effect" in report or "effect" in report


# ---------------------------------------------------------------------------
# Tests: run_analysis
# ---------------------------------------------------------------------------


class TestRunAnalysis:
    def test_creates_output_files(self, synthetic_csv, screenshots_manifest, tmp_path):
        output_dir = str(tmp_path / "output")
        run_analysis(
            trial_csv=synthetic_csv,
            manifest_path=screenshots_manifest,
            output_dir=output_dir,
        )
        assert os.path.isdir(output_dir)
        # Should produce at least a summary report and a stats table
        files = os.listdir(output_dir)
        assert len(files) >= 2

    def test_creates_report_file(self, synthetic_csv, screenshots_manifest, tmp_path):
        output_dir = str(tmp_path / "output")
        run_analysis(
            trial_csv=synthetic_csv,
            manifest_path=screenshots_manifest,
            output_dir=output_dir,
        )
        report_files = [f for f in os.listdir(output_dir) if f.endswith(".md")]
        assert len(report_files) >= 1
