# 🤖 ĐỘI NGŨ SUB-AGENTS (AI TEAMWORK)

Hệ thống được trang bị 3 Sub-Agents chuyên biệt hóa cao, tự động đọc cấu hình dự án từ [`AGENTS.md`](../../AGENTS.md) và [`docs/architecture/`](../../docs/architecture/README.md) để phối hợp làm việc trên bất kỳ dự án phần mềm nào:

---

## 1. Danh Sách 3 Sub-Agents

| Tên Sub-Agent | Vai Trò | Quyền Hạn | Trọng Tâm |
| :--- | :--- | :--- | :--- |
| **`codebase-researcher`** | Nghiên cứu & Khảo sát | **Read-only** (Không sửa code, có Context7) | Đọc `AGENTS.md` & `docs/architecture/`, khảo sát codebase, tra cứu tài liệu thư viện mới, phân tích Root Cause và đề xuất giải pháp kiến trúc. |
| **`core-developer`** | Lập trình viên chính | **Write Code** (Sửa file, chạy lệnh build/test) | Viết tính năng, fix bug tuân thủ nghiêm ngặt Tech Stack, Scope Control và Manual Commit Gate quy định trong `AGENTS.md`. |
| **`quality-tester`** | Tester khó tính (QA) | **Write Test & Run Test** (Viết & chạy test) | Viết Black-box test độc lập theo SPEC/DTO, săn lỗi biên, chống gian lận test, bao phủ đủ 4 nhóm test case và chạy lệnh kiểm thử chuẩn trong `AGENTS.md`. |

---

## 2. Quy Trình Phối Hợp Tối Ưu (Optimal Workflow)

```text
[ Người dùng giao Task / Gõ /teamwork ]
           │
           ▼
[ BƯỚC 1: Gọi codebase-researcher ]
- Đọc AGENTS.md và docs/architecture/ để nắm bối cảnh dự án
- Khảo sát các module/file bị ảnh hưởng trong codebase
- Tra cứu tài liệu thư viện qua Context7 MCP (nếu cần)
- Lập bản tóm tắt phương án & trích dẫn dòng code cụ thể
           │
           ▼
[ BƯỚC 2: Gọi core-developer ]
- Nhận bản tóm tắt từ researcher
- Viết code chuẩn theo Tech Stack quy định trong AGENTS.md
- Tự đọc terminal log để tự sửa lỗi (Self-healing)
- Đồng bộ docs/architecture/ nếu có thay đổi kiến trúc
           │
           ▼
[ BƯỚC 3: Gọi quality-tester ]
- Viết test độc lập theo SPEC/Contract (Black-box testing)
- Bao phủ đủ 4 nhóm test: Happy Path, Edge cases, Mutation, Persistence
- Chạy lệnh test suite chuẩn trong AGENTS.md xác nhận pass 100%
- Báo cáo kết quả và dừng lại ở Waiting Gate chờ người dùng nghiệm thu
```
