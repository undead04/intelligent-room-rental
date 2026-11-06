"""Compatibility shim: Re-exporting from app.services.reranker.

To follow clean architecture, all MCDM Dynamic Reranking logic has been moved
to app.services.reranker.
"""
from app.services.reranker import (
    DEFAULT_WEIGHTS,
    _NORMALIZE_AMENITY,
    _amenity_fit,
    _dynamic_weights,
    _normalize_amenity,
    explain_match,
    rerank,
)

__all__ = [
    "rerank",
    "explain_match",
    "DEFAULT_WEIGHTS",
    "_amenity_fit",
    "_dynamic_weights",
    "_NORMALIZE_AMENITY",
    "_normalize_amenity",
]