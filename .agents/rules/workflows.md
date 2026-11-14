# 🎯 Quy Chuẩn Quy Trình Làm Việc Của AI Agent (Standard Workflows & Rules)

Tài liệu này quy định các nguyên tắc bắt buộc dành cho AI Agent xuyên suốt toàn bộ vòng đời phát triển tính năng, bảo trì và gỡ lỗi trong bất kỳ dự án phần mềm nào (tham chiếu bối cảnh cụ thể tại [`AGENTS.md`](../../AGENTS.md) và [`docs/architecture/`](../../docs/architecture/README.md)).

---

## PHẦN 1: 📋 QUY TRÌNH VIẾT SPEC, CHIA MỐC & LẬP PLAN (Trước khi viết code)

Khi tiếp nhận yêu cầu tính năng mới, gõ `/plan` hoặc đọc tài liệu đặc tả trong `docs/`:

### 1. Khảo Sát Docs & Đánh Giá Hiện Trạng:
- **Đọc kỹ tài liệu liên quan trong `docs/`:**
  - `docs/architecture/`: Modules, Tech Stack, Database Schemas, Design System.
  - `docs/contracts/`: API Specs, DTO giữa các services/modules.
  - `docs/features/`: Đối chiếu các spec trong `backlog/`, `in-progress/`, `released/` (nếu là tính năng mới).
  - `docs/maintenance/`: Đối chiếu các issue trong `in-progress/` hoặc `resolved/` (nếu là task sửa lỗi/bảo trì).
- So sánh spec với codebase hiện tại để xác định chính xác các API, models, components hoặc pipeline cần xây dựng hay nâng cấp.

### 2. Checklist Bắt Buộc Để Theo Dõi Tiến Độ (Progress Tracking Checklist):
- Trong tài liệu Spec/Plan luôn phải có bảng phân công checklist công việc chi tiết dạng `[ ]` theo từng tầng kiến trúc / module được quy định trong [`AGENTS.md`](../../AGENTS.md).
- **Cập nhật trạng thái liên tục:** Mỗi khi một đầu việc hoặc một mốc hoàn thành, Agent phải cập nhật chuyển `[ ]` thành `[x]` ngay trong tài liệu Spec để người dùng và các phiên làm việc sau nhìn vào là biết chính xác tiến độ.

### 3. ⚡ 3 Nguyên Tắc Bắt Buộc Khi Chia Mốc:
1. **Working Software (Phần mềm chạy được thực tế):**
   - Mỗi mốc sau khi hoàn thành **BẮT BUỘC phải là một phiên bản chạy thử được ngay** trên trình duyệt hoặc terminal (lát cắt dọc hoàn chỉnh - Vertical Slice).
   - ❌ **CẤM:** Chia mốc cụt lủn theo chiều ngang (ví dụ: Mốc 1 chỉ tạo file type/schema, Mốc 2 mới viết logic, Mốc 3 mới test).
2. **One Session Scope (Gói gọn trong 1 phiên chat):**
   - Mỗi mốc chỉ gói gọn lượng việc vừa đủ để code và kiểm thử hoàn chỉnh trong vòng **1 phiên chat duy nhất**.
   - Khống chế khối lượng: **Tối đa 4 - 6 files code** trong một mốc để tránh cạn context window và đảm bảo độ tập trung.
3. **Tiêu Chí Nghiệm Thu Rõ Ràng (Acceptance Criteria):**
   - Mỗi mốc bắt buộc phải nêu rõ đủ 3 nội dung:
     + Mục tiêu cụ thể của mốc: Giải quyết bài toán gì?
     + Danh sách file chính sẽ tạo hoặc chỉnh sửa.
     + Cách kiểm chứng thực tế: Câu lệnh terminal cụ thể (theo Bảng lệnh chuẩn trong `AGENTS.md`) hoặc thao tác trên giao diện để người dùng tự tay xác nhận.

### 4. ⚡ Quy Tắc Thực Thi Tinh Gọn Theo Kiến Trúc Orchestrator (Planner → Executor):
- Trong chế độ **Orchestrator 2 pha (Plan & Execute)**, **Planning Model** đảm nhiệm toàn bộ vai trò khảo sát & thiết kế kiến trúc, còn **Execution Model** trực tiếp đảm nhiệm viết code, *Self-healing*, đồng bộ `docs/architecture/` và viết/chạy Black-box test (4 nhóm theo skill [`rigorous-testing`](../skills/rigorous-testing/SKILL.md)) ngay trong phiên chính.
- **Không bắt buộc gắn thẻ hoặc gọi `invoke_subagent` tuần tự 3 con** (`[codebase-researcher]`, `[core-developer]`, `[quality-tester]`) khi bấm **Proceed**, giúp tránh đọc lặp codebase tốn gấp 2–3 lần token và tránh giới hạn quyền ghi file của sandbox subagent.
- Chỉ gọi subagent khi cần tách biệt ngữ cảnh khảo sát diện rộng (*context isolation*) hoặc khi người dùng chủ động yêu cầu `/teamwork`.

