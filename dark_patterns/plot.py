"""Publication-quality plotting for the Dark Patterns research study."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from dark_patterns.utils import short_model_name

# ---------------------------------------------------------------------------
# Colorblind-safe palette
# ---------------------------------------------------------------------------
_CB_PALETTE = sns.color_palette("colorblind")
_GREEN = _CB_PALETTE[2]
_RED = _CB_PALETTE[3]
_BLUE = _CB_PALETTE[0]
_ORANGE = _CB_PALETTE[1]

# Journal column widths (inches)
_SINGLE_COL = 3.5
_DOUBLE_COL = 7.0


# ---------------------------------------------------------------------------
# 1. Publication style
# ---------------------------------------------------------------------------

def setup_publication_style() -> None:
    """Set matplotlib rcParams for publication-quality figures."""
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
    })


setup_publication_style()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_fig(fig: plt.Figure, output_dir: Path, stem: str, fmt: str = "png") -> None:
    """Save figure and close it."""
    out = Path(output_dir) / f"{stem}.{fmt}"
    fig.savefig(str(out), format=fmt)
    plt.close(fig)


def _short_models(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with shortened model names."""
    out = df.copy()
    out["model"] = out["model"].apply(short_model_name)
    return out


# ---------------------------------------------------------------------------
# 2. Score heatmap
# ---------------------------------------------------------------------------

def plot_score_heatmap(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Heatmap of mean scores: Model x Image."""
    sdf = _short_models(df)
    pivot = sdf.pivot_table(index="model", columns="image", values="score", aggfunc="mean")

    # Sort columns by sp_element_count if available
    if "sp_element_count" in df.columns:
        order = (
            df[["image", "sp_element_count"]]
            .drop_duplicates()
            .sort_values("sp_element_count")["image"]
            .tolist()
        )
        pivot = pivot[[c for c in order if c in pivot.columns]]

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.55))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        vmin=1,
        vmax=5,
        linewidths=0.5,
        ax=ax,
    )
    ax.set_ylabel("Model")
    ax.set_xlabel("Image")
    ax.set_title("Mean Recommendation Score (1\u20135)")
    fig.tight_layout()
    _save_fig(fig, output_dir, "score_heatmap", fmt)
    return fig


# ---------------------------------------------------------------------------
# 3. Skepticism delta
# ---------------------------------------------------------------------------

def plot_skepticism_delta(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Bar chart of (AVERAGE_CONSUMER - CONSUMER_ADVOCATE) mean score per model."""
    sdf = _short_models(df)
    naive = sdf[sdf["condition"] == "AVERAGE_CONSUMER"].groupby("model")["score"].mean()
    advocate = sdf[sdf["condition"] == "CONSUMER_ADVOCATE"].groupby("model")["score"].mean()
    delta = (naive - advocate).sort_values(ascending=False)

    colors = [_GREEN if v > 0 else _RED for v in delta.values]

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.5))
    bars = ax.bar(range(len(delta)), delta.values, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_xticks(range(len(delta)))
    ax.set_xticklabels(delta.index, rotation=45, ha="right")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("Score delta (points)")
    ax.set_xlabel("Model")
    ax.set_title("Skepticism Delta (Average Consumer \u2212 Consumer Advocate)")

    for bar in bars:
        h = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            h + (0.05 if h >= 0 else -0.15),
            f"{h:.2f}",
            ha="center",
            va="bottom" if h >= 0 else "top",
            fontsize=7,
            fontweight="bold",
        )

    fig.tight_layout()
    _save_fig(fig, output_dir, "skepticism_delta", fmt)
    return fig


# ---------------------------------------------------------------------------
# 4. Dose-response
# ---------------------------------------------------------------------------

