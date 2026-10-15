"""Backward compatibility shim.
Vị trí chính thức: `crawler.model.llm.prompt`
"""
from crawler.model.llm.prompt import (
    FEW_SHOTS,
    SYSTEM_PROMPT,
    build_ai_contents,
)

__all__ = ["SYSTEM_PROMPT", "FEW_SHOTS", "build_ai_contents"]