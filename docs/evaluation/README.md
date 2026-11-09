# 📊 Khung Đo Lường & Đánh Giá Chất Lượng (Evaluation Framework)

Thư mục này quản lý toàn bộ bộ tiêu chí, kịch bản kiểm thử (Benchmarks) và kết quả đo lường chất lượng của mô hình AI/ML và AI Agent.

---

## 1. Cấu Trúc Thư Mục Evaluation

```text
docs/evaluation/
├── README.md                 # Tổng quan phương pháp luận & chỉ số đánh giá
├── human-eval-protocol.md    # Bộ kịch bản 40 queries & tiêu chí chấm điểm Human-in-the-loop
├── metrics-definition.md     # Công thức toán học các chỉ số (P@k, MRR, nDCG, CSR, Compliance)
└── reports/                  # Lịch sử các báo cáo đo lường (Eval Run Reports)
    └── 2026-11-baseline.md   # Kết quả baseline 40 queries × 5 personas
```

---

## 3. 🏆 Các Báo Cáo Đo Lường Tiêu Biểu

- 🤖 [**Recommendation Evaluation Report (40 Queries × 5 Personas)**](./reports/2026-11-recommendation-eval-40queries.md):
  - **Điểm Thẩm định LLM Judge (`gemini-2.5-flash-lite`):** **`4.48 / 5.0`** (Relevance: 4.50, Ranking: 4.32, Faithfulness: 4.62).
  - **Các chỉ số IR cốt lõi:** $P@3 = 82.50\%$, $\text{MRR} = 0.8750$, $\text{nDCG}@5 = 0.8750$, $\text{CSR} = 87.50\%$.
  - **Độ trễ trung bình:** $0.200$s (Trung vị p50: $0.124$s).
- 🧑‍🎓 [**Human Evaluation Report Template (Mô phỏng N = 30 sinh viên)**](./reports/demo-human-eval-simulation.md):
  - Khung kiểm định thống kê chuẩn (Paired $t$-test & Wilcoxon Signed-Rank Test) với điểm mô phỏng 4.42/5.0. Sẵn sàng thay thế bằng dữ liệu khảo sát thực tế khi nghiệm thu.

