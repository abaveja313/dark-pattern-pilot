"""Tests for dark_patterns.plot module."""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from dark_patterns.config import MODELS, CONDITIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_scores_df():
    """Synthetic DataFrame mimicking TrialResult data for plotting."""
    rng = np.random.RandomState(42)
    rows = []
    images = ["one-tag.png", "two-tags.png", "three-tags.png"]
    sp_counts = {"one-tag.png": 1, "two-tags.png": 2, "three-tags.png": 3}
    conditions = list(CONDITIONS.keys())

    for model in MODELS:
        for image in images:
            for condition in conditions:
                for trial in range(1, 4):
                    rows.append({
                        "model": model,
                        "image": image,
                        "condition": condition,
                        "score": int(rng.randint(1, 6)),
                        "trial_number": trial,
                        "sp_element_count": sp_counts[image],
                    })
    return pd.DataFrame(rows)


@pytest.fixture()
def effect_sizes_df():
    """Synthetic effect-sizes DataFrame for forest plot."""
    rng = np.random.RandomState(42)
    rows = []
    for model in MODELS:
        d = rng.normal(0.5, 0.3)
        rows.append({
            "model": model,
            "cohens_d": d,
            "ci_lower": d - rng.uniform(0.2, 0.5),
            "ci_upper": d + rng.uniform(0.2, 0.5),
        })
    return pd.DataFrame(rows)


@pytest.fixture()
def anchoring_df():
    """Synthetic anchoring data (aggregated per model)."""
    rng = np.random.RandomState(42)
    rows = []
    for model in MODELS:
        rows.append({
            "model": model,
            "mean_shift": rng.uniform(-0.5, 2.0),
            "p_value": rng.uniform(0.01, 0.5),
            "effect_size": rng.uniform(0.1, 1.0),
        })
    return pd.DataFrame(rows)


@pytest.fixture()
def awareness_gap_df():
    """Synthetic awareness/action gap data (aggregated per model)."""
    rng = np.random.RandomState(42)
    rows = []
    for model in MODELS:
        n_with = int(rng.randint(10, 20))
        n_gap = int(rng.randint(2, n_with))
        rows.append({
            "model": model,
            "n_with_tactics": n_with,
            "n_gap": n_gap,
            "gap_percentage": n_gap / n_with * 100,
        })
    return pd.DataFrame(rows)


@pytest.fixture()
def judge_df():
    """Synthetic judge results DataFrame."""
    rng = np.random.RandomState(42)
    dims = [
        "detection_accuracy",
        "specificity",
        "consumer_harm_reasoning",
        "evidence_grounding",
        "logical_coherence",
        "score_reasoning_alignment",
        "overall_quality",
    ]
    rows = []
    for model in MODELS:
        for trial in range(1, 4):
            row = {"model": model, "trial_number": trial}
            for dim in dims:
                row[dim] = int(rng.randint(1, 6))
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSetupPublicationStyle:
    def test_changes_rcparams(self):
        from dark_patterns.plot import setup_publication_style

        # Store a default before calling
        original_dpi = matplotlib.rcParams["savefig.dpi"]
        setup_publication_style()
        # Publication style should set 300 DPI
        assert matplotlib.rcParams["savefig.dpi"] == 300
        assert matplotlib.rcParams["font.size"] >= 8


