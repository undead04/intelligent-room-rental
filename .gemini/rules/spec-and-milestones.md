# 🎯 Quy Chuẩn Viết Spec, Chia Mốc & Triển Khai Tính Năng (Spec & Milestones)

Tài liệu này quy định các nguyên tắc bắt buộc dành cho AI Agent khi lập tài liệu đặc tả kỹ thuật (Spec), chia nhỏ mốc triển khai và thực thi từng mốc tính năng trong dự án (tham chiếu bối cảnh cụ thể tại [`AGENTS.md`](../../AGENTS.md)).

---

## 1. 📋 Quy Chuẩn Viết Spec & Chia Mốc Triển Khai (Milestones)

Khi tiếp nhận yêu cầu tính năng mới hoặc đọc tài liệu đặc tả trong `docs/`:

1. **Checklist Bắt Buộc Để Theo Dõi Tiến Độ (Progress Tracking Checklist):**
   - Trong tài liệu Spec luôn phải có bảng phân công checklist công việc chi tiết dạng `[ ]` theo từng tầng kiến trúc / module được quy định trong [`AGENTS.md`](../../AGENTS.md).
   - **Cập nhật trạng thái liên tục:** Mỗi khi một đầu việc hoặc một mốc hoàn thành, Agent phải cập nhật chuyển `[ ]` thành `[x]` ngay trong tài liệu Spec để người dùng và các phiên làm việc sau nhìn vào là biết chính xác:
     + Việc nào đã làm xong (`[x]`).
     + Dự án đang làm tới đâu / tiến độ hiện tại.
     + Còn lại những việc nào chưa làm (`[ ]`).
2. **Quy Tắc Cổng Phê Duyệt (Milestone Gate):**
   - **TUYỆT ĐỐI CHƯA ĐƯỢC VIẾT CODE NGAY.**
   - Agent phải xuất bảng danh sách các **Mốc triển khai (Milestones) tuần tự** ra trước để người dùng xem xét và bấm duyệt.

---

## 2. ⚡ 3 Yêu Cầu Bắt Buộc Khi Chia Mốc

Khi chia nhỏ tính năng thành các mốc, Agent bắt buộc phải tuân thủ 3 nguyên tắc:

### 2.1. Quy tắc "Working Software" (Phần mềm chạy được thực tế)
- Mỗi mốc sau khi hoàn thành **BẮT BUỘC phải là một phiên bản chạy thử được ngay** trên trình duyệt hoặc terminal (lát cắt dọc hoàn chỉnh - Vertical Slice).
- ❌ **CẤM:** Chia mốc cụt lủn theo chiều ngang (ví dụ: Mốc 1 chỉ tạo file type/schema, Mốc 2 mới viết logic, Mốc 3 mới test).

### 2.2. Quy tắc "One Session Scope" (Gói gọn trong 1 phiên chat)
- Mỗi mốc chỉ gói gọn lượng việc vừa đủ để code và kiểm thử hoàn chỉnh trong vòng **1 phiên chat duy nhất**.
- Khống chế khối lượng: **Tối đa 4 - 6 files code** trong một mốc để tránh cạn context window và đảm bảo độ tập trung.

### 2.3. Tiêu Chí Nghiệm Thu Rõ Ràng (Acceptance Criteria)
Mỗi mốc được chia ra **BẮT BUỘC** phải nêu rõ đủ 3 nội dung:
1. **Mục tiêu của mốc:** Giải quyết cụ thể bài toán gì?
2. **Các file chính sẽ tạo/sửa:** Liệt kê rõ đường dẫn file.
3. **Cách kiểm chứng thực tế:** Hướng dẫn chính xác câu lệnh terminal cần gõ (theo bảng lệnh trong `AGENTS.md`) hoặc thao tác trên giao diện để người dùng tự tay xác nhận mốc đã chạy ngon lành trước khi chuyển sang mốc tiếp theo.

### 2.4. Quy Tắc Phân Công Sub-Agents Vào Plan (Sub-Agent Allocation Gate)
- Mọi bản kế hoạch triển khai (Implementation Plan Artifact có nút **Proceed**) **BẮT BUỘC phải gắn thẻ danh tính Sub-agent phụ trách cho từng bước**:
  + `[codebase-researcher]`: Khảo sát, đọc codebase, tra cứu tài liệu Context7 MCP.
  + `[core-developer]`: Viết code tính năng, tự đọc log sửa lỗi (Self-healing).
  + `[quality-tester]`: Viết Black-box test (4 nhóm test cases) và chạy kiểm thử.
- **Cam kết thực thi khi bấm Proceed:** Khi người dùng bấm nút **Proceed**, Agent chính **BẮT BUỘC phải kích hoạt tool `invoke_subagent`** để triệu hồi tuần tự các Sub-agents chạy ngầm theo đúng phân công trong Plan, tuyệt đối không được tự ý ôm đồm làm một mình.

---

## 3. 🚀 Quy Chuẩn Triển Khai Từng Mốc (`/plan: [MỐC X]`)

Khi người dùng ra lệnh triển khai:  
👉 `"/plan: Chúng ta sẽ triển khai [MỐC X: TÊN MỐC]"`

Agent phải thực hiện theo đúng trình tự sau:
1. **Đọc lại tài liệu liên quan:** Đọc lại spec, `AGENTS.md`, `docs/architecture/` và các file mã nguồn liên quan trực tiếp đến Mốc X.
2. **Lập bảng Implementation Plan (Artifact) phân công Sub-Agents:**
   - Tạo file kế hoạch triển khai kèm cờ `RequestFeedback: true` để người dùng duyệt qua nút **Proceed**.
   - **Bắt buộc phân công rõ danh tính Sub-Agent trong từng bước:** `[codebase-researcher]` (khảo sát), `[core-developer]` (viết code), `[quality-tester]` (kiểm thử). Khi người dùng bấm **Proceed**, Agent chính bắt buộc phải gọi đúng tool `invoke_subagent` theo kế hoạch, không được tự ý làm một mình.
3. **Kiểm soát phạm vi tuyệt đối (Strict Scope Control):**
   - **CHỈ TẬP TRUNG 100% VÀO PHẠM VI CỦA MỐC X.**
   - **TUYỆT ĐỐI KHÔNG** đụng vào code, schema hay các file thuộc phạm vi của các mốc sau.
4. **Đồng bộ Tài liệu Kiến trúc (`docs/architecture/`):**
   - Nếu Mốc X có thay đổi đến Database Schema, DTO/Contract, luồng xử lý cốt lõi, cấu trúc module hoặc dependencies, bắt buộc cập nhật ngay vào `docs/architecture/` trước khi đóng mốc.
5. **Cập nhật tiến độ Spec:** Chuyển các đầu việc hoàn thành từ `[ ]` $\rightarrow$ `[x]` trong tài liệu đặc tả.
6. **Lưu trữ & Bàn giao:** Kích hoạt chuyên biệt skill [`.gemini/skills/github-workflow/SKILL.md`](../skills/github-workflow/SKILL.md) để dừng lại chờ người dùng nghiệm thu (Waiting Gate) và chỉ thực hiện commit/push/merge khi có lệnh.

