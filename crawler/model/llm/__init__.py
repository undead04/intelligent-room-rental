"""Package crawler.model.llm
Chuyên trách toàn bộ logic gọi LLM (Gemini), dynamic chunking, checkpointing và bóc tách thông tin tin đăng.
"""
from crawler.model.llm.checkpoint import load_checkpoint, save_checkpoint, convert_checkpoint_to_jsonl
from crawler.model.llm.chunker import create_dynamic_chunks
from crawler.model.llm.client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RPM_DELAY,
    GeminiRoundRobin,
    call_gemini_chunk,
    is_quota_error,
)
from crawler.model.llm.pipeline import (
    DEFAULT_MAX_TOKENS_PER_CHUNK,
    DEFAULT_MODEL,
    run_pipeline_chunking,
)
from crawler.model.llm.processor import process_chunk_result, process_one_chunk
from crawler.model.llm.prompt import SYSTEM_PROMPT, build_ai_contents

__all__ = [
    "run_pipeline_chunking",
    "GeminiRoundRobin",
    "call_gemini_chunk",
    "is_quota_error",
    "load_checkpoint",
    "save_checkpoint",
    "convert_checkpoint_to_jsonl",
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
