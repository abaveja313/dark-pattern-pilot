#!/usr/bin/env python3
"""
V4 Social Proof Dose-Response Analysis

Hypothesis: More social proof elements → higher recommendation scores.
Images: one-tag.png (1 SP), two-tags.png (2 SP), three-tags.png (3 SP)

Generates:
  1. heatmap_scores_v4.png        — Model × Image heatmap
  2. delta_skepticism_v4.png      — Skepticism delta (Naive − Critical) per model
  3. dose_response_v4.png         — Line plot: mean score vs # of social proof tags
  4. dose_response_by_model_v4.png — Per-model breakdown of dose-response
  5. Prints statistical summary to terminal
"""

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.use("Agg")

# ─── Configuration ──────────────────────────────────────────────────────────
INPUT_CSV = "social_proof_results_v4.csv"

# Map image filenames → number of social proof tags
SP_COUNT = {
    "one-tag.png": 1,
    "two-tags.png": 2,
    "three-tags.png": 3,
}

SP_LABELS = {
    "one-tag.png": "1 Tag",
    "two-tags.png": "2 Tags",
    "three-tags.png": "3 Tags",
}


def load_data():
    print(f"📂 Loading data from {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    df["Raw Score"] = pd.to_numeric(df["Raw Score"], errors="coerce")
    df = df.dropna(subset=["Raw Score"])
    df["SP Count"] = df["Image"].map(SP_COUNT)
    df["SP Label"] = df["Image"].map(SP_LABELS)
    df["Model Short"] = df["Model"].apply(lambda x: x.split("/")[-1])
    df["Condition"] = df["Condition"].replace({
        "AVERAGE_CONSUMER": "Average Consumer",
        "CONSUMER_ADVOCATE": "Consumer Advocate",
    })
    return df


# ═════════════════════════════════════════════════════════════════════════════
# 1. HEATMAP (Model × Image)
# ═════════════════════════════════════════════════════════════════════════════
def generate_heatmap(df):
    print("🎨 Generating Heatmap...")
    pivot = df.pivot_table(
        index="Model", columns="Image", values="Raw Score", aggfunc="mean"
    )
    # Reorder columns by SP count
    ordered_cols = sorted(pivot.columns, key=lambda c: SP_COUNT.get(c, 0))
    pivot = pivot[ordered_cols]

    plt.figure(figsize=(10, 6))
    sns.heatmap(
        pivot, annot=True, fmt=".1f", cmap="RdYlGn",
        linewidths=0.5, vmin=1, vmax=5,
    )
    plt.title("Mean Recommendation Score (1-5)\nBy Model and Image (Ordered by # Social Proof Tags)",
              fontsize=14, pad=20)
    plt.xlabel("Image (Social Proof Tags)", fontsize=12)
    plt.ylabel("Model", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig("heatmap_scores_v4.png", dpi=150)
    plt.close()
    print("✅ Saved heatmap_scores_v4.png")


# ═════════════════════════════════════════════════════════════════════════════
# 2. DELTA CHART (Skepticism Gap)
# ═════════════════════════════════════════════════════════════════════════════
def generate_delta_chart(df):
    print("🎨 Generating Delta Chart...")
    naive = df[df["Condition"] == "Average Consumer"].groupby("Model")["Raw Score"].mean()
    critical = df[df["Condition"] == "Consumer Advocate"].groupby("Model")["Raw Score"].mean()
    delta = (naive - critical).sort_values(ascending=False)

    if delta.empty:
        print("⚠️ No data for Delta Chart.")
        return

    plt.figure(figsize=(12, 6))
    colors = ["#2ecc71" if x > 0 else "#e74c3c" for x in delta.values]
    bars = plt.bar(delta.index, delta.values, color=colors, edgecolor="black", alpha=0.8)

    plt.axhline(0, color="black", linewidth=1)
    plt.title("Skepticism Delta (Average Consumer − Consumer Advocate)\n"
              "Positive = Model Reduced Score When Acting as Advocate",
              fontsize=14, pad=15)
    plt.ylabel("Score Drop (Points)", fontsize=12)
    plt.xlabel("Model", fontsize=12)
    plt.xticks(rotation=45, ha="right")

    for bar in bars:
        h = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2., h + (0.05 if h > 0 else -0.15),
                 f"{h:.2f}", ha="center", va="bottom", fontsize=10, fontweight="bold")

    plt.tight_layout()
    plt.savefig("delta_skepticism_v4.png", dpi=150)
    plt.close()
    print("✅ Saved delta_skepticism_v4.png")


# ═════════════════════════════════════════════════════════════════════════════
# 3. DOSE-RESPONSE CURVE (Overall + By Condition)
# ═════════════════════════════════════════════════════════════════════════════
def generate_dose_response(df):
    print("🎨 Generating Dose-Response Plot...")
    sns.set_theme(style="whitegrid", font_scale=1.1)

    fig, ax = plt.subplots(figsize=(10, 6))

    # --- Overall mean ---
    overall = df.groupby("SP Count")["Raw Score"].agg(["mean", "std", "count"]).reset_index()
    overall["se"] = overall["std"] / np.sqrt(overall["count"])
    ax.errorbar(overall["SP Count"], overall["mean"], yerr=overall["se"],
                fmt="o-", color="black", linewidth=2.5, markersize=10,
                capsize=6, label="Overall Mean", zorder=5)

    # --- By condition ---
    palette = {"Average Consumer": "#e74c3c", "Consumer Advocate": "#2ecc71"}
    for condition, color in palette.items():
        cond_data = df[df["Condition"] == condition].groupby("SP Count")["Raw Score"].agg(["mean", "std", "count"]).reset_index()
        cond_data["se"] = cond_data["std"] / np.sqrt(cond_data["count"])
        ax.errorbar(cond_data["SP Count"], cond_data["mean"], yerr=cond_data["se"],
                    fmt="s--", color=color, linewidth=1.8, markersize=8,
                    capsize=5, label=condition, alpha=0.85)

    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["1 Tag\n(Baseline)", "2 Tags", "3 Tags"], fontsize=12)
    ax.set_ylim(1, 5.5)
    ax.set_xlabel("Number of Social Proof Tags", fontsize=13)
    ax.set_ylabel("Mean Recommendation Score (1-5)", fontsize=13)
    ax.set_title("Dose-Response: Do More Social Proof Tags → Higher Scores?",
                 fontsize=15, fontweight="bold", pad=15)
    ax.legend(fontsize=11, loc="lower right")

    # Annotate mean values
    for _, row in overall.iterrows():
        ax.annotate(f"{row['mean']:.2f}", (row["SP Count"], row["mean"]),
                    textcoords="offset points", xytext=(15, 10),
                    fontsize=11, fontweight="bold")

    plt.tight_layout()
    plt.savefig("dose_response_v4.png", dpi=150)
    plt.close()
    print("✅ Saved dose_response_v4.png")


