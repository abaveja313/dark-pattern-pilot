"""CLI entry point for the Dark Patterns research study."""

import argparse
import glob as glob_module
import os
import sys

from dotenv import load_dotenv

from dark_patterns.config import (
    MODELS,
    CONDITIONS,
    DEFAULT_TRIALS,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    TASK_MODES,
    COT_MODES,
)


def parse_args(argv=None):
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed argparse.Namespace.
    """
    parser = argparse.ArgumentParser(
        prog="dark_patterns",
        description="Dark Patterns Research Study - Publication-Ready Experiment Framework",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Common arguments ---
    def add_common_args(p):
        p.add_argument("--verbose", action="store_true", help="Enable debug logging")
        p.add_argument("--dry-run", action="store_true", help="Show plan without executing")

    # --- collect ---
    p_collect = subparsers.add_parser("collect", help="Run experiment (collect data)")
    p_collect.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="Number of trials per condition")
    p_collect.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Sampling temperature")
    p_collect.add_argument("--models", nargs="+", default=None, help="Models to test (default: all)")
    p_collect.add_argument("--conditions", nargs="+", default=None, help="Conditions to test (default: all)")
    p_collect.add_argument("--task-mode", choices=TASK_MODES, default="single", help="single or dual task paradigm")
    p_collect.add_argument("--cot-mode", choices=COT_MODES, default="on", help="Chain-of-thought mode")
    p_collect.add_argument("--enable-anchoring", action="store_true", help="Enable multi-turn anchoring probe")
    p_collect.add_argument("--enable-counterbalancing", action="store_true", help="Enable Product A/B counterbalancing")
    p_collect.add_argument("--screenshots-dir", default="data/screenshots/v4", help="Screenshots directory")
    p_collect.add_argument("--output-dir", default="runs", help="Base output directory for runs")
    p_collect.add_argument("--resume", default=None, help="Resume from run directory")
    add_common_args(p_collect)

    # --- judge ---
    p_judge = subparsers.add_parser("judge", help="Run LLM judge pipeline on collected results")
    p_judge.add_argument("--input", required=True, help="Input run directory")
    p_judge.add_argument("--judge-model", default="anthropic/claude-opus-4.6", help="Judge model")
    p_judge.add_argument("--multi-judge", action="store_true", help="Use multiple judges and compute agreement")
    p_judge.add_argument("--manifest", default="screenshots.yaml", help="Screenshots manifest path")
    add_common_args(p_judge)

    # --- analyze ---
    p_analyze = subparsers.add_parser("analyze", help="Run statistical analysis")
    p_analyze.add_argument("--input", required=True, help="Input run directory")
    p_analyze.add_argument("--latex", action="store_true", help="Output LaTeX tables")
    p_analyze.add_argument("--manifest", default="screenshots.yaml", help="Screenshots manifest path")
    add_common_args(p_analyze)

    # --- plot ---
    p_plot = subparsers.add_parser("plot", help="Generate publication figures")
    p_plot.add_argument("--input", required=True, help="Input run directory")
    p_plot.add_argument("--format", choices=["png", "pdf"], default="png", help="Output format")
    add_common_args(p_plot)

    # --- run (full pipeline) ---
    p_run = subparsers.add_parser("run", help="Full pipeline: collect + judge + analyze + plot")
    p_run.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="Number of trials")
    p_run.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Sampling temperature")
    p_run.add_argument("--models", nargs="+", default=None, help="Models to test")
    p_run.add_argument("--conditions", nargs="+", default=None, help="Conditions to test")
    p_run.add_argument("--task-mode", choices=TASK_MODES, default="single", help="Task mode")
    p_run.add_argument("--cot-mode", choices=COT_MODES, default="on", help="CoT mode")
    p_run.add_argument("--enable-anchoring", action="store_true", help="Enable anchoring probe")
    p_run.add_argument("--enable-counterbalancing", action="store_true", help="Enable counterbalancing")
    p_run.add_argument("--screenshots-dir", default="data/screenshots/v4", help="Screenshots directory")
    p_run.add_argument("--output-dir", default="runs", help="Base output directory")
    p_run.add_argument("--judge-model", default="anthropic/claude-opus-4.6", help="Judge model")
    p_run.add_argument("--multi-judge", action="store_true", help="Use multiple judges")
    p_run.add_argument("--manifest", default="screenshots.yaml", help="Screenshots manifest path")
    p_run.add_argument("--format", choices=["png", "pdf"], default="png", help="Plot format")
    p_run.add_argument("--latex", action="store_true", help="Output LaTeX tables")
    add_common_args(p_run)

    args = parser.parse_args(argv)
    return args


def _scan_screenshots(screenshots_dir):
    """Scan a directory for image files and return sorted list of paths."""
    images = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        images.extend(glob_module.glob(os.path.join(screenshots_dir, ext)))
    return sorted(images)


def dispatch(args):
    """Route to the appropriate subcommand handler."""
    handlers = {
        "collect": cmd_collect,
        "judge": cmd_judge,
        "analyze": cmd_analyze,
        "plot": cmd_plot,
        "run": cmd_run,
    }
    handler = handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


def cmd_collect(args):
    """Handle the 'collect' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.collect import run_experiment, generate_trial_plan

    logger = setup_logging(verbose=getattr(args, "verbose", False))

    models = args.models or MODELS
    conditions = args.conditions or list(CONDITIONS.keys())
    images = _scan_screenshots(args.screenshots_dir)

    if not images:
        logger.error(f"No images found in {args.screenshots_dir}")
        sys.exit(1)

    if args.dry_run:
        plan = generate_trial_plan(
            models=models,
            images=[os.path.basename(i) for i in images],
            conditions=conditions,
            trials=args.trials,
            task_mode=args.task_mode,
            cot_mode=args.cot_mode,
            enable_anchoring=args.enable_anchoring,
            enable_counterbalancing=args.enable_counterbalancing,
        )
        print(f"DRY RUN: Would execute {len(plan)} trials")
        print(f"  Models: {models}")
        print(f"  Images: {[os.path.basename(i) for i in images]}")
        print(f"  Conditions: {conditions}")
        print(f"  Trials per condition: {args.trials}")
        print(f"  Task mode: {args.task_mode}")
        print(f"  CoT mode: {args.cot_mode}")
        print(f"  Anchoring: {args.enable_anchoring}")
        print(f"  Counterbalancing: {args.enable_counterbalancing}")
        return None

    results = run_experiment(
        models=models,
        images=images,
        conditions=conditions,
        trials=args.trials,
        temperature=args.temperature,
        task_mode=args.task_mode,
        cot_mode=args.cot_mode,
        enable_anchoring=args.enable_anchoring,
        enable_counterbalancing=args.enable_counterbalancing,
        max_tokens=DEFAULT_MAX_TOKENS,
        base_dir=args.output_dir,
        resume_run_id=args.resume,
    )
    return results


