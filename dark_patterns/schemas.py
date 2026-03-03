"""Data validation schemas for the Dark Patterns research study."""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


def _validate_score(score: Optional[int], field_name: str = "score") -> None:
    """Validate a score is None or in 1-5 range."""
    if score is not None:
        if not isinstance(score, int):
            raise TypeError(f"{field_name} must be int or None, got {type(score).__name__}")
        if not (1 <= score <= 5):
            raise ValueError(f"{field_name} must be 1-5, got {score}")


def _validate_dimension(value: int, field_name: str) -> None:
    """Validate a judge dimension score is in 1-5 range."""
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int, got {type(value).__name__}")
    if not (1 <= value <= 5):
        raise ValueError(f"{field_name} must be 1-5, got {value}")


@dataclass
class TrialResult:
    """Result from a single experimental trial."""

    trial_id: str
    model: str
    image: str
    condition: str
    task_mode: str
    cot_mode: str
    target_product: str
    trial_number: int
    temperature: float
    score: Optional[int]
    raw_response: str
    reasoning: Optional[str]
    identified_tactics: List[str]
    parse_method: str  # "json", "regex", or "none"
    anchoring_followup_score: Optional[int]
    timestamp: str

    def __post_init__(self):
        _validate_score(self.score, "score")
        _validate_score(self.anchoring_followup_score, "anchoring_followup_score")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JudgeResult:
    """Result from an LLM judge evaluation of a reasoning trace."""

    trial_id: str
    judge_model: str
    detection_accuracy: int
    specificity: int
    consumer_harm_reasoning: int
    evidence_grounding: int
    logical_coherence: int
    score_reasoning_alignment: int
    overall_quality: int
    notable_observations: str
    timestamp: str

    def __post_init__(self):
        for dim in [
            "detection_accuracy",
            "specificity",
            "consumer_harm_reasoning",
            "evidence_grounding",
            "logical_coherence",
            "score_reasoning_alignment",
            "overall_quality",
        ]:
            _validate_dimension(getattr(self, dim), dim)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RunManifest:
    """Metadata for a single experiment run."""

    run_id: str
    git_sha: str
    models: List[str]
    conditions: List[str]
    images: List[str]
    trials: int
    temperature: float
    task_mode: str
    cot_mode: str
    enable_anchoring: bool
    enable_counterbalancing: bool
    total_api_calls: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_trial_result(data: Dict[str, Any]) -> TrialResult:
    """Validate and create a TrialResult from a dict.

    Raises:
        KeyError: If required fields are missing.
        ValueError/TypeError: If field values are invalid.
    """
    return TrialResult(**data)


def validate_judge_result(data: Dict[str, Any]) -> JudgeResult:
    """Validate and create a JudgeResult from a dict.

    Raises:
        KeyError: If required fields are missing.
        ValueError/TypeError: If field values are invalid.
    """
    return JudgeResult(**data)
