"""Tiện ích địa lý."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Khoảng cách đường chim bay (km) giữa hai toạ độ."""
    p1, l1, p2, l2 = map(radians, (float(lat1), float(lng1), float(lat2), float(lng2)))
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin((l2 - l1) / 2) ** 2
    return EARTH_RADIUS_KM * 2 * asin(sqrt(a))
