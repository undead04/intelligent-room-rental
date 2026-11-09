# 📦 Quy Chuẩn Cấu Trúc Hệ Thống `.agents` (Generic Agent Engine)

Thư mục `.agents/` là **Bộ máy Thực thi Độc lập (Generic Agent Engine)**, được thiết kế theo tiêu chuẩn Plug-and-Play để có thể cắm vào **bất kỳ dự án phần mềm nào** (Web, Mobile, Backend, AI/ML, Microservices, Monorepo...).

---

## 1. Triết Lý Thiết Kế: Single Source of Truth

Để không bị phụ thuộc vào bất kỳ công nghệ hay dự án cụ thể nào:
- **`.agents/` KHÔNG chứa thông tin cứng (hard-coded) của dự án:** Không ghi cứng tên framework, database, port, hay tên biến của riêng một dự án.
- **`AGENTS.md` (ở root repo):** Là file cấu hình trung tâm (Single Source of Truth) định nghĩa:
  1. Mục tiêu và phạm vi của dự án hiện tại.
  2. Bảng phân chia Tech Stack, Runtime, Ports của các dịch vụ/modules.
  3. Bảng lệnh chạy chuẩn (Run, Build, Test, Lint) của môi trường cục bộ.
- **`docs/` (ở root repo):** Chứa toàn bộ tri thức kỹ thuật & nghiệp vụ:
  1. `docs/architecture/`: Kiến trúc hệ thống, Tech Stack, Data Models/Schemas, System Principles.
  2. `docs/features/`: Tài liệu đặc tả tính năng (Specs & Requirements).
  3. `docs/fix/`: Lịch sử và kế hoạch sửa lỗi, tối ưu hệ thống (Bug Fixing & Refactoring).

---

## 2. Cấu Trúc Thư Mục `.agents/`

```text
.agents/
├── README.md                 # Hướng dẫn tích hợp & quy chuẩn sử dụng Generic Agent Engine
├── mcp_config.json.example   # Template cấu hình Model Context Protocol (MCP) servers
│
├── agents/                   # Đội ngũ Sub-Agents chuyên môn hóa
│   ├── README.md             # Quy trình phối hợp 3 bước (Researcher -> Developer -> Tester)
│   ├── codebase-researcher.md# Sub-agent Khảo sát & Phân tích (Read-only, Context7)
│   ├── core-developer.md     # Sub-agent Lập trình chính (Full Write, Self-healing)
│   └── quality-tester.md     # Sub-agent QA độc lập (Anti-Cheating Black-box Tester)
│
├── rules/                    # Quy tắc ứng xử và tiêu chuẩn làm việc
│   ├── spec-and-milestones.md# Quy chuẩn viết Spec, chia mốc Vertical Slice (4-6 files/mốc)
│   └── code-review.md        # Tiêu chuẩn review code (Security, Edge cases, Format)
│
└── skills/                   # Kỹ năng hành động chuẩn hóa
    ├── plan-and-execute/     # Lập kế hoạch kèm Implementation Plan Artifact & Nút Proceed
    ├── github-workflow/      # Quy trình Git an toàn: Solo Dev vs Team, Manual Commit Gate
    ├── rigorous-testing/     # Quy trình Black-box testing đủ 4 nhóm test case
    ├── code-review/          # Rà soát code theo 3 mức độ (🔴 Nghiêm trọng, 🟡 Cảnh báo, 🟢 Gợi ý)
    ├── security-audit/       # Kiểm toán an ninh ứng dụng (AppSec / Vulnerability hunting)
    ├── db-migration/         # Quy trình migration schema & rollback an toàn
    └── summarize-session/    # Tóm tắt tiến độ để chuyển giao session mượt mà
```

---

## 3. Cách Tích Hợp Vào Một Dự Án Mới (Plug-and-Play)

Khi muốn mang bộ khung này sang một dự án phần mềm mới:

1. **Copy 2 thư mục vào thư mục gốc của repo:**
   - Copy thư mục `.agents/`
   - Copy cấu trúc thư mục `docs/` (kèm các file mẫu `architecture/`, `features/`, `fix/`)
2. **Tạo file `AGENTS.md` tại thư mục gốc:**
   - Điền tên dự án và mô tả tổng quan.
   - Điền Tech Stack, đường dẫn module và bảng lệnh chạy test/dev chuẩn của dự án đó.
3. **Cập nhật `docs/architecture/`:**
   - Điền thông tin kiến trúc, mô hình dữ liệu (Database Schema / DTO) của dự án.
4. **Bắt đầu làm việc:**
   - Gõ `/plan` để AI Agent tự động đọc `AGENTS.md` + `docs/` và phân công Sub-Agents thực hiện công việc!
