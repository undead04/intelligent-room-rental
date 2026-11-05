# 🏛️ Tài Liệu Kiến Trúc Hệ Thống Homigo (Architecture Overview)

Thư mục này chứa toàn bộ tài liệu kiến trúc kỹ thuật của dự án **Homigo — Hệ thống Hỗ trợ Ra quyết định Tìm kiếm Phòng trọ Thông minh**. 

> [!NOTE]
> **Quy tắc Đồng bộ Kiến trúc dành cho AI Agent:**  
> 1. **Khi bắt đầu phiên mới (New Session):** Hãy đọc lướt qua 3 tài liệu cốt lõi bên dưới để nắm bắt chuẩn xác 100% bối cảnh, công nghệ và mô hình dữ liệu của dự án.
> 2. **Khi có thay đổi kiến trúc:** Bất kỳ thay đổi nào về DB Schema, DTO, luồng ETL, Hybrid Search/Reranker, LangGraph State Machine hoặc Tech Stack đều **bắt buộc** phải được cập nhật đồng bộ ngay vào các file tương ứng trong thư mục này.

---

## 📚 Danh Mục Tài Liệu Kiến Trúc

1. 🛠️ [**Kiến Trúc Công Nghệ (Tech Stack)**](./tech-stack.md)
   - Phân tách 4 microservices: `backend/` (Port 8000), `ai-agent/` (Port 8001), `frontend/` (Port 3000), và `crawler/`.
   - Chi tiết dependencies, runtime môi trường ảo, cổng mạng và lệnh khởi chạy từng service.

2. 🏛️ [**Các Nguyên Tắc Thiết Kế Hệ Thống (System Principles)**](./system-principles.md)
   - Pipeline ETL dữ liệu 6 bước (`Extract -> Clean -> Enrich -> Transform (ML) -> Embed (E5) -> Load (Postgres)`).
   - Cơ chế Hybrid Search (70% Dense pgvector + 30% Sparse PostgreSQL FTS).
   - Thuật toán Reranker MCDM 5 tiêu chí (Price, Location, Amenity, Safety, Quality).
   - LangGraph State Machine 8 nodes và nguyên tắc Tool Partitioning.
   - Cơ chế chống ảo giác hai tầng (Crawler `verify_evidence` & AI-Agent `verify_node` Self-RAG).
   - Chu trình đồng bộ vòng đời tin hết hạn (Listing Lifecycle Sync).

3. 🗄️ [**Mô Hình Dữ Liệu (Data Models & Database Schema)**](./data-models.md)
   - Sơ đồ quan hệ thực thể ERD chi tiết (PostgreSQL).
   - Cấu trúc các bảng: `listings`, `listing_embeddings`, `cities`, `districts`, `wards`, `room_types`, `users`.
   - Bảng Staging SQLite: `raw_listings` (chế độ WAL).
   - Chuẩn Taxonomy 17 tiện ích, an ninh & lối sống chuẩn hóa (`Canonical Taxonomy`).
   - Khế ước dữ liệu DTO mẫu giữa Backend và Frontend/AI-Agent.

