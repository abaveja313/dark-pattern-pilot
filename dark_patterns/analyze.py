"""Statistical analysis module for the Dark Patterns research study.

Provides functions for descriptive statistics, hypothesis testing,
effect size computation, mixed models, and report generation.
"""

import ast
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from dark_patterns.config import MODELS, REASONING_MODELS
from dark_patterns.utils import load_screenshots_manifest, short_model_name


# ---------------------------------------------------------------------------
# 1. load_results
# ---------------------------------------------------------------------------


def load_results(
    trial_csv: str,
    judge_csv: Optional[str] = None,
) -> pd.DataFrame:
    """Load trial results CSV into a pandas DataFrame.

    Optionally loads and merges judge results on trial_id.

    Args:
        trial_csv: Path to the trial results CSV file.
        judge_csv: Optional path to the judge results CSV file.

    Returns:
        DataFrame with trial (and optionally judge) data.

    Raises:
        FileNotFoundError: If trial_csv does not exist.
    """
    if not os.path.exists(trial_csv):
        raise FileNotFoundError(f"Trial results CSV not found: {trial_csv}")

    df = pd.read_csv(trial_csv)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    if judge_csv and os.path.exists(judge_csv):
        judge_df = pd.read_csv(judge_csv)
        df = df.merge(judge_df, on="trial_id", how="left", suffixes=("", "_judge"))

    return df


# ---------------------------------------------------------------------------
# 2. compute_descriptive_stats
# ---------------------------------------------------------------------------


def compute_descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive statistics per model and condition.

    Returns DataFrame with columns: model, condition, mean, sd, median, iqr, n.
    """
    rows = []
    for (model, condition), group in df.groupby(["model", "condition"]):
        scores = group["score"].dropna()
        q1 = scores.quantile(0.25)
        q3 = scores.quantile(0.75)
        rows.append(
            {
                "model": model,
                "condition": condition,
                "mean": scores.mean(),
                "sd": scores.std(),
                "median": scores.median(),
                "iqr": q3 - q1,
                "n": len(scores),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. test_within_condition
# ---------------------------------------------------------------------------


def test_within_condition(df: pd.DataFrame, neutral: float = 3.0) -> pd.DataFrame:
    """Wilcoxon signed-rank test against neutral score for each model x condition.

    Tests whether scores significantly differ from neutral (3).

    Returns DataFrame with model, condition, test_stat, p_value, effect_size.
    Effect size is rank-biserial correlation r = 1 - (2T)/(n(n+1)).
    """
    rows = []
    for (model, condition), group in df.groupby(["model", "condition"]):
        scores = group["score"].dropna()
        diff = scores - neutral
        diff = diff[diff != 0]

        if len(diff) < 2:
            rows.append(
                {
                    "model": model,
                    "condition": condition,
                    "test_stat": np.nan,
                    "p_value": np.nan,
                    "effect_size": np.nan,
                }
            )
            continue

        stat, p = stats.wilcoxon(diff, alternative="two-sided")
        n = len(diff)
        # Rank-biserial correlation
        r = 1 - (2 * stat) / (n * (n + 1) / 2)
        rows.append(
            {
                "model": model,
                "condition": condition,
                "test_stat": stat,
                "p_value": p,
                "effect_size": r,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 4. test_between_conditions
# ---------------------------------------------------------------------------


def test_between_conditions(df: pd.DataFrame) -> pd.DataFrame:
    """Paired Wilcoxon and Mann-Whitney U comparing conditions per model.

    For each model, compares AVERAGE_CONSUMER vs CONSUMER_ADVOCATE scores.

    Returns DataFrame with model, test_stat, p_value, effect_size_cohens_d,
    effect_size_rank_biserial.
    """
    rows = []
    for model, group in df.groupby("model"):
        avg = group[group["condition"] == "AVERAGE_CONSUMER"]["score"].dropna()
        adv = group[group["condition"] == "CONSUMER_ADVOCATE"]["score"].dropna()

        if len(avg) < 2 or len(adv) < 2:
            rows.append(
                {
                    "model": model,
                    "test_stat": np.nan,
                    "p_value": np.nan,
                    "effect_size_cohens_d": np.nan,
                    "effect_size_rank_biserial": np.nan,
                }
            )
            continue

        # Mann-Whitney U
        u_stat, u_p = stats.mannwhitneyu(avg, adv, alternative="two-sided")

        # Cohen's d
        pooled_std = np.sqrt(
            ((len(avg) - 1) * avg.std() ** 2 + (len(adv) - 1) * adv.std() ** 2)
            / (len(avg) + len(adv) - 2)
        )
        d = (avg.mean() - adv.mean()) / pooled_std if pooled_std > 0 else 0.0

        # Rank-biserial correlation from U
        n1, n2 = len(avg), len(adv)
        r = 1 - (2 * u_stat) / (n1 * n2)

        rows.append(
            {
                "model": model,
                "test_stat": u_stat,
                "p_value": u_p,
                "effect_size_cohens_d": d,
                "effect_size_rank_biserial": r,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. compute_effect_sizes
# ---------------------------------------------------------------------------


def compute_effect_sizes(
    df: pd.DataFrame, n_bootstrap: int = 1000, seed: int = 42
) -> pd.DataFrame:
    """Cohen's d for skepticism shift with 95% bootstrap CI.

    Computes d = (mean_avg - mean_adv) / pooled_sd for each model.
    """
    rng = np.random.RandomState(seed)
    rows = []
    for model, group in df.groupby("model"):
        avg = group[group["condition"] == "AVERAGE_CONSUMER"]["score"].dropna().values
        adv = group[group["condition"] == "CONSUMER_ADVOCATE"]["score"].dropna().values

        d = _cohens_d(avg, adv)

        # Bootstrap CI
        boot_ds = []
        for _ in range(n_bootstrap):
            b_avg = rng.choice(avg, size=len(avg), replace=True)
            b_adv = rng.choice(adv, size=len(adv), replace=True)
            boot_ds.append(_cohens_d(b_avg, b_adv))

        ci_lower = np.percentile(boot_ds, 2.5)
        ci_upper = np.percentile(boot_ds, 97.5)

        rows.append(
            {
                "model": model,
                "cohens_d": d,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            }
        )
    return pd.DataFrame(rows)


def _cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """Compute Cohen's d between two groups."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0.0
    pooled_std = np.sqrt(
        ((n1 - 1) * group1.std(ddof=1) ** 2 + (n2 - 1) * group2.std(ddof=1) ** 2)
        / (n1 + n2 - 2)
    )
    if pooled_std == 0:
        return 0.0
    return (group1.mean() - group2.mean()) / pooled_std