def cmd_judge(args):
    """Handle the 'judge' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.judge import run_judge_pipeline, run_multi_judge

    logger = setup_logging(verbose=getattr(args, "verbose", False))
    manifest_path = getattr(args, "manifest", "screenshots.yaml")

    if args.dry_run:
        print(f"DRY RUN: Would run judge pipeline on {args.input}")
        print(f"  Judge model: {args.judge_model}")
        print(f"  Multi-judge: {args.multi_judge}")
        return

    if args.multi_judge:
        run_multi_judge(input_dir=args.input, manifest_path=manifest_path, output_dir=args.input)
    else:
        run_judge_pipeline(
            input_dir=args.input,
            judge_model=args.judge_model,
            manifest_path=manifest_path,
            output_dir=args.input,
        )


def cmd_analyze(args):
    """Handle the 'analyze' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.analyze import run_analysis

    logger = setup_logging(verbose=getattr(args, "verbose", False))
    manifest_path = getattr(args, "manifest", "screenshots.yaml")

    trial_csv = os.path.join(args.input, "results.csv")
    judge_csv = os.path.join(args.input, "judge_results.csv")
    output_dir = os.path.join(args.input, "analysis")

    run_analysis(
        trial_csv=trial_csv,
        manifest_path=manifest_path,
        output_dir=output_dir,
        judge_csv=judge_csv if os.path.exists(judge_csv) else None,
    )
    logger.info(f"Analysis complete. Results in {output_dir}")


