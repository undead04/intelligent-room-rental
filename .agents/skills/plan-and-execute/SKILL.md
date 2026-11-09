---
name: plan-and-execute
description: Quy chuẩn bắt buộc khi người dùng yêu cầu lập kế hoạch (plan), chia mốc (milestones), triển khai tính năng mới hoặc gõ /plan. Tự động đọc tài liệu docs/, đối chiếu kiến trúc hệ thống, tạo Implementation Plan Artifact kèm cờ RequestFeedback (nút Proceed), phân công 3 Sub-Agents rõ ràng ([codebase-researcher], [core-developer], [quality-tester]), và cam kết kích hoạt invoke_subagent tuần tự khi người dùng bấm Proceed.
---

# Skill: Lập Kế Hoạch & Triển Khai Tính Năng (Plan & Execution Protocol)

Kích hoạt skill này mỗi khi người dùng:
- Yêu cầu lập kế hoạch / lập plan / triển khai tính năng mới.
- Ra lệnh `/plan: [MỐC X]`.
- Yêu cầu chia nhỏ công việc thành các mốc (Milestones).

---

## 1. Quy Trình Lập Kế Hoạch (Planning Protocol)

Khi người dùng yêu cầu lập kế hoạch hoặc gõ `/plan`:

### BƯỚC 1: Khảo Sát Codebase & Đối Chiếu Tài Liệu Đặc Tả (`docs/`)
1. **Đọc kỹ `AGENTS.md`:** Nắm vững Tech stack, quy tắc code, bảng lệnh chuẩn của các dịch vụ/modules.
2. **Quét tài liệu kiến trúc & đặc tả tương ứng trong `docs/`:**
   - **Kiến trúc tổng thể & Modules:** `docs/architecture/tech-stack.md`, `docs/architecture/modules/`, `docs/architecture/data-models.md`, `docs/architecture/design-system.md`.
   - **Khế ước giao tiếp:** `docs/contracts/` (API Specs, Schema/DTO giữa các services).
   - **Tính năng mới:** `docs/features/` (đối chiếu các spec trong `backlog/`, `in-progress/`, `released/`).
   - **Sự cố & bảo trì:** `docs/maintenance/` (nếu là task sửa bug, đối chiếu `docs/maintenance/in-progress/` hoặc các issue đã giải quyết trong `resolved/`).
   - **Đối chiếu khoảng trống kỹ thuật & phạm vi:** Xác định chính xác các API endpoint, Database Model/Schema, Core Logic Node hoặc Frontend Component cần phát triển/sửa đổi.

### BƯỚC 2: 3 Nguyên Tắc Bắt Buộc Khi Chia Mốc
1. **Working Software (Phần mềm chạy được thực tế):**
   - Mỗi mốc sau khi hoàn thành BẮT BUỘC phải là một phiên bản chạy thử được ngay trên trình duyệt hoặc terminal (lát cắt dọc hoàn chỉnh - Vertical Slice).
   - ❌ **CẤM:** Chia mốc cụt lủn theo chiều ngang (ví dụ: Mốc 1 chỉ tạo file type/schema, Mốc 2 mới viết logic, Mốc 3 mới test).
2. **One Session Scope (Gói gọn trong 1 phiên chat):**
   - Mỗi mốc chỉ gói gọn lượng việc vừa đủ để code và kiểm thử hoàn chỉnh trong vòng 1 phiên chat duy nhất.
   - Khống chế khối lượng: **Tối đa 4 - 6 files code** trong một mốc để tránh cạn context window.
3. **Tiêu Chí Nghiệm Thu Rõ Ràng (Acceptance Criteria):**
   - Mỗi mốc bắt buộc phải nêu rõ đủ 3 nội dung:
     + Mục tiêu cụ thể của mốc: Giải quyết bài toán gì?
     + Danh sách file chính sẽ tạo hoặc chỉnh sửa.
     + Cách kiểm chứng thực tế: Câu lệnh terminal cụ thể (theo Bảng lệnh chuẩn trong `AGENTS.md`) hoặc thao tác trên giao diện để người dùng tự tay xác nhận.

### BƯỚC 3: Tạo Implementation Plan Artifact (Kèm Nút Proceed)
- Viết kế hoạch vào file Artifact trong thư mục artifact với `ArtifactMetadata`:
  ```json
  {
    "Summary": "Kế hoạch chi tiết triển khai tính năng theo từng mốc",
    "UserFacing": true,
    "RequestFeedback": true
  }
  ```
- **Bắt buộc phân công Sub-Agents vào từng bước của Plan:**
  - `[codebase-researcher]`: Khảo sát, đọc codebase, tra cứu tài liệu Context7 MCP, đối chiếu spec `docs/` và phân tích rủi ro.
  - `[core-developer]`: Viết code tính năng, sửa bug, tự đọc log sửa lỗi (Self-healing), tuân thủ tech stack và cập nhật docs/architecture/.
  - `[quality-tester]`: Viết Black-box test (4 nhóm test cases) và chạy kiểm thử.

---

## 2. Quy Trình Thực Thi Sau Khi Người Dùng Bấm PROCEED (Execution Protocol)

> [!IMPORTANT]
> **CAM KẾT THỰC THI (Sub-Agent Allocation Gate):**
> Khi người dùng bấm nút **Proceed**, Agent chính **BẮT BUỘC phải gọi tool `invoke_subagent`** để triệu hồi tuần tự các Sub-agents chạy ngầm theo đúng phân công trong Plan, tuyệt đối không được tự ý ôm đồm làm một mình!

### Trình tự 3 bước:
1. **Triệu hồi `codebase-researcher`:**
   - Dùng `invoke_subagent` với `TypeName: "codebase-researcher"`, `Role: "Codebase Researcher"`.
   - Prompt: Khảo sát các module/file liên quan trong Mốc X, đối chiếu spec `docs/architecture/`, `docs/contracts/` và `docs/features/` (hoặc `docs/maintenance/`), báo cáo rủi ro kỹ thuật.
2. **Triệu hồi `core-developer`:**
   - Dùng `invoke_subagent` với `TypeName: "core-developer"`, `Role: "Core Developer"`.
   - Prompt: Nhận kết quả từ researcher, viết code theo đúng Tech Stack, tự đọc log terminal sửa lỗi (Self-healing).
3. **Triệu hồi `quality-tester`:**
   - Dùng `invoke_subagent` với `TypeName: "quality-tester"`, `Role: "Quality Tester"`.
   - Prompt: Viết test Black-box theo Spec bao phủ đủ 4 nhóm test cases, chạy lệnh test kiểm chứng pass 100%.

---

## 3. Hoàn Tất Mốc & Bàn Giao

1. **Cập nhật Tiến Độ:** Chuyển các đầu việc từ `[ ]` $\rightarrow$ `[x]` trong tài liệu đặc tả / spec / checklist.
2. **Đồng bộ Kiến trúc:** Cập nhật `docs/architecture/` nếu có thay đổi schema, DTO, luồng xử lý hoặc dependencies.
3. **Cổng Chờ Nghiệm Thu (Waiting Gate):** Kích hoạt skill `github-workflow` — dừng lại để người dùng tự test, **TUYỆT ĐỐI CẤM tự ý chạy `git commit`** khi người dùng chưa xác nhận.