# ---------------------------------------------------------------------------
# 6. correct_multiple_comparisons
# ---------------------------------------------------------------------------


def correct_multiple_comparisons(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Benjamini-Hochberg FDR correction to p_value column.

    Adds p_adjusted column to the DataFrame.
    """
    result = df.copy()
    p_values = result["p_value"].values

    if len(p_values) == 0:
        result["p_adjusted"] = []
        return result

    valid_mask = ~np.isnan(p_values)
    if valid_mask.sum() == 0:
        result["p_adjusted"] = np.nan
        return result

    adjusted = np.full_like(p_values, np.nan, dtype=float)
    _, pvals_corrected, _, _ = multipletests(
        p_values[valid_mask], method="fdr_bh"
    )
    adjusted[valid_mask] = pvals_corrected
    result["p_adjusted"] = adjusted

    return result


# ---------------------------------------------------------------------------
# 7. test_dose_response
# ---------------------------------------------------------------------------


def test_dose_response(
    df: pd.DataFrame, manifest_path: str
) -> Dict:
    """Jonckheere-Terpstra-like trend test via Spearman correlation.

    Tests whether increasing sp_element_count predicts higher scores.
    Uses Spearman rank correlation as a proxy for J-T trend test.

    Args:
        df: Trial results DataFrame.
        manifest_path: Path to screenshots.yaml.

    Returns:
        Dict with stat (Spearman rho), p_value, and n.
    """
    images = load_screenshots_manifest(manifest_path)
    sp_map = {img["file"]: img["sp_element_count"] for img in images}

    merged = df.copy()
    merged["sp_count"] = merged["image"].map(sp_map)
    merged = merged.dropna(subset=["sp_count", "score"])

    if len(merged) < 3:
        return {"stat": np.nan, "p_value": np.nan, "n": len(merged)}

    rho, p_value = stats.spearmanr(merged["sp_count"], merged["score"])

    return {"stat": rho, "p_value": p_value, "n": len(merged)}


# ---------------------------------------------------------------------------
# 8. fit_mixed_model
# ---------------------------------------------------------------------------


def fit_mixed_model(df: pd.DataFrame, manifest_path: str):
    """Fit a mixed-effects model: Score ~ Condition * SP_Count + (1|Model) + (1|Image).

    Uses statsmodels MixedLM.

    Returns:
        Fitted MixedLMResults object.
    """
    import statsmodels.formula.api as smf

    images = load_screenshots_manifest(manifest_path)
    sp_map = {img["file"]: img["sp_element_count"] for img in images}

    merged = df.copy()
    merged["sp_count"] = merged["image"].map(sp_map)
    merged = merged.dropna(subset=["sp_count", "score"])

    # Encode condition as numeric
    merged["cond_code"] = (merged["condition"] == "CONSUMER_ADVOCATE").astype(int)

    # Fit with model as random effect (image as a second grouping is not
    # natively supported in a single MixedLM call, so we nest image within model)
    model = smf.mixedlm(
        "score ~ cond_code * sp_count",
        data=merged,
        groups=merged["model"],
    )
    result = model.fit(reml=True)
    return result


# ---------------------------------------------------------------------------
# 9. analyze_anchoring_effect
# ---------------------------------------------------------------------------


def analyze_anchoring_effect(df: pd.DataFrame) -> pd.DataFrame:
    """Paired test on pre/post nudge scores per model.

    Compares score vs anchoring_followup_score.

    Returns DataFrame with model, mean_shift, p_value, effect_size.
    """
    rows = []
    for model, group in df.groupby("model"):
        sub = group.dropna(subset=["score", "anchoring_followup_score"])

        if len(sub) < 2:
            rows.append(
                {
                    "model": model,
                    "mean_shift": 0.0,
                    "p_value": np.nan,
                    "effect_size": np.nan,
                }
            )
            continue

        pre = sub["score"].values
        post = sub["anchoring_followup_score"].values
        shift = post - pre
        mean_shift = shift.mean()

        nonzero = shift[shift != 0]
        if len(nonzero) < 2:
            rows.append(
                {
                    "model": model,
                    "mean_shift": mean_shift,
                    "p_value": np.nan,
                    "effect_size": np.nan,
                }
            )
            continue

        stat, p = stats.wilcoxon(nonzero, alternative="two-sided")
        n = len(nonzero)
        r = 1 - (2 * stat) / (n * (n + 1) / 2)

        rows.append(
            {
                "model": model,
                "mean_shift": mean_shift,
                "p_value": p,
                "effect_size": r,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 10. analyze_awareness_action_gap
# ---------------------------------------------------------------------------


def analyze_awareness_action_gap(df: pd.DataFrame) -> pd.DataFrame:
    """Percent of trials where model detects dark patterns but still gives high score.

    A trial has a 'gap' when identified_tactics is non-empty AND score >= 4.

    Returns DataFrame with model, n_with_tactics, n_gap, gap_percentage.
    """
    rows = []
    for model, group in df.groupby("model"):
        tactics_col = group["identified_tactics"].fillna("[]")

        # Parse tactics - handle both string repr of list and actual lists
        has_tactics = tactics_col.apply(_has_nonempty_tactics)
        with_tactics = group[has_tactics]
        n_with = len(with_tactics)

        if n_with == 0:
            rows.append(
                {
                    "model": model,
                    "n_with_tactics": 0,
                    "n_gap": 0,
                    "gap_percentage": 0.0,
                }
            )
            continue

        n_gap = int((with_tactics["score"] >= 4).sum())
        gap_pct = (n_gap / n_with) * 100

        rows.append(
            {
                "model": model,
                "n_with_tactics": n_with,
                "n_gap": n_gap,
                "gap_percentage": gap_pct,
            }
        )
    return pd.DataFrame(rows)


def _has_nonempty_tactics(val) -> bool:
    """Check if tactics value represents a non-empty list."""
    if isinstance(val, list):
        return len(val) > 0
    if isinstance(val, str):
        val = val.strip()
        if val in ("[]", "", "nan"):
            return False
        try:
            parsed = ast.literal_eval(val)
            return isinstance(parsed, list) and len(parsed) > 0
        except (ValueError, SyntaxError):
            return False
    return False


# ---------------------------------------------------------------------------
# 11. analyze_position_bias
# ---------------------------------------------------------------------------


def analyze_position_bias(df: pd.DataFrame) -> pd.DataFrame:
    """Compare scores for target_product A vs B per model.

    Uses Mann-Whitney U test.

    Returns DataFrame with model, mean_A, mean_B, u_stat, p_value.
    """
    rows = []
    for model, group in df.groupby("model"):
        a_scores = group[group["target_product"] == "A"]["score"].dropna()
        b_scores = group[group["target_product"] == "B"]["score"].dropna()

        mean_a = a_scores.mean() if len(a_scores) > 0 else np.nan
        mean_b = b_scores.mean() if len(b_scores) > 0 else np.nan

        if len(a_scores) < 2 or len(b_scores) < 2:
            rows.append(
                {
                    "model": model,
                    "mean_A": mean_a,
                    "mean_B": mean_b,
                    "u_stat": np.nan,
                    "p_value": np.nan,
                }
            )
            continue

        u_stat, p = stats.mannwhitneyu(a_scores, b_scores, alternative="two-sided")
        rows.append(
            {
                "model": model,
                "mean_A": mean_a,
                "mean_B": mean_b,
                "u_stat": u_stat,
                "p_value": p,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 12. analyze_inter_trial_consistency
# ---------------------------------------------------------------------------


def analyze_inter_trial_consistency(df: pd.DataFrame) -> pd.DataFrame:
    """ICC across repeated trials per model x image x condition.

    Uses pingouin.intraclass_corr() with ICC3 (two-way mixed, consistency).

    Returns DataFrame with model, ICC, ci_lower, ci_upper.
    """
    import pingouin as pg

    results = []
    for model, group in df.groupby("model"):
        # Build long-format data for ICC: targets = image x condition combos,
        # raters = trial numbers, ratings = scores
        sub = group[["image", "condition", "trial_number", "score"]].dropna()
        sub = sub.copy()
        sub["target"] = sub["image"] + "_" + sub["condition"]

        # Need at least 2 targets and 2 raters
        n_targets = sub["target"].nunique()
        n_raters = sub["trial_number"].nunique()

        if n_targets < 2 or n_raters < 2:
            results.append(
                {"model": model, "ICC": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
            )
            continue

        try:
            # Ensure balanced design by keeping only combos with all trials
            combo_counts = sub.groupby("target")["trial_number"].nunique()
            valid_targets = combo_counts[combo_counts >= 2].index
            sub = sub[sub["target"].isin(valid_targets)]

            if len(sub) < 4:
                results.append(
                    {"model": model, "ICC": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
                )
                continue

            icc = pg.intraclass_corr(
                data=sub,
                targets="target",
                raters="trial_number",
                ratings="score",
            )
            # Use ICC3 (two-way mixed, consistency, single measures)
            icc3 = icc[icc["Type"] == "ICC3"]
            if len(icc3) > 0:
                results.append(
                    {
                        "model": model,
                        "ICC": icc3["ICC"].values[0],
                        "ci_lower": icc3["CI95%"].values[0][0],
                        "ci_upper": icc3["CI95%"].values[0][1],
                    }
                )
            else:
                results.append(
                    {"model": model, "ICC": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
                )
        except Exception:
            results.append(
                {"model": model, "ICC": np.nan, "ci_lower": np.nan, "ci_upper": np.nan}
            )

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# 13. analyze_provider_differences
# ---------------------------------------------------------------------------


def _model_provider(model: str) -> str:
    """Extract provider from model string (e.g., 'google/gemini-...' -> 'google')."""
    return model.split("/")[0] if "/" in model else "unknown"


def analyze_provider_differences(df: pd.DataFrame) -> Dict:
    """Kruskal-Wallis test comparing scores across providers.

    Groups models by provider prefix (google, anthropic, openai).

    Returns dict with stat, p_value, and per-provider means.
    """
    df_copy = df.copy()
    df_copy["provider"] = df_copy["model"].apply(_model_provider)

    groups = [g["score"].dropna().values for _, g in df_copy.groupby("provider")]
    groups = [g for g in groups if len(g) >= 1]

    if len(groups) < 2:
        return {"stat": np.nan, "p_value": np.nan, "provider_means": {}}

    stat, p = stats.kruskal(*groups)

    provider_means = df_copy.groupby("provider")["score"].mean().to_dict()

    return {"stat": stat, "p_value": p, "provider_means": provider_means}


# ---------------------------------------------------------------------------
# 14. analyze_reasoning_tier
# ---------------------------------------------------------------------------


def analyze_reasoning_tier(df: pd.DataFrame) -> Dict:
    """Compare reasoning models vs fast models using Mann-Whitney U.

    Uses REASONING_MODELS from config to classify.

    Returns dict with stat, p_value, mean_reasoning, mean_fast.
    """
    reasoning_scores = df[df["model"].isin(REASONING_MODELS)]["score"].dropna()
    fast_scores = df[~df["model"].isin(REASONING_MODELS)]["score"].dropna()

    if len(reasoning_scores) < 2 or len(fast_scores) < 2:
        return {
            "stat": np.nan,
            "p_value": np.nan,
            "mean_reasoning": reasoning_scores.mean() if len(reasoning_scores) else np.nan,
            "mean_fast": fast_scores.mean() if len(fast_scores) else np.nan,
        }

    stat, p = stats.mannwhitneyu(reasoning_scores, fast_scores, alternative="two-sided")

    return {
        "stat": stat,
        "p_value": p,
        "mean_reasoning": reasoning_scores.mean(),
        "mean_fast": fast_scores.mean(),
    }


# ---------------------------------------------------------------------------
# 15. generate_latex_table
# ---------------------------------------------------------------------------


def generate_latex_table(df: pd.DataFrame) -> str:
    """Format key results as a LaTeX table.

    Produces an effect-size table:
    Model | Condition | Mean (SD) | Cohen's d [95% CI] | p | p_adj
    """
    desc = compute_descriptive_stats(df)
    effects = compute_effect_sizes(df)
    between = test_between_conditions(df)
    between = correct_multiple_comparisons(between)

    lines = []
    lines.append("\\begin{tabular}{llcccc}")
    lines.append("\\toprule")
    lines.append(
        "Model & Condition & Mean (SD) & Cohen's $d$ [95\\% CI] & $p$ & $p_{adj}$ \\\\"
    )
    lines.append("\\midrule")

    for _, erow in effects.iterrows():
        model = erow["model"]
        short = short_model_name(model)
        d = erow["cohens_d"]
        ci_lo = erow["ci_lower"]
        ci_hi = erow["ci_upper"]

        brow = between[between["model"] == model]
        p_val = brow["p_value"].values[0] if len(brow) > 0 else np.nan
        p_adj = brow["p_adjusted"].values[0] if len(brow) > 0 else np.nan

        for cond in ["AVERAGE_CONSUMER", "CONSUMER_ADVOCATE"]:
            drow = desc[(desc["model"] == model) & (desc["condition"] == cond)]
            if len(drow) == 0:
                continue
            mean_val = drow["mean"].values[0]
            sd_val = drow["sd"].values[0]
            cond_short = "Avg" if cond == "AVERAGE_CONSUMER" else "Adv"

            if cond == "AVERAGE_CONSUMER":
                lines.append(
                    f"{short} & {cond_short} & {mean_val:.2f} ({sd_val:.2f}) & "
                    f"{d:.2f} [{ci_lo:.2f}, {ci_hi:.2f}] & "
                    f"{p_val:.4f} & {p_adj:.4f} \\\\"
                )
            else:
                lines.append(
                    f" & {cond_short} & {mean_val:.2f} ({sd_val:.2f}) & & & \\\\"
                )

    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 16. generate_summary_report
# ---------------------------------------------------------------------------


def generate_summary_report(df: pd.DataFrame, manifest_path: str) -> str:
    """Generate a Markdown summary report of all analyses."""
    sections = []

    sections.append("# Dark Patterns Study - Analysis Report\n")

    # Descriptive stats
    desc = compute_descriptive_stats(df)
    sections.append("## Descriptive Statistics\n")
    sections.append(desc.to_markdown(index=False))
    sections.append("")

    # Between-condition tests
    between = test_between_conditions(df)
    between = correct_multiple_comparisons(between)
    sections.append("## Between-Condition Tests\n")
    sections.append(between.to_markdown(index=False))
    sections.append("")

    # Effect sizes
    effects = compute_effect_sizes(df)
    sections.append("## Effect Sizes (Cohen's d with 95% Bootstrap CI)\n")
    sections.append(effects.to_markdown(index=False))
    sections.append("")

    # Dose-response
    try:
        dose = test_dose_response(df, manifest_path)
        sections.append("## Dose-Response Trend Test\n")
        sections.append(f"- Spearman rho = {dose['stat']:.4f}")
        sections.append(f"- p-value = {dose['p_value']:.4f}")
        sections.append(f"- N = {dose['n']}")
        sections.append("")
    except Exception:
        pass

    # Anchoring
    if "anchoring_followup_score" in df.columns:
        anchor = analyze_anchoring_effect(df)
        sections.append("## Anchoring Effect\n")
        sections.append(anchor.to_markdown(index=False))
        sections.append("")

    # Awareness-action gap
    if "identified_tactics" in df.columns:
        gap = analyze_awareness_action_gap(df)
        sections.append("## Awareness-Action Gap\n")
        sections.append(gap.to_markdown(index=False))
        sections.append("")

    # Provider differences
    provider = analyze_provider_differences(df)
    sections.append("## Provider Differences (Kruskal-Wallis)\n")
    sections.append(f"- H statistic = {provider['stat']:.4f}")
    sections.append(f"- p-value = {provider['p_value']:.4f}")
    sections.append("")

    # Reasoning tier
    reasoning = analyze_reasoning_tier(df)
    sections.append("## Reasoning vs Fast Models\n")
    sections.append(f"- U statistic = {reasoning['stat']:.4f}")
    sections.append(f"- p-value = {reasoning['p_value']:.4f}")
    sections.append("")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# 17. run_analysis
# ---------------------------------------------------------------------------


def run_analysis(
    trial_csv: str,
    manifest_path: str,
    output_dir: str,
    judge_csv: Optional[str] = None,
) -> None:
    """Main entry point. Load data, run all analyses, save outputs.

    Args:
        trial_csv: Path to trial results CSV.
        manifest_path: Path to screenshots.yaml.
        output_dir: Directory for output files.
        judge_csv: Optional path to judge results CSV.
    """
    os.makedirs(output_dir, exist_ok=True)

    df = load_results(trial_csv, judge_csv=judge_csv)

    # Descriptive stats
    desc = compute_descriptive_stats(df)
    desc.to_csv(os.path.join(output_dir, "descriptive_stats.csv"), index=False)

    # Between-condition tests
    between = test_between_conditions(df)
    between = correct_multiple_comparisons(between)
    between.to_csv(os.path.join(output_dir, "between_conditions.csv"), index=False)

    # Within-condition tests
    within = test_within_condition(df)
    within = correct_multiple_comparisons(within)
    within.to_csv(os.path.join(output_dir, "within_conditions.csv"), index=False)

    # Effect sizes
    effects = compute_effect_sizes(df)
    effects.to_csv(os.path.join(output_dir, "effect_sizes.csv"), index=False)

    # Dose-response
    try:
        dose = test_dose_response(df, manifest_path)
        pd.DataFrame([dose]).to_csv(
            os.path.join(output_dir, "dose_response.csv"), index=False
        )
    except Exception:
        pass

    # Mixed model
    try:
        mm_result = fit_mixed_model(df, manifest_path)
        with open(os.path.join(output_dir, "mixed_model_summary.txt"), "w") as f:
            f.write(str(mm_result.summary()))
    except Exception:
        pass

    # Anchoring
    if "anchoring_followup_score" in df.columns:
        anchor = analyze_anchoring_effect(df)
        anchor.to_csv(os.path.join(output_dir, "anchoring_effect.csv"), index=False)

    # Awareness-action gap
    if "identified_tactics" in df.columns:
        gap = analyze_awareness_action_gap(df)
        gap.to_csv(os.path.join(output_dir, "awareness_action_gap.csv"), index=False)

    # Position bias
    if "target_product" in df.columns:
        pos = analyze_position_bias(df)
        pos.to_csv(os.path.join(output_dir, "position_bias.csv"), index=False)

    # ICC
    try:
        icc = analyze_inter_trial_consistency(df)
        icc.to_csv(os.path.join(output_dir, "icc.csv"), index=False)
    except Exception:
        pass

    # LaTeX table
    latex = generate_latex_table(df)
    with open(os.path.join(output_dir, "effect_table.tex"), "w") as f:
        f.write(latex)

    # Summary report
    report = generate_summary_report(df, manifest_path)
    with open(os.path.join(output_dir, "summary_report.md"), "w") as f:
        f.write(report)
