---
name: plan-and-execute
description: Quy chuẩn khi người dùng yêu cầu lập kế hoạch (plan), chia mốc (milestones), triển khai tính năng mới hoặc gõ /plan. Tự động đọc tài liệu docs/, đối chiếu kiến trúc hệ thống, tạo Implementation Plan Artifact kèm cờ RequestFeedback (nút Proceed) và thực thi trực tiếp theo kiến trúc Orchestrator (Planner -> Executor + rigorous-testing) tiết kiệm token.
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
- **Nội dung bắt buộc trong từng bước của Plan:**
  - Thứ tự các bước rõ ràng kèm **Files / Symbols cần tạo hoặc chỉnh sửa**.
  - **Edge cases / Pitfalls cần tránh** (schema, backward compatibility, zero/null checks).
  - **Lệnh Verification cụ thể** (trích từ [`docs/architecture/tech-stack.md`](../../../docs/architecture/tech-stack.md)).

---

## 2. Quy Trình Thực Thi Sau Khi Người Dùng Bấm PROCEED (Orchestrator Execution Protocol)

> [!IMPORTANT]
> **THỰC THI TINH GỌN TRONG PHIÊN CHÍNH:**
> Trong chế độ Orchestrator (Planner $\rightarrow$ Executor), Agent trực tiếp triển khai code và kiểm thử theo Plan đã duyệt; **không gọi lặp `invoke_subagent` tuần tự 3 bước** trừ khi người dùng chủ động yêu cầu `/teamwork` hoặc cần khảo sát độc lập (*context isolation*).

### Trình tự 3 giai đoạn trong phiên chính:
1. **Giai đoạn 1 — Lập trình & Self-Healing:** Thực thi tuần tự các bước trong Plan (hoặc bàn giao qua `exit_plan_mode`), tuân thủ Tech Stack, Scope Control và tự đọc log terminal sửa lỗi đến khi sạch.
2. **Giai đoạn 2 — Kiểm thử Độc Lập (`rigorous-testing`):** Áp dụng trực tiếp skill [`.agents/skills/rigorous-testing/SKILL.md`](../rigorous-testing/SKILL.md) viết Black-box test bao phủ đủ 4 nhóm (*Happy Path, Boundary/Edge, State Mutation/Concurrency, Persistence*) và chạy lệnh kiểm thử chuẩn tại [`docs/architecture/tech-stack.md`](../../../docs/architecture/tech-stack.md) đạt **100% pass**.
3. **Giai đoạn 3 — Đồng bộ Kiến trúc & Manual Commit Gate:** Cập nhật `docs/architecture/` nếu có thay đổi schema/DTO/luồng thuật toán, báo cáo kết quả và dừng tại Waiting Gate chờ người dùng duyệt.

---

## 3. Hoàn Tất Mốc & Bàn Giao

1. **Cập nhật Tiến Độ:** Chuyển các đầu việc từ `[ ]` $\rightarrow$ `[x]` trong tài liệu đặc tả / spec / checklist.
2. **Đồng bộ Kiến trúc:** Cập nhật `docs/architecture/` nếu có thay đổi schema, DTO, luồng xử lý hoặc dependencies.
3. **Cổng Chờ Nghiệm Thu (Waiting Gate):** Kích hoạt skill `github-workflow` — dừng lại để người dùng tự test, **TUYỆT ĐỐI CẤM tự ý chạy `git commit`** khi người dùng chưa xác nhận.
