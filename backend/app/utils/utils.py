"""Compatibility shim: Re-exporting from app.services.reranker.

To follow clean architecture, all MCDM Dynamic Reranking logic has been moved
to app.services.reranker.
"""
from app.services.reranker import (
    DEFAULT_WEIGHTS,
    EARTH_RADIUS_KM,
    UNKNOWN_SCORE,
    _ALIAS_MAP,
    _NORMALIZE_AMENITY,
    _amenity_fit,
    _clamp01,
    _dynamic_weights,
    _get,
    _haversine_km,
    _location_fit,
    _location_part,
    _match_breakdown,
    _normalize_amenity,
    _price_fit,
    _score_or_unknown,
    component_influence,
    explain_match,
    rerank,
)

__all__ = [
    "rerank",
    "explain_match",
    "component_influence",
    "DEFAULT_WEIGHTS",
    "_amenity_fit",
    "_dynamic_weights",
    "_NORMALIZE_AMENITY",
    "_normalize_amenity",
    "_ALIAS_MAP",
]