### 5. 🚀 Quy Chuẩn Triển Khai Từng Mốc (`/plan: [MỐC X]`):
1. **Đọc lại tài liệu liên quan:** Đọc lại spec, `AGENTS.md`, `docs/architecture/`, `docs/contracts/` và các file mã nguồn liên quan trực tiếp đến Mốc X.
2. **Kiểm soát phạm vi tuyệt đối & Quy tắc Commit (Strict Scope & Commit Control):**
   - **CHỈ TẬP TRUNG 100% VÀO PHẠM VI CỦA MỐC X.**
   - **TUYỆT ĐỐI KHÔNG** đụng vào code, schema hay các file thuộc phạm vi của các mốc sau.
   - **Chỉ commit những file mình đã sửa:** Sử dụng `git add <file-cụ-thể>`, cấm `git add .` bừa bãi.
3. **Đồng bộ Tài liệu Kiến trúc (`docs/architecture/`):**
   - Nếu Mốc X có thay đổi đến Database Schema, DTO/Contract, luồng xử lý cốt lõi, cấu trúc module hoặc dependencies, bắt buộc cập nhật ngay vào `docs/architecture/` trước khi đóng mốc.
4. **Cập nhật tiến độ Spec:** Chuyển các đầu việc hoàn thành từ `[ ]` $\rightarrow$ `[x]` trong tài liệu đặc tả.
5. **Lưu trữ & Bàn giao:** Kích hoạt chuyên biệt skill [`.agents/skills/github-workflow/SKILL.md`](../skills/github-workflow/SKILL.md) để dừng lại chờ người dùng nghiệm thu (Waiting Gate) và chỉ thực hiện commit/push/merge khi có lệnh.

---

## PHẦN 2: 🔍 TIÊU CHUẨN RÀ SOÁT CHẤT LƯỢNG CODE (Code Review Checklist)

Trước khi bàn giao một tính năng, đóng mốc hoặc tạo commit, Agent bắt buộc phải tự rà soát code theo 3 cấp độ:

### 1. 🔴 Bảo Mật & Hợp Đồng Dữ Liệu (Security & Contract Safety):
- **Không rò rỉ secret:** Tuyệt đối không hard-code API key, token, mật khẩu hoặc file cấu hình nhạy cảm.
- **Input Validation:** Validate chặt chẽ dữ liệu đầu vào từ người dùng (phòng chống SQL Injection, Command/Prompt Injection, XSS, SSRF).
- **Hợp đồng dữ liệu & Type Safety:** Đảm bảo khớp 100% DTO/Schema giữa các dịch vụ; xử lý đầy đủ các trường hợp ngoại lệ `null` / `None` / `undefined`, mảng rỗng hoặc lỗi mạng.

### 2. 🟡 Hiệu Năng & Quản Lý Tài Nguyên (Performance & Resource Management):
- **Quản lý kết nối & I/O:** Luôn đóng toàn bộ kết nối Database, file handle, session I/O sau khi sử dụng (tránh leak connection/memory).
- **Tối ưu truy vấn ORM:** Tránh lỗi N+1 query; đánh index hợp lý cho các trường query thường xuyên; đảm bảo có điều kiện lọc trạng thái hoạt động (ví dụ `is_active == True`).
- **Tối ưu UI:** Hạn chế re-render thừa trong UI components; đảm bảo Type-safe tuyệt đối, cấm lạm dụng kiểu `any` / dynamic types bừa bãi.

### 3. 🟢 Định Dạng & Dọn Rác (Formatting & Clean Code):
- **Dọn debug log:** Loại bỏ toàn bộ log debug tạm (`console.log`, `print` tạm thời).
- **Dọn code thừa:** Xóa sạch dead code, imports thừa và comment rác không còn giá trị.
- **Độ rõ ràng:** Đặt tên biến/hàm rõ nghĩa, viết docstring/comment giải thích thuật toán phức tạp nếu có.

