# 📚 Kho Tri Thức & Tài Liệu Kỹ Thuật (Documentation Hub)

Chào mừng bạn đến với trung tâm tài liệu kỹ thuật của dự án. Hệ thống tài liệu được tổ chức theo tiêu chuẩn **Module hóa & Hướng Miền (Modularized Domain-Driven Documentation)**, giúp cả con người và AI Coding Agent có thể tra cứu thông tin nhanh chóng, chính xác mà không bị tràn context.

---

## 🗺️ Bản Đồ Tài Liệu (Documentation Sitemap)

```text
docs/
├── architecture/                 # 1. 🏛️ KIẾN TRÚC TỔNG THỂ & QUYẾT ĐỊNH THIẾT KẾ
│   ├── README.md                 # - Tổng quan kiến trúc & các quy tắc đồng bộ
│   ├── tech-stack.md             # - Danh sách công nghệ, ports, runtime, bảng lệnh
│   ├── system-principles.md      # - Nguyên lý luồng dữ liệu, thuật toán lõi, ETL, Reranker
│   ├── data-models.md            # - Sơ đồ ERD, Database Schemas, Taxonomy 17 tiện ích
│   └── decisions/                # ⭐️ Architecture Decision Records (ADRs)
│       ├── 0001-hybrid-search-70-30.md
│       ├── 0002-mcdm-reranker-5-pillars.md
│       └── 0003-langgraph-tool-partitioning.md
│
├── contracts/                    # 2. 🤝 KHẾ ƯỚC DỮ LIỆU & API GIAO TIẾP
│   ├── README.md                 # - Tổng quan nguyên tắc thiết kế API
│   └── api/                      # - Chi tiết các REST & SSE Endpoints giữa các services
│
├── features/                     # 3. 🚀 ĐẶC TẢ TÍNH NĂNG THEO VÒNG ĐỜI
│   ├── README.md                 # - Bảng trạng thái tính năng (Backlog, In-progress, Released)
│   ├── backlog/                  # - Tính năng đang lên kế hoạch
│   ├── in-progress/              # - Tính năng đang triển khai
│   └── released/                 # - Tính năng đã phát hành & kiểm thử hoàn tất
│       ├── listing-lifecycle-sync.md
│       ├── ml-price-model-v2.md
│       └── ai-agent-recommendation-eval.md
│
├── evaluation/                   # 4. 📊 ĐO LƯỜNG CHẤT LƯỢNG & BENCHMARKS
│   ├── README.md                 # - Khung đo lường & 3 nhóm chỉ số (IR, Compliance, Rubric)
│   ├── human-eval-protocol.md    # - Bộ tiêu chí & kịch bản đánh giá chất lượng gợi ý
│   └── reports/                  # - Báo cáo thực nghiệm (Human Eval 4.42/5.0 & Recommendation Eval)
│
└── maintenance/                  # 5. 🛠️ BẢO TRÌ, SỬA LỖI & NÂNG CẤP HỆ THỐNG
    ├── README.md                 # - Dashboard theo dõi tiến độ sửa lỗi & bảo trì
    ├── TEMPLATE.md               # - Mẫu chuẩn tạo issue bảo trì/sửa lỗi mới
    ├── in-progress/              # - Các sự cố & tối ưu đang thực hiện
    └── resolved/                 # - Các sự cố đã nghiệm thu & bài học rút ra
```

---

## ⚡ Nguyên Tắc Bắt Buộc Dành Cho AI Agent

1. **Session Start:** Luôn đọc [`architecture/tech-stack.md`](./architecture/tech-stack.md) và [`architecture/README.md`](./architecture/README.md) trước khi làm việc.
2. **Architecture Sync Gate:** Khi thay đổi code làm thay đổi Database Schema, API Contract hoặc Luồng dữ liệu, bắt buộc phải cập nhật ngay file tương ứng trong `docs/architecture/` hoặc `docs/contracts/` trước khi bàn giao.
3. **Traceability:** Các quyết định thay đổi thuật toán lớn phải được ghi lại dưới dạng một bản ADR mới trong `docs/architecture/decisions/`.
