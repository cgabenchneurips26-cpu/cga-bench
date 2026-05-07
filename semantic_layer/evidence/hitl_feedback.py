from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict


class FeedbackAction(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    MODIFY = "modify"


class ClinicalFeedback(TypedDict):
    episode_id: str
    action_id: str
    feedback_action: str
    rationale: str
    suggested_alternative: str | None
    reviewer_id: str
    timestamp_minutes: float


@dataclass
class HITLFeedbackConfig:
    require_rationale: bool = True
    allow_modify: bool = True
    max_feedback_per_episode: int = 10

    @classmethod
    def default(cls) -> HITLFeedbackConfig:
        return cls()


def validate_feedback(feedback: ClinicalFeedback, config: HITLFeedbackConfig) -> list[str]:
    """Validate a feedback entry."""
    errors: list[str] = []
    raw_feedback: dict[str, object] = dict(feedback)
    required = {
        "episode_id",
        "action_id",
        "feedback_action",
        "rationale",
        "suggested_alternative",
        "reviewer_id",
        "timestamp_minutes",
    }
    missing = required - set(raw_feedback.keys())
    if missing:
        errors.append(f"missing_fields:{','.join(sorted(missing))}")
        return errors

    for key in ("episode_id", "action_id", "reviewer_id"):
        value = raw_feedback.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}:empty_or_invalid")

    action = raw_feedback.get("feedback_action")
    valid_actions = {item.value for item in FeedbackAction}
    if not isinstance(action, str) or action not in valid_actions:
        errors.append("feedback_action:invalid")

    rationale = raw_feedback.get("rationale")
    if config.require_rationale and (not isinstance(rationale, str) or not rationale.strip()):
        errors.append("rationale:required")
    elif not isinstance(rationale, str):
        errors.append("rationale:invalid")

    suggested = raw_feedback.get("suggested_alternative")
    if suggested is not None and (not isinstance(suggested, str) or not suggested.strip()):
        errors.append("suggested_alternative:invalid")

    if action == FeedbackAction.MODIFY.value:
        if not config.allow_modify:
            errors.append("feedback_action:modify_not_allowed")
        if suggested is None or not isinstance(suggested, str) or not suggested.strip():
            errors.append("suggested_alternative:required_for_modify")

    timestamp = raw_feedback.get("timestamp_minutes")
    if not isinstance(timestamp, (int, float)):
        errors.append("timestamp_minutes:not_numeric")
    elif timestamp < 0:
        errors.append("timestamp_minutes:negative")

    return errors


@dataclass
class FeedbackSession:
    """Collects and tracks feedback for an episode."""

    episode_id: str
    feedbacks: list[ClinicalFeedback] = field(default_factory=list)
    config: HITLFeedbackConfig = field(default_factory=HITLFeedbackConfig.default)

    def add_feedback(self, feedback: ClinicalFeedback) -> list[str]:
        """Add feedback, returns validation errors (empty = OK)."""
        errors = validate_feedback(feedback, self.config)
        if feedback.get("episode_id") != self.episode_id:
            errors.append("episode_id:mismatch")
        if len(self.feedbacks) >= self.config.max_feedback_per_episode:
            errors.append("feedback_limit:exceeded")
        if errors:
            return errors
        self.feedbacks.append(feedback)
        return []

    def get_rejected_actions(self) -> list[str]:
        return [
            f["action_id"]
            for f in self.feedbacks
            if f.get("feedback_action") == FeedbackAction.REJECT.value
        ]

    def get_modified_actions(self) -> list[tuple[str, str]]:
        """Returns [(original_action, suggested_alternative)]"""
        modified: list[tuple[str, str]] = []
        for feedback in self.feedbacks:
            if feedback.get("feedback_action") != FeedbackAction.MODIFY.value:
                continue
            alternative = feedback.get("suggested_alternative")
            if isinstance(alternative, str) and alternative:
                modified.append((feedback["action_id"], alternative))
        return modified

    def get_accepted_actions(self) -> list[str]:
        return [
            f["action_id"]
            for f in self.feedbacks
            if f.get("feedback_action") == FeedbackAction.ACCEPT.value
        ]

    def acceptance_rate(self) -> float:
        if not self.feedbacks:
            return 0.0
        return len(self.get_accepted_actions()) / len(self.feedbacks)

    def rejection_rate(self) -> float:
        if not self.feedbacks:
            return 0.0
        return len(self.get_rejected_actions()) / len(self.feedbacks)


@dataclass
class FeedbackImpactMetrics:
    """Measures impact of feedback on agent behavior."""

    total_feedbacks: int = 0
    feedbacks_applied: int = 0
    same_error_repeated: int = 0
    safety_violations_pre: int = 0
    safety_violations_post: int = 0

    @property
    def application_rate(self) -> float:
        return self.feedbacks_applied / max(self.total_feedbacks, 1)

    @property
    def error_reduction_rate(self) -> float:
        if self.safety_violations_pre == 0:
            return 0.0
        return 1.0 - (self.safety_violations_post / self.safety_violations_pre)

    def summary(self) -> dict[str, object]:
        return {
            "total_feedbacks": self.total_feedbacks,
            "feedbacks_applied": self.feedbacks_applied,
            "same_error_repeated": self.same_error_repeated,
            "safety_violations_pre": self.safety_violations_pre,
            "safety_violations_post": self.safety_violations_post,
            "application_rate": round(self.application_rate, 4),
            "error_reduction_rate": round(self.error_reduction_rate, 4),
        }


def compute_feedback_impact(
    feedbacks: list[ClinicalFeedback],
    pre_actions: list[str],
    post_actions: list[str],
    pre_violations: int,
    post_violations: int,
) -> FeedbackImpactMetrics:
    """Compute impact of feedback on agent behavior."""
    pre_action_set = set(pre_actions)
    post_action_set = set(post_actions)

    applied = 0
    repeated_errors = 0

    for feedback in feedbacks:
        action_id = feedback.get("action_id")
        feedback_action = feedback.get("feedback_action")

        if feedback_action == FeedbackAction.ACCEPT.value:
            if action_id in pre_action_set and action_id in post_action_set:
                applied += 1
        elif feedback_action == FeedbackAction.REJECT.value:
            if action_id not in post_action_set:
                applied += 1
            else:
                repeated_errors += 1
        elif feedback_action == FeedbackAction.MODIFY.value:
            alternative = feedback.get("suggested_alternative")
            if isinstance(alternative, str) and alternative in post_action_set and action_id not in post_action_set:
                applied += 1

    return FeedbackImpactMetrics(
        total_feedbacks=len(feedbacks),
        feedbacks_applied=applied,
        same_error_repeated=repeated_errors,
        safety_violations_pre=pre_violations,
        safety_violations_post=post_violations,
    )