def plot_dose_response(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Line plot of mean score vs SP element count, split by condition."""
    sdf = _short_models(df)

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.55))

    # Overall
    overall = sdf.groupby("sp_element_count")["score"].agg(["mean", "sem"]).reset_index()
    ax.errorbar(
        overall["sp_element_count"],
        overall["mean"],
        yerr=overall["sem"],
        fmt="o-",
        color="black",
        linewidth=2,
        markersize=7,
        capsize=4,
        label="Overall",
        zorder=5,
    )
    for _, row in overall.iterrows():
        ax.annotate(
            f"{row['mean']:.2f}",
            (row["sp_element_count"], row["mean"]),
            textcoords="offset points",
            xytext=(10, 8),
            fontsize=7,
            fontweight="bold",
        )

    # By condition
    cond_colors = {"AVERAGE_CONSUMER": _RED, "CONSUMER_ADVOCATE": _GREEN}
    cond_labels = {"AVERAGE_CONSUMER": "Average Consumer", "CONSUMER_ADVOCATE": "Consumer Advocate"}
    for cond, color in cond_colors.items():
        sub = sdf[sdf["condition"] == cond].groupby("sp_element_count")["score"].agg(["mean", "sem"]).reset_index()
        ax.errorbar(
            sub["sp_element_count"],
            sub["mean"],
            yerr=sub["sem"],
            fmt="s--",
            color=color,
            linewidth=1.5,
            markersize=6,
            capsize=3,
            label=cond_labels.get(cond, cond),
            alpha=0.85,
        )

    ax.set_xlabel("Number of social-proof elements")
    ax.set_ylabel("Mean recommendation score (1\u20135)")
    ax.set_title("Dose\u2013Response: Social Proof Elements vs. Score")
    ax.set_ylim(1, 5.5)
    ax.legend(loc="lower right", frameon=True)
    fig.tight_layout()
    _save_fig(fig, output_dir, "dose_response", fmt)
    return fig


# ---------------------------------------------------------------------------
# 5. Dose-response by model (faceted)
# ---------------------------------------------------------------------------

def plot_dose_response_by_model(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Faceted bar chart: SP count x condition, one subplot per model."""
    sdf = _short_models(df)
    sdf["condition_label"] = sdf["condition"].map({
        "AVERAGE_CONSUMER": "Avg. Consumer",
        "CONSUMER_ADVOCATE": "Cons. Advocate",
    })

    models = sorted(sdf["model"].unique())
    n = len(models)
    col_wrap = 3
    nrows = int(np.ceil(n / col_wrap))

    fig, axes = plt.subplots(nrows, col_wrap, figsize=(_DOUBLE_COL, 3 * nrows), squeeze=False)
    axes_flat = axes.flatten()

    for idx, model in enumerate(models):
        ax = axes_flat[idx]
        sub = sdf[sdf["model"] == model]
        sns.barplot(
            data=sub,
            x="sp_element_count",
            y="score",
            hue="condition_label",
            palette=[_RED, _GREEN],
            edgecolor="black",
            linewidth=0.5,
            ax=ax,
            errorbar=None,
        )
        ax.set_title(model, fontsize=8)
        ax.set_ylim(0, 5.5)
        ax.set_xlabel("")
        ax.set_ylabel("Score" if idx % col_wrap == 0 else "")
        ax.axhline(3.0, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)
        if idx == 0:
            ax.legend(fontsize=6, loc="upper left")
        else:
            legend = ax.get_legend()
            if legend is not None:
                legend.remove()

    # Hide unused subplots
    for idx in range(n, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle("Per-Model Dose\u2013Response", fontsize=10, y=1.01)
    fig.tight_layout()
    _save_fig(fig, output_dir, "dose_response_by_model", fmt)
    return fig


# ---------------------------------------------------------------------------
# 6. Score distributions
# ---------------------------------------------------------------------------

def plot_score_distributions(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Violin plots of score distributions per model, split by condition."""
    sdf = _short_models(df)
    sdf["condition_label"] = sdf["condition"].map({
        "AVERAGE_CONSUMER": "Avg. Consumer",
        "CONSUMER_ADVOCATE": "Cons. Advocate",
    })

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.55))
    sns.violinplot(
        data=sdf,
        x="model",
        y="score",
        hue="condition_label",
        split=True,
        inner="quart",
        palette=[_RED, _GREEN],
        ax=ax,
        linewidth=0.6,
    )
    ax.set_xlabel("Model")
    ax.set_ylabel("Recommendation score (1\u20135)")
    ax.set_title("Score Distributions by Model and Condition")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.legend(loc="upper right", frameon=True)
    fig.tight_layout()
    _save_fig(fig, output_dir, "score_distributions", fmt)
    return fig


# ---------------------------------------------------------------------------
# 7. Effect sizes forest plot
# ---------------------------------------------------------------------------

def plot_effect_sizes_forest(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Forest plot of Cohen's d with 95% CIs, sorted by effect size."""
    sdf = df.copy()
    sdf["model"] = sdf["model"].apply(short_model_name)
    sdf = sdf.sort_values("cohens_d", ascending=True)

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, max(_SINGLE_COL, len(sdf) * 0.5)))
    y_pos = range(len(sdf))

    ax.errorbar(
        sdf["cohens_d"],
        y_pos,
        xerr=[
            sdf["cohens_d"] - sdf["ci_low"],
            sdf["ci_high"] - sdf["cohens_d"],
        ],
        fmt="o",
        color=_BLUE,
        ecolor="gray",
        elinewidth=1.2,
        capsize=3,
        markersize=6,
    )
    ax.axvline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(sdf["model"].tolist())
    ax.set_xlabel("Cohen's d (effect size)")
    ax.set_title("Effect Sizes: Consumer Advocate vs. Average Consumer")
    fig.tight_layout()
    _save_fig(fig, output_dir, "effect_sizes_forest", fmt)
    return fig


# ---------------------------------------------------------------------------
# 8. Anchoring shift
# ---------------------------------------------------------------------------

def plot_anchoring_shift(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Paired dot plot: pre-nudge vs post-nudge scores per model."""
    sdf = df.copy()
    sdf["model"] = sdf["model"].apply(short_model_name)
    models = sorted(sdf["model"].unique())

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.55))
    x = np.arange(len(models))

    for _, row in sdf.iterrows():
        midx = models.index(row["model"])
        jitter = np.random.uniform(-0.1, 0.1)
        ax.plot(
            [midx + jitter, midx + jitter],
            [row["score"], row["anchoring_followup_score"]],
            color="gray",
            alpha=0.4,
            linewidth=0.8,
        )
        ax.scatter(midx + jitter, row["score"], color=_BLUE, s=20, zorder=3)
        ax.scatter(midx + jitter, row["anchoring_followup_score"], color=_ORANGE, s=20, zorder=3)

    # Means
    pre_means = sdf.groupby("model")["score"].mean()
    post_means = sdf.groupby("model")["anchoring_followup_score"].mean()
    for i, m in enumerate(models):
        ax.scatter(i, pre_means[m], color=_BLUE, s=80, marker="D", zorder=5, edgecolors="black", linewidths=0.5)
        ax.scatter(i, post_means[m], color=_ORANGE, s=80, marker="D", zorder=5, edgecolors="black", linewidths=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=45, ha="right")
    ax.set_ylabel("Score (1\u20135)")
    ax.set_xlabel("Model")
    ax.set_title("Anchoring Shift: Pre- vs. Post-Nudge Scores")

    # Legend
    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="D", color=_BLUE, label="Pre-nudge", markersize=6, linestyle="None"),
        Line2D([0], [0], marker="D", color=_ORANGE, label="Post-nudge", markersize=6, linestyle="None"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=True)
    fig.tight_layout()
    _save_fig(fig, output_dir, "anchoring_shift", fmt)
    return fig


# ---------------------------------------------------------------------------
# 9. Awareness-action gap
# ---------------------------------------------------------------------------

def plot_awareness_action_gap(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Grouped bar: % detecting dark pattern vs % recommending despite detecting."""
    sdf = df.copy()
    sdf["model"] = sdf["model"].apply(short_model_name)

    agg = sdf.groupby("model").agg(
        detect_pct=("detected_dark_pattern", "mean"),
        n=("score", "count"),
    )
    # % that detected AND still scored >= 3 (recommend)
    detected_only = sdf[sdf["detected_dark_pattern"]]
    detected_and_rec = detected_only.groupby("model")["score"].apply(
        lambda s: (s >= 3).mean()
    )
    agg["rec_despite_pct"] = detected_and_rec
    agg = agg.fillna(0)

    models = agg.index.tolist()
    x = np.arange(len(models))
    width = 0.35

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.55))
    ax.bar(x - width / 2, agg["detect_pct"] * 100, width, label="Detected dark pattern (%)", color=_BLUE, edgecolor="black", linewidth=0.5)
    ax.bar(x + width / 2, agg["rec_despite_pct"] * 100, width, label="Recommended despite detecting (%)", color=_RED, edgecolor="black", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=45, ha="right")
    ax.set_ylabel("Percentage (%)")
    ax.set_xlabel("Model")
    ax.set_title("Awareness\u2013Action Gap")
    ax.legend(loc="upper right", frameon=True, fontsize=7)
    fig.tight_layout()
    _save_fig(fig, output_dir, "awareness_action_gap", fmt)
    return fig


