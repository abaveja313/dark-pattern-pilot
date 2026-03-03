"""Tests for dark_patterns.cli module."""

import sys
import pytest
from unittest.mock import patch, MagicMock


class TestCliParsing:
    """Test argument parsing for all subcommands."""

    def test_collect_defaults(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["collect"])
        assert args.command == "collect"
        assert args.trials == 5
        assert args.temperature == 1.0
        assert args.task_mode == "single"
        assert args.cot_mode == "on"
        assert not args.enable_anchoring
        assert not args.enable_counterbalancing
        assert not args.dry_run
        assert not args.verbose

    def test_collect_custom_args(self):
        from dark_patterns.cli import parse_args

        args = parse_args([
            "collect",
            "--trials", "3",
            "--temperature", "0.7",
            "--task-mode", "dual",
            "--cot-mode", "both",
            "--enable-anchoring",
            "--enable-counterbalancing",
            "--dry-run",
            "--verbose",
        ])
        assert args.trials == 3
        assert args.temperature == 0.7
        assert args.task_mode == "dual"
        assert args.cot_mode == "both"
        assert args.enable_anchoring
        assert args.enable_counterbalancing
        assert args.dry_run
        assert args.verbose

    def test_collect_models_filter(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["collect", "--models", "anthropic/claude-opus-4.6", "openai/gpt-5.2"])
        assert args.models == ["anthropic/claude-opus-4.6", "openai/gpt-5.2"]

    def test_collect_resume(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["collect", "--resume", "runs/20260303_100000/"])
        assert args.resume == "runs/20260303_100000/"

    def test_judge_defaults(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["judge", "--input", "runs/latest/"])
        assert args.command == "judge"
        assert args.input == "runs/latest/"
        assert args.judge_model == "anthropic/claude-opus-4.6"
        assert not args.multi_judge
        assert not args.dry_run

    def test_judge_multi(self):
        from dark_patterns.cli import parse_args

        args = parse_args([
            "judge",
            "--input", "runs/latest/",
            "--multi-judge",
            "--judge-model", "openai/gpt-5.2",
        ])
        assert args.multi_judge
        assert args.judge_model == "openai/gpt-5.2"

    def test_analyze_defaults(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["analyze", "--input", "runs/latest/"])
        assert args.command == "analyze"
        assert args.input == "runs/latest/"
        assert not args.latex

    def test_analyze_latex(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["analyze", "--input", "runs/latest/", "--latex"])
        assert args.latex

    def test_plot_defaults(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["plot", "--input", "runs/latest/"])
        assert args.command == "plot"
        assert args.format == "png"

    def test_plot_pdf(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["plot", "--input", "runs/latest/", "--format", "pdf"])
        assert args.format == "pdf"

    def test_run_full_pipeline(self):
        from dark_patterns.cli import parse_args

        args = parse_args([
            "run",
            "--trials", "5",
            "--task-mode", "dual",
            "--enable-anchoring",
        ])
        assert args.command == "run"
        assert args.trials == 5
        assert args.task_mode == "dual"
        assert args.enable_anchoring

    def test_no_command_shows_help(self):
        from dark_patterns.cli import parse_args

        with pytest.raises(SystemExit):
            parse_args([])


class TestCliRouting:
    """Test that subcommands route to correct functions."""

    @patch("dark_patterns.cli.cmd_collect")
    def test_collect_routes(self, mock_collect):
        from dark_patterns.cli import dispatch

        args = MagicMock()
        args.command = "collect"
        dispatch(args)
        mock_collect.assert_called_once_with(args)

    @patch("dark_patterns.cli.cmd_judge")
    def test_judge_routes(self, mock_judge):
        from dark_patterns.cli import dispatch

        args = MagicMock()
        args.command = "judge"
        dispatch(args)
        mock_judge.assert_called_once_with(args)

    @patch("dark_patterns.cli.cmd_analyze")
    def test_analyze_routes(self, mock_analyze):
        from dark_patterns.cli import dispatch

        args = MagicMock()
        args.command = "analyze"
        dispatch(args)
        mock_analyze.assert_called_once_with(args)

    @patch("dark_patterns.cli.cmd_plot")
    def test_plot_routes(self, mock_plot):
        from dark_patterns.cli import dispatch

        args = MagicMock()
        args.command = "plot"
        dispatch(args)
        mock_plot.assert_called_once_with(args)

    @patch("dark_patterns.cli.cmd_run")
    def test_run_routes(self, mock_run):
        from dark_patterns.cli import dispatch

        args = MagicMock()
        args.command = "run"
        dispatch(args)
        mock_run.assert_called_once_with(args)


class TestDryRun:
    """Test dry-run mode shows plan without executing."""

    @patch("dark_patterns.cli.cmd_collect")
    def test_dry_run_flag_passed(self, mock_collect):
        from dark_patterns.cli import parse_args, dispatch

        args = parse_args(["collect", "--dry-run", "--trials", "2"])
        assert args.dry_run


class TestConditionsFilter:
    """Test --conditions flag filters conditions."""

    def test_conditions_default_all(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["collect"])
        assert args.conditions is None  # None means all

    def test_conditions_single(self):
        from dark_patterns.cli import parse_args

        args = parse_args(["collect", "--conditions", "CONSUMER_ADVOCATE"])
        assert args.conditions == ["CONSUMER_ADVOCATE"]