def cmd_plot(args):
    """Handle the 'plot' subcommand."""
    import pandas as pd
    from dark_patterns.utils import setup_logging
    from dark_patterns.plot import plot_all

    logger = setup_logging(verbose=getattr(args, "verbose", False))

    trial_csv = os.path.join(args.input, "results.csv")
    if not os.path.exists(trial_csv):
        logger.error(f"No results.csv found in {args.input}")
        sys.exit(1)

    df = pd.read_csv(trial_csv)
    df["score"] = pd.to_numeric(df["score"], errors="coerce")

    output_dir = os.path.join(args.input, "figures")

    # Load optional data
    effect_sizes_df = None
    anchoring_df = None
    awareness_gap_df = None
    judge_df = None

    analysis_dir = os.path.join(args.input, "analysis")
    if os.path.isdir(analysis_dir):
        es_path = os.path.join(analysis_dir, "effect_sizes.csv")
        if os.path.exists(es_path):
            effect_sizes_df = pd.read_csv(es_path)

        anchor_path = os.path.join(analysis_dir, "anchoring_effect.csv")
        if os.path.exists(anchor_path):
            anchoring_df = pd.read_csv(anchor_path)

        gap_path = os.path.join(analysis_dir, "awareness_action_gap.csv")
        if os.path.exists(gap_path):
            awareness_gap_df = pd.read_csv(gap_path)

    judge_csv = os.path.join(args.input, "judge_results.csv")
    if os.path.exists(judge_csv):
        judge_df = pd.read_csv(judge_csv)

    plot_all(
        scores_df=df,
        output_dir=output_dir,
        fmt=args.format,
        effect_sizes_df=effect_sizes_df,
        anchoring_df=anchoring_df,
        awareness_gap_df=awareness_gap_df,
        judge_df=judge_df,
    )
    logger.info(f"Figures saved to {output_dir}")


def cmd_run(args):
    """Handle the 'run' subcommand (full pipeline)."""
    from dark_patterns.utils import setup_logging

    logger = setup_logging(verbose=getattr(args, "verbose", False))

    # Step 1: Collect
    collect_args = argparse.Namespace(
        command="collect",
        trials=args.trials,
        temperature=args.temperature,
        models=args.models,
        conditions=args.conditions,
        task_mode=args.task_mode,
        cot_mode=args.cot_mode,
        enable_anchoring=args.enable_anchoring,
        enable_counterbalancing=args.enable_counterbalancing,
        screenshots_dir=args.screenshots_dir,
        output_dir=args.output_dir,
        resume=None,
        verbose=args.verbose,
        dry_run=getattr(args, "dry_run", False),
    )
    cmd_collect(collect_args)

    # Find the latest run directory
    base = args.output_dir
    run_dirs = sorted(
        [d for d in glob_module.glob(os.path.join(base, "*/")) if os.path.isdir(d)]
    )
    if not run_dirs:
        logger.error(f"No run directories found in {base}")
        return
    latest_run = run_dirs[-1]
    logger.info(f"Using run directory: {latest_run}")

    # Step 2: Judge
    judge_args = argparse.Namespace(
        command="judge",
        input=latest_run,
        judge_model=args.judge_model,
        multi_judge=args.multi_judge,
        manifest=args.manifest,
        verbose=args.verbose,
        dry_run=getattr(args, "dry_run", False),
    )
    cmd_judge(judge_args)

    # Step 3: Analyze
    analyze_args = argparse.Namespace(
        command="analyze",
        input=latest_run,
        latex=args.latex,
        manifest=args.manifest,
        verbose=args.verbose,
        dry_run=getattr(args, "dry_run", False),
    )
    cmd_analyze(analyze_args)

    # Step 4: Plot
    plot_args = argparse.Namespace(
        command="plot",
        input=latest_run,
        format=args.format,
        verbose=args.verbose,
        dry_run=getattr(args, "dry_run", False),
    )
    cmd_plot(plot_args)

    logger.info(f"Full pipeline complete. Results in {latest_run}")


def main():
    """Main entry point."""
    load_dotenv()
    args = parse_args()
    dispatch(args)
