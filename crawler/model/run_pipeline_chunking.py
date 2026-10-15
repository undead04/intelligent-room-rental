"""Backward compatibility shim.
Vị trí module chính thức: `crawler.model.llm`
"""
from crawler.model.llm import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS_PER_CHUNK,
    DEFAULT_MODEL,
    DEFAULT_RPM_DELAY,
    SYSTEM_PROMPT,
    GeminiRoundRobin,
    build_ai_contents,
    call_gemini_chunk,
    create_dynamic_chunks,
    is_quota_error,
    load_checkpoint,
    process_chunk_result,
    process_one_chunk,
    run_pipeline_chunking,
    save_checkpoint,
)

__all__ = [
    "run_pipeline_chunking",
    "GeminiRoundRobin",
    "call_gemini_chunk",
    "is_quota_error",
    "load_checkpoint",
    "save_checkpoint",
    "create_dynamic_chunks",
    "process_chunk_result",
    "process_one_chunk",
    "SYSTEM_PROMPT",
    "build_ai_contents",
    "DEFAULT_MODEL",
    "DEFAULT_RPM_DELAY",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MAX_TOKENS_PER_CHUNK",
]