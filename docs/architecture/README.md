# 🏛️ Tài Liệu Kiến Trúc Hệ Thống (Architecture Hub)

Thư mục này chứa toàn bộ tài liệu kiến trúc kỹ thuật của hệ thống, được module hóa để tối ưu hóa context window cho AI Agent và phòng tránh xung đột git.

---

## 📚 Danh Mục Module Kiến Trúc

1. 🛠️ [**Kiến Trúc Công Nghệ & Bảng Lệnh (Tech Stack)**](./tech-stack.md)
   - Phân tách 4 microservices: `backend/`, `ai-agent/`, `frontend/`, `crawler/`.
   - Runtime, môi trường ảo, cổng mạng và bảng lệnh chuẩn.

2. 🧩 **Các Module Nguyên Lý Hệ Thống (Modular Principles):**
   - 🔄 [`modules/etl-pipeline.md`](./modules/etl-pipeline.md): Pipeline ETL 6 bước, Staging SQLite WAL, Crawler concurrency.
   - 🔍 [`modules/search-and-ranking.md`](./modules/search-and-ranking.md): Hybrid Search 70/30, Haversine filter, MCDM Reranker 5 tiêu chí.
   - 🤖 [`modules/ai-agent-graph.md`](./modules/ai-agent-graph.md): LangGraph State Machine 8 nodes, Tool Partitioning, Self-RAG Grounding.

3. 🗄️ [**Mô Hình Dữ Liệu (Data Models & Schemas)**](./data-models.md)
   - Sơ đồ quan hệ thực thể ERD chi tiết (PostgreSQL).
   - Cấu trúc các bảng: `listings`, `listing_embeddings`, `room_types`...
   - Taxonomy 17 tiện ích chuẩn hóa.

4. 🎨 [**Hệ Thống Thiết Kế Giao Diện (Design System)**](./design-system.md)
   - Triết lý thị giác *Modern Housing UI (Hiện đại & Tối giản)*.
   - Bảng mã màu tokens (`#FAF8F4`, `#0F5F4A`, `#E88C38`), font `Be Vietnam Pro`.
   - Quy chuẩn components (`Button`, `ListingCard`, `Filters`) & Prompt context cho Stitch UI.

5. ⭐️ [**Lịch Sử Quyết Định Kiến Trúc (Architecture Decision Records - ADR)**](./decisions/)
   - [`decisions/0001-hybrid-search-70-30.md`](./decisions/0001-hybrid-search-70-30.md): Tại sao chọn Hybrid Search 70/30.
   - [`decisions/0002-mcdm-reranker-5-pillars.md`](./decisions/0002-mcdm-reranker-5-pillars.md): Tại sao chọn Reranker 5 tiêu chí.
   - [`decisions/0003-langgraph-tool-partitioning.md`](./decisions/0003-langgraph-tool-partitioning.md): Tại sao chọn State Machine 8 nodes.
