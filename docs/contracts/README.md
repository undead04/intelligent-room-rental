# 🤝 Hợp Đồng Giao Tiếp API (API Contracts Overview)

Thư mục này định nghĩa toàn bộ **Khế ước Giao tiếp (Contracts)** giữa các dịch vụ độc lập trong hệ thống:
- `frontend` (Next.js 16)
- `backend` (FastAPI)
- `ai-agent` (LangGraph Service)
- `crawler` (ETL Engine)

---

## 1. Nguyên Tắc Thiết Kế API Contracts

1. **Single Source of Truth:**
   - Mọi thay đổi về Request Body, Query Params, Response DTO phải được cập nhật tại đây trước khi viết code.
   - Các types trong `frontend/src/types/` và Pydantic Schemas trong `backend/app/schemas/` và `ai-agent/domain/schemas.py` phải khớp 100% với tài liệu này.
2. **Cấm sử dụng kiểu động không kiểm soát (`any` / `dict` tự do):**
   - Mọi payload đều phải có cấu trúc tường minh và validation chặt chẽ.
3. **Tương thích ngược (Backward Compatibility):**
   - Không được xóa bỏ đột ngột các trường cũ khi client chưa kịp cập nhật; sử dụng cờ deprecation hoặc shim tương thích.

---

## 2. Danh Mục Khế Ước

| Tài Liệu Contract | Chi Tiết | Các Bên Tham Gia |
| :--- | :--- | :--- |
| [`api/backend-api.md`](./api/backend-api.md) | Đặc tả các REST endpoints tìm kiếm, chi tiết phòng, bộ lọc | `backend` $\leftrightarrow$ `frontend`, `ai-agent` |
| [`api/ai-agent-api.md`](./api/ai-agent-api.md) | Đặc tả SSE Chat Stream, Preference Patch, Feedback | `ai-agent` $\leftrightarrow$ `frontend` |
| [`../architecture/data-models.md`](../architecture/data-models.md) | Database Schemas (PostgreSQL & SQLite Staging) | `backend`, `crawler` |

