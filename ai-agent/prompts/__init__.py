"""Prompt Management Layer cho Homigo AI Agent."""

from __future__ import annotations

from prompts.advisory_prompt import build_advisory_prompt
from prompts.decision_prompt import (
    ADVICE_RULES,
    DECISION_RULES,
    build_advice_prompt,
    build_decision_prompt,
)
from prompts.nlu_prompt import BASE_PROMPT

CAPABILITY_PROMPT = f"{DECISION_RULES}"


def build_system_prompt() -> str:
    return f"{BASE_PROMPT}\n\n{CAPABILITY_PROMPT}"


__all__ = [
    "BASE_PROMPT",
    "ADVICE_RULES",
    "DECISION_RULES",
    "CAPABILITY_PROMPT",
    "build_advice_prompt",
    "build_decision_prompt",
    "build_advisory_prompt",
    "build_system_prompt",
]
