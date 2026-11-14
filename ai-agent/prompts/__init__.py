"""Prompt Management Layer cho Homigo AI Agent."""

from __future__ import annotations

from prompts.advisory_prompt import build_advisory_prompt
from prompts.decision_prompt import (
    ADVICE_RULES,
    DECISION_RULES,
    build_advice_prompt,
    build_decision_prompt,
    build_zero_result_user_prompt,
)
from prompts.nlu_prompt import (
    BASE_PROMPT,
    INTENT_GUIDE,
    NLU_RULES,
    build_nlu_system_prompt,
)

__all__ = [
    "BASE_PROMPT",
    "INTENT_GUIDE",
    "NLU_RULES",
    "ADVICE_RULES",
    "DECISION_RULES",
    "build_nlu_system_prompt",
    "build_advice_prompt",
    "build_decision_prompt",
    "build_zero_result_user_prompt",
    "build_advisory_prompt",
]
