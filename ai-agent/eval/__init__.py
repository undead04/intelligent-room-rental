"""Bộ đánh giá & ablation. Chạy: python -m eval.run --help

Các số đo của gói này chia hai loại, KHÔNG được trộn khi viết báo cáo:
  - ĐO ĐƯỢC NGAY, xác định (guardrail, kiểm chứng grounding, NLU keyword baseline): chạy không cần LLM/backend.
  - CẦN LLM/BACKEND THẬT (NLU bằng LLM, e2e + ablation): bạn tự chạy, kết quả phụ thuộc model và dữ liệu.
Dataset ở đây do người viết hệ thống tạo (nhỏ, có thể thiên lệch): hãy bổ sung ca thật từ log người dùng trước khi công bố số.
"""
