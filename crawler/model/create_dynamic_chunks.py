"""Backward compatibility shim.
Vị trí chính thức: `crawler.model.llm.chunker`
"""
from crawler.model.llm.chunker import create_dynamic_chunks

__all__ = ["create_dynamic_chunks"]