# ---------------------------------------------------------------------------
# 10. Judge quality heatmap
# ---------------------------------------------------------------------------

_JUDGE_DIMS = [
    "detection_accuracy",
    "specificity",
    "consumer_harm_reasoning",
    "evidence_grounding",
    "logical_coherence",
    "score_reasoning_alignment",
    "overall_quality",
]


def plot_judge_quality_heatmap(
    df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
) -> plt.Figure:
    """Heatmap of judge dimension scores: Model x Dimension."""
    sdf = df.copy()
    sdf["model"] = sdf["model"].apply(short_model_name)

    dims = [c for c in _JUDGE_DIMS if c in sdf.columns]
    pivot = sdf.groupby("model")[dims].mean()

    fig, ax = plt.subplots(figsize=(_DOUBLE_COL, _DOUBLE_COL * 0.5))
    sns.heatmap(
        pivot,
        annot=True,
        fmt=".2f",
        cmap="viridis",
        vmin=1,
        vmax=5,
        linewidths=0.5,
        ax=ax,
    )
    ax.set_ylabel("Model")
    ax.set_xlabel("Judge Dimension")
    ax.set_title("Judge Quality Scores (1\u20135)")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()
    _save_fig(fig, output_dir, "judge_quality_heatmap", fmt)
    return fig


