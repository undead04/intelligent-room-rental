# 🎯 Quy Chuẩn Viết Spec, Chia Mốc & Triển Khai Tính Năng (Spec & Milestones)

Tài liệu này quy định các nguyên tắc bắt buộc dành cho AI Agent khi lập tài liệu đặc tả kỹ thuật (Spec), chia nhỏ mốc triển khai và thực thi từng mốc tính năng trong dự án Homigo.

---

## 1. 📋 Quy Chuẩn Viết Spec & Chia Mốc Triển Khai (Milestones)

Khi tiếp nhận yêu cầu tính năng mới hoặc đọc file `docs/xxx.md`:

1. **Checklist Bắt Buộc:**
   - Trong tài liệu Spec luôn phải có bảng phân công checklist công việc chi tiết dạng `[ ]` theo từng tầng kiến trúc (`backend`, `crawler`, `ai-agent`, `frontend`).
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
3. **Cách kiểm chứng thực tế:** Hướng dẫn chính xác câu lệnh terminal cần gõ hoặc thao tác trên trình duyệt để người dùng tự tay xác nhận mốc đã chạy ngon lành trước khi chuyển sang mốc tiếp theo.

---

## 3. 🚀 Quy Chuẩn Triển Khai Từng Mốc (`/plan: [MỐC X]`)

Khi người dùng ra lệnh triển khai:  
👉 `"/plan: Chúng ta sẽ triển khai [MỐC X: TÊN MỐC]"`

Agent phải thực hiện theo đúng trình tự sau:
1. **Đọc lại tài liệu liên quan:** Đọc lại spec và các file mã nguồn liên quan trực tiếp đến Mốc X.
2. **Lập bảng Plan chi tiết:** Lập kế hoạch từng bước nhỏ cho riêng Mốc X (qua Artifact hoặc phản hồi trực tiếp).
3. **Kiểm soát phạm vi tuyệt đối (Strict Scope Control):**
   - **CHỈ TẬP TRUNG 100% VÀO PHẠM VI CỦA MỐC X.**
   - **TUYỆT ĐỐI KHÔNG** đụng vào code, schema hay các file thuộc phạm vi của các mốc sau.
4. **Quy trình Git Workflow:**
   - Tạo nhánh tính năng riêng: `git checkout -b feat/<ten-feature>`.
   - Mỗi bước nhỏ hoàn thành chỉ commit ở local: `git commit -m "feat/fix: ..."`.
   - Chạy test kiểm thử tự động pass 100%.
   - Dừng lại hỏi ý kiến người dùng trước khi push và mở Pull Request (Manual PR Gate).
