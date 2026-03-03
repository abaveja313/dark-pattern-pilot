"""Tests for dark_patterns.config module."""

import pytest
from dark_patterns.config import (
    MODELS,
    CONDITIONS,
    TASK_MODES,
    COT_MODES,
    ANCHORING_FOLLOWUP,
    REASONING_MODELS,
    DEFAULT_TRIALS,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    OPENROUTER_BASE_URL,
    get_condition_prompt,
    get_detect_prompt,
    get_anchoring_followup,
    get_cot_instruction,
)


class TestModels:
    def test_models_has_all_providers(self):
        providers = {m.split("/")[0] for m in MODELS}
        assert "google" in providers
        assert "anthropic" in providers
        assert "openai" in providers

    def test_models_count(self):
        assert len(MODELS) >= 6

    def test_models_are_strings(self):
        for model in MODELS:
            assert isinstance(model, str)
            assert "/" in model  # provider/model format

    def test_reasoning_models_subset_of_models(self):
        for rm in REASONING_MODELS:
            assert rm in MODELS


class TestConditions:
    def test_conditions_has_both(self):
        assert "AVERAGE_CONSUMER" in CONDITIONS
        assert "CONSUMER_ADVOCATE" in CONDITIONS

    def test_condition_prompts_are_nonempty(self):
        for name, prompt in CONDITIONS.items():
            assert len(prompt) > 50  # substantial prompts

    def test_condition_prompts_mention_score(self):
        for name, prompt in CONDITIONS.items():
            assert "score" in prompt.lower() or "1" in prompt


class TestGetConditionPrompt:
    def test_returns_prompt_for_valid_condition(self):
        prompt = get_condition_prompt("AVERAGE_CONSUMER")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_raises_for_invalid_condition(self):
        with pytest.raises(KeyError):
            get_condition_prompt("NONEXISTENT")

    def test_supports_target_product(self):
        prompt_a = get_condition_prompt("AVERAGE_CONSUMER", target_product="A")
        prompt_b = get_condition_prompt("AVERAGE_CONSUMER", target_product="B")
        assert "Product A" in prompt_a
        assert "Product B" in prompt_b


class TestDetectPrompt:
    def test_detect_prompt_asks_for_tactics(self):
        prompt = get_detect_prompt()
        assert "manipulation" in prompt.lower() or "tactic" in prompt.lower()

    def test_detect_prompt_is_nonempty(self):
        assert len(get_detect_prompt()) > 20


class TestAnchoringFollowup:
    def test_anchoring_mentions_percentage(self):
        followup = get_anchoring_followup()
        assert "89%" in followup or "%" in followup

    def test_anchoring_asks_to_revise(self):
        followup = get_anchoring_followup()
        assert "revise" in followup.lower() or "update" in followup.lower()


class TestCoTInstruction:
    def test_cot_on(self):
        instruction = get_cot_instruction("on")
        assert "step" in instruction.lower()

    def test_cot_off(self):
        instruction = get_cot_instruction("off")
        assert "directly" in instruction.lower() or "brief" in instruction.lower()

    def test_cot_invalid(self):
        with pytest.raises(ValueError):
            get_cot_instruction("invalid")


class TestDefaults:
    def test_default_trials(self):
        assert DEFAULT_TRIALS == 5

    def test_default_temperature(self):
        assert DEFAULT_TEMPERATURE == 1.0

    def test_default_max_tokens(self):
        assert DEFAULT_MAX_TOKENS == 4000

    def test_base_url(self):
        assert "openrouter" in OPENROUTER_BASE_URL


class TestTaskModes:
    def test_valid_modes(self):
        assert "single" in TASK_MODES
        assert "dual" in TASK_MODES


class TestCoTModes:
    def test_valid_cot_modes(self):
        assert "on" in COT_MODES
        assert "off" in COT_MODES
        assert "both" in COT_MODES