# ---------------------------------------------------------------------------
# 11. plot_all
# ---------------------------------------------------------------------------

def plot_all(
    scores_df: pd.DataFrame,
    output_dir: str | Path = ".",
    fmt: str = "png",
    effect_sizes_df: Optional[pd.DataFrame] = None,
    anchoring_df: Optional[pd.DataFrame] = None,
    awareness_gap_df: Optional[pd.DataFrame] = None,
    judge_df: Optional[pd.DataFrame] = None,
) -> None:
    """Generate all applicable figures based on available data."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Core plots (always available with scores_df)
    plot_score_heatmap(scores_df, output_dir, fmt)
    plot_skepticism_delta(scores_df, output_dir, fmt)
    plot_score_distributions(scores_df, output_dir, fmt)

    if "sp_element_count" in scores_df.columns:
        plot_dose_response(scores_df, output_dir, fmt)
        plot_dose_response_by_model(scores_df, output_dir, fmt)

    # Optional plots
    if effect_sizes_df is not None:
        plot_effect_sizes_forest(effect_sizes_df, output_dir, fmt)

    if anchoring_df is not None:
        plot_anchoring_shift(anchoring_df, output_dir, fmt)

    if awareness_gap_df is not None:
        plot_awareness_action_gap(awareness_gap_df, output_dir, fmt)

    if judge_df is not None:
        plot_judge_quality_heatmap(judge_df, output_dir, fmt)
