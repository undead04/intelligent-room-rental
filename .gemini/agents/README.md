# 🤖 ĐỘI NGŨ SUB-AGENTS (AI TEAMWORK)

Hệ thống được trang bị 3 Sub-Agents chuyên biệt hóa cao để làm việc song song hiệu quả trong toàn bộ 4 microservices của Homigo:

---

## 1. Danh Sách 3 Sub-Agents

| Tên Sub-Agent | Vai Trò | Quyền Hạn | Trọng Tâm |
| :--- | :--- | :--- | :--- |
| **`codebase-researcher`** | Nghiên cứu & Khảo sát | **Read-only** (Không sửa code, có Context7) | Đọc codebase 4 microservices, tra cứu docs mới, tìm nguyên nhân lỗi, đề xuất giải pháp kiến trúc. |
| **`core-developer`** | Lập trình viên chính | **Write Code** (Sửa file, chạy dev server) | Viết tính năng, fix bug, tuân thủ `AGENTS.md` (Next.js 16 App Router, FastAPI, LangGraph, Crawler). |
| **`quality-tester`** | Tester khó tính (QA) | **Write Test & Run Test** (Viết test, chạy pytest) | Viết test độc lập theo SPEC, săn lỗi biên, test chống gian lận, bao phủ 4 nhóm test case. |

---

## 2. Quy Trình Phối Hợp Tối Ưu (Optimal Workflow)

```text
[ Người dùng giao Task ]
           │
           ▼
[ BƯỚC 1: Gọi codebase-researcher ]
- Khảo sát các file bị ảnh hưởng trong 4 microservices
- Tra cứu tài liệu thư viện mới qua Context7 MCP
- Lập bản tóm tắt phương án & trích dẫn dòng code
           │
           ▼
[ BƯỚC 2: Gọi core-developer ]
- Nhận bản tóm tắt từ researcher
- Viết code chuẩn tech stack (Next.js 16, FastAPI, LangGraph, Python 3.11/3.13)
- Tự đọc terminal log để tự sửa lỗi (Self-healing)
           │
           ▼
[ BƯỚC 3: Gọi quality-tester ]
- Viết test độc lập theo SPEC (Black-box testing)
- Bao phủ đủ 4 nhóm test: Happy Path, Edge cases, Mutation, Persistence
- Chạy pytest / test suite xác nhận pass 100%
- Báo cáo kết quả và dừng lại chờ người dùng duyệt PR
```
