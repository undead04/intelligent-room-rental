# 📊 Khung Đo Lường & Đánh Giá Chất Lượng (Evaluation Framework)

Thư mục này quản lý toàn bộ bộ tiêu chí, kịch bản kiểm thử (Benchmarks) và kết quả đo lường chất lượng của mô hình AI/ML và AI Agent.

---

## 1. Cấu Trúc Thư Mục Evaluation

```text
docs/evaluation/
├── README.md                             # Tổng quan phương pháp luận & chỉ số đánh giá
├── human-eval-protocol.md                # Giao thức & tiêu chí chấm điểm Human-in-the-loop
└── reports/                              # Báo cáo thực nghiệm (Eval Run Reports)
    ├── 2026-11-evaluation-summary.md     # Báo cáo tổng hợp (AI Agent + Ablation E2E + ML v2)
    └── demo-human-eval-simulation.md     # Mẫu phân tích Human Eval (N = 30 mô phỏng)
```

---

## 3. 🏆 Các Báo Cáo Đo Lường Tiêu Biểu

- 📊 [**Báo Cáo Tổng Hợp Đánh Giá Hệ Thống Homigo (AI Agent + Ablation + ML v2)**](./reports/2026-11-evaluation-summary.md):
  - **Ablation Study End-to-End (`eval.run ablation`):** `E_full` đạt **`100.0% (39/39)`** checks, **`0.0% (0/12)`** lỗi tới người dùng (so với `8.3%` ở `B_+NLU`) và **`0.0% (0/12)`** fallback câu mẫu (so với `16.7%` ở `D_+verify_no_retry`).
  - **Độ ổn định & An toàn (`eval.run`):** Guardrail **`100.0% (83/83)`** ngoài HARD (`0.0%` false positive), Grounding **`100.0% (480/480)`**, `pass^3 = 100.0% (15/15)`.
  - **Thang Điểm 5 Trụ Cột (`eval.thesis_eval_rubric --with-model`):** **`100.00 / 100.0`** (độ phủ 100%, NLU LLM `12/12`).
  - **Mô hình Định giá ML v2:** Ensemble Blend **`MAE = 598,769 đ`**, **`R²(Log) = 0.7235`**, Conformal Coverage **`83.15%`**.
- 🧑‍🎓 [**Human Evaluation Report Template (Mô phỏng N = 30 sinh viên)**](./reports/demo-human-eval-simulation.md):
  - Khung kiểm định thống kê chuẩn (Paired $t$-test & Wilcoxon Signed-Rank Test) với điểm mô phỏng 4.42/5.0. Sẵn sàng thay thế bằng dữ liệu khảo sát thực tế khi nghiệm thu.

