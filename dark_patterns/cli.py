"""CLI entry point for the Dark Patterns research study."""

import argparse
import sys

from dark_patterns.config import (
    MODELS,
    DEFAULT_TRIALS,
    DEFAULT_TEMPERATURE,
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
    p_collect.add_argument("--output-dir", default=None, help="Output directory (default: runs/TIMESTAMP/)")
    p_collect.add_argument("--resume", default=None, help="Resume from run directory")
    add_common_args(p_collect)

    # --- judge ---
    p_judge = subparsers.add_parser("judge", help="Run LLM judge pipeline on collected results")
    p_judge.add_argument("--input", required=True, help="Input run directory")
    p_judge.add_argument("--judge-model", default="anthropic/claude-opus-4.6", help="Judge model")
    p_judge.add_argument("--multi-judge", action="store_true", help="Use multiple judges and compute agreement")
    add_common_args(p_judge)

    # --- analyze ---
    p_analyze = subparsers.add_parser("analyze", help="Run statistical analysis")
    p_analyze.add_argument("--input", required=True, help="Input run directory")
    p_analyze.add_argument("--latex", action="store_true", help="Output LaTeX tables")
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
    p_run.add_argument("--output-dir", default=None, help="Output directory")
    p_run.add_argument("--judge-model", default="anthropic/claude-opus-4.6", help="Judge model")
    p_run.add_argument("--multi-judge", action="store_true", help="Use multiple judges")
    p_run.add_argument("--format", choices=["png", "pdf"], default="png", help="Plot format")
    p_run.add_argument("--latex", action="store_true", help="Output LaTeX tables")
    add_common_args(p_run)

    args = parser.parse_args(argv)
    return args


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
    from dark_patterns.collect import run_experiment

    logger = setup_logging(verbose=getattr(args, "verbose", False))

    models = args.models or MODELS
    conditions = args.conditions

    if args.dry_run:
        from dark_patterns.collect import generate_trial_plan, load_screenshots_manifest_for_collect
        images = load_screenshots_manifest_for_collect(args.screenshots_dir)
        plan = generate_trial_plan(
            models=models,
            images=images,
            conditions=conditions,
            trials=args.trials,
            task_mode=args.task_mode,
            cot_mode=args.cot_mode,
            enable_anchoring=args.enable_anchoring,
            enable_counterbalancing=args.enable_counterbalancing,
        )
        print(f"DRY RUN: Would execute {len(plan)} API calls")
        print(f"  Models: {models}")
        print(f"  Images: {[img['file'] for img in images]}")
        print(f"  Trials per condition: {args.trials}")
        print(f"  Task mode: {args.task_mode}")
        print(f"  CoT mode: {args.cot_mode}")
        print(f"  Anchoring: {args.enable_anchoring}")
        print(f"  Counterbalancing: {args.enable_counterbalancing}")
        return

    run_experiment(
        models=models,
        conditions=conditions,
        trials=args.trials,
        temperature=args.temperature,
        task_mode=args.task_mode,
        cot_mode=args.cot_mode,
        enable_anchoring=args.enable_anchoring,
        enable_counterbalancing=args.enable_counterbalancing,
        screenshots_dir=args.screenshots_dir,
        output_dir=args.output_dir,
        resume_dir=args.resume,
    )


def cmd_judge(args):
    """Handle the 'judge' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.judge import run_judge_pipeline, run_multi_judge

    logger = setup_logging(verbose=getattr(args, "verbose", False))

    if args.dry_run:
        print(f"DRY RUN: Would run judge pipeline on {args.input}")
        print(f"  Judge model: {args.judge_model}")
        print(f"  Multi-judge: {args.multi_judge}")
        return

    if args.multi_judge:
        run_multi_judge(input_dir=args.input)
    else:
        run_judge_pipeline(
            input_dir=args.input,
            judge_model=args.judge_model,
        )


def cmd_analyze(args):
    """Handle the 'analyze' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.analyze import run_analysis

    logger = setup_logging(verbose=getattr(args, "verbose", False))
    run_analysis(input_dir=args.input, latex=getattr(args, "latex", False))


def cmd_plot(args):
    """Handle the 'plot' subcommand."""
    from dark_patterns.utils import setup_logging
    from dark_patterns.plot import plot_all

    logger = setup_logging(verbose=getattr(args, "verbose", False))
    plot_all(input_dir=args.input, fmt=args.format)


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
        dry_run=args.dry_run,
    )
    cmd_collect(collect_args)

    # Step 2: Judge
    # Use the latest run directory
    import os
    import glob as glob_module

    runs = sorted(glob_module.glob("runs/*/"))
    if not runs:
        logger.error("No run directories found after collection")
        return
    latest_run = runs[-1]

    judge_args = argparse.Namespace(
        command="judge",
        input=latest_run,
        judge_model=args.judge_model,
        multi_judge=args.multi_judge,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    cmd_judge(judge_args)

    # Step 3: Analyze
    analyze_args = argparse.Namespace(
        command="analyze",
        input=latest_run,
        latex=args.latex,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    cmd_analyze(analyze_args)

    # Step 4: Plot
    plot_args = argparse.Namespace(
        command="plot",
        input=latest_run,
        format=args.format,
        verbose=args.verbose,
        dry_run=args.dry_run,
    )
    cmd_plot(plot_args)

    logger.info(f"Full pipeline complete. Results in {latest_run}")


def main():
    """Main entry point."""
    args = parse_args()
    dispatch(args)
