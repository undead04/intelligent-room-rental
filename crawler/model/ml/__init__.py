"""Cầu nối (Re-export) tới module Machine Learning tại `/ml` (nếu có mặt trong cùng môi trường).
Nếu chạy trong container tách biệt không có `/ml`, module vẫn hoạt động an toàn.
"""

try:
    from ml.price_evaluator import PriceEvaluator, RoomPriceEvaluator
except ImportError:
    PriceEvaluator = None
    RoomPriceEvaluator = None

__all__ = ["RoomPriceEvaluator", "PriceEvaluator"]
