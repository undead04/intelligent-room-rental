from __future__ import annotations

import math
import statistics
from typing import Iterable, Sequence


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy Wilson 95% cho tỉ lệ k/n (đúng khi mẫu nhỏ, không như xấp xỉ chuẩn)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "rate": (k / n) if n else None, "ci_lo": lo, "ci_hi": hi}


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = (2 * p * r / (p + r)) if p and r else (0.0 if p is not None and r is not None else None)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f}


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * q
    lo, hi = math.floor(idx), math.ceil(idx)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def summarize(values: Iterable[float]) -> dict:
    v = list(values)
    return {"n": len(v), "mean": statistics.fmean(v) if v else 0.0, "p50": percentile(v, 0.5), "p95": percentile(v, 0.95), "max": max(v) if v else 0.0}


def fmt_rate(d: dict) -> str:
    if d.get("rate") is None:
        return "n/a"
    return f"{d['rate'] * 100:.1f}% ({d['k']}/{d['n']}; CI {d['ci_lo'] * 100:.0f}–{d['ci_hi'] * 100:.0f}%)"