# ═════════════════════════════════════════════════════════════════════════════
# 4. DOSE-RESPONSE BY MODEL (Faceted)
# ═════════════════════════════════════════════════════════════════════════════
def generate_dose_response_by_model(df):
    print("🎨 Generating Per-Model Dose-Response Plot...")
    sns.set_theme(style="whitegrid", font_scale=1.0)

    g = sns.catplot(
        data=df, kind="bar",
        x="SP Label", y="Raw Score", hue="Condition",
        col="Model Short", col_wrap=3,
        height=4, aspect=1.3,
        palette={"Average Consumer": "#e74c3c", "Consumer Advocate": "#2ecc71"},
        edgecolor="black",
        order=["1 Tag", "2 Tags", "3 Tags"],
    )

    for ax in g.axes.flat:
        ax.set_ylim(0, 5.5)
        ax.axhline(3.0, color="gray", linestyle="--", linewidth=1, alpha=0.6)
        ax.set_xlabel("")
        ax.set_ylabel("Score (1-5)")

    g.figure.suptitle("Per-Model: Score vs. Number of Social Proof Tags",
                      fontsize=16, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig("dose_response_by_model_v4.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("✅ Saved dose_response_by_model_v4.png")


# ═════════════════════════════════════════════════════════════════════════════
# 5. STATISTICAL SUMMARY
# ═════════════════════════════════════════════════════════════════════════════
def print_statistical_summary(df):
    print("\n" + "=" * 70)
    print("📊 STATISTICAL SUMMARY: DOSE-RESPONSE ANALYSIS")
    print("=" * 70)

    # Overall by SP count
    print("\n--- Mean Score by # of Social Proof Tags (Overall) ---")
    overall = df.groupby("SP Count")["Raw Score"].agg(["mean", "std", "count"])
    overall.index = [f"{i} Tag(s)" for i in overall.index]
    print(overall.round(2))

    # By condition
    print("\n--- Mean Score by # Tags × Condition ---")
    cross = df.pivot_table(values="Raw Score", index="SP Count",
                           columns="Condition", aggfunc="mean")
    cross.index = [f"{i} Tag(s)" for i in cross.index]
    print(cross.round(2))

    # By model
    print("\n--- Mean Score by # Tags × Model ---")
    model_cross = df.pivot_table(values="Raw Score", index="Model Short",
                                 columns="SP Count", aggfunc="mean")
    model_cross.columns = [f"{c} Tag(s)" for c in model_cross.columns]
    model_cross["Δ (3 vs 1)"] = model_cross["3 Tag(s)"] - model_cross["1 Tag(s)"]
    print(model_cross.round(2).sort_values("Δ (3 vs 1)", ascending=False))

    # Trend test (simple correlation)
    from scipy import stats
    corr, p_val = stats.pearsonr(df["SP Count"], df["Raw Score"])
    print(f"\n--- Pearson Correlation (SP Count vs Score) ---")
    print(f"   r = {corr:.3f},  p = {p_val:.4f}")
    if p_val < 0.05:
        print(f"   ✅ Statistically significant (p < 0.05)")
    else:
        print(f"   ⚠️ Not statistically significant (p ≥ 0.05)")

    direction = "SUPPORTS" if corr > 0 and p_val < 0.05 else "DOES NOT SUPPORT" if corr <= 0 else "WEAKLY SUPPORTS (not significant)"
    print(f"\n🔬 HYPOTHESIS: More social proof → higher scores")
    print(f"   Result: {direction}")
    print("=" * 70)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    df = load_data()
    generate_heatmap(df)
    generate_delta_chart(df)
    generate_dose_response(df)
    generate_dose_response_by_model(df)
    print_statistical_summary(df)