class TestPlotScoreHeatmap:
    def test_file_created(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_score_heatmap

        plot_score_heatmap(sample_scores_df, output_dir=tmp_path)
        files = list(tmp_path.glob("score_heatmap.*"))
        assert len(files) >= 1

    def test_figure_axes(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_score_heatmap

        fig = plot_score_heatmap(sample_scores_df, output_dir=tmp_path)
        ax = fig.axes[0]
        # Heatmap should have ylabel (model) and xlabel (image)
        assert ax.get_ylabel() != "" or ax.get_xlabel() != ""
        plt.close("all")


class TestPlotSkepticismDelta:
    def test_file_created(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_skepticism_delta

        plot_skepticism_delta(sample_scores_df, output_dir=tmp_path)
        files = list(tmp_path.glob("skepticism_delta.*"))
        assert len(files) >= 1

    def test_bar_count_matches_models(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_skepticism_delta

        fig = plot_skepticism_delta(sample_scores_df, output_dir=tmp_path)
        ax = fig.axes[0]
        # Number of bars should match number of unique models
        n_models = sample_scores_df["model"].nunique()
        bars = [p for p in ax.patches if hasattr(p, "get_height")]
        assert len(bars) == n_models
        plt.close("all")


class TestPlotDoseResponse:
    def test_file_created(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_dose_response

        plot_dose_response(sample_scores_df, output_dir=tmp_path)
        files = list(tmp_path.glob("dose_response.*"))
        assert len(files) >= 1


class TestPlotDoseResponseByModel:
    def test_file_created(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_dose_response_by_model

        plot_dose_response_by_model(sample_scores_df, output_dir=tmp_path)
        files = list(tmp_path.glob("dose_response_by_model.*"))
        assert len(files) >= 1


class TestPlotScoreDistributions:
    def test_file_created(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_score_distributions

        plot_score_distributions(sample_scores_df, output_dir=tmp_path)
        files = list(tmp_path.glob("score_distributions.*"))
        assert len(files) >= 1


class TestPlotEffectSizesForest:
    def test_file_created(self, tmp_path, effect_sizes_df):
        from dark_patterns.plot import plot_effect_sizes_forest

        plot_effect_sizes_forest(effect_sizes_df, output_dir=tmp_path)
        files = list(tmp_path.glob("effect_sizes_forest.*"))
        assert len(files) >= 1


class TestPlotAnchoringShift:
    def test_file_created(self, tmp_path, anchoring_df):
        from dark_patterns.plot import plot_anchoring_shift

        plot_anchoring_shift(anchoring_df, output_dir=tmp_path)
        files = list(tmp_path.glob("anchoring_shift.*"))
        assert len(files) >= 1


class TestPlotAwarenessActionGap:
    def test_file_created(self, tmp_path, awareness_gap_df):
        from dark_patterns.plot import plot_awareness_action_gap

        plot_awareness_action_gap(awareness_gap_df, output_dir=tmp_path)
        files = list(tmp_path.glob("awareness_action_gap.*"))
        assert len(files) >= 1


class TestPlotJudgeQualityHeatmap:
    def test_file_created(self, tmp_path, judge_df):
        from dark_patterns.plot import plot_judge_quality_heatmap

        plot_judge_quality_heatmap(judge_df, output_dir=tmp_path)
        files = list(tmp_path.glob("judge_quality_heatmap.*"))
        assert len(files) >= 1


class TestPlotAll:
    def test_creates_multiple_files(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_all

        plot_all(
            scores_df=sample_scores_df,
            output_dir=tmp_path,
        )
        # At minimum the core plots that only need scores_df
        png_files = list(tmp_path.glob("*.png"))
        assert len(png_files) >= 4

    def test_with_all_data(
        self,
        tmp_path,
        sample_scores_df,
        effect_sizes_df,
        anchoring_df,
        awareness_gap_df,
        judge_df,
    ):
        from dark_patterns.plot import plot_all

        plot_all(
            scores_df=sample_scores_df,
            effect_sizes_df=effect_sizes_df,
            anchoring_df=anchoring_df,
            awareness_gap_df=awareness_gap_df,
            judge_df=judge_df,
            output_dir=tmp_path,
        )
        png_files = list(tmp_path.glob("*.png"))
        # All 9 plot types should be generated
        assert len(png_files) >= 9

    def test_pdf_format(self, tmp_path, sample_scores_df):
        from dark_patterns.plot import plot_all

        plot_all(
            scores_df=sample_scores_df,
            output_dir=tmp_path,
            fmt="pdf",
        )
        pdf_files = list(tmp_path.glob("*.pdf"))
        assert len(pdf_files) >= 4
