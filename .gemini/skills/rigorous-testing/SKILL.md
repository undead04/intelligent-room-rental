---
name: rigorous-testing
description: Quy trình viết Unit/Integration Test độc lập, chống gian lận (Anti-Cheating Test). Test phải bám chặt vào yêu cầu nghiệp vụ (SPEC/Requirement), kiểm thử biên (edge cases) và lỗi tiềm ẩn, TUYỆT ĐỐI không viết test xuôi theo code hiện tại.
---

# Skill: Viết Test Nghiêm Ngặt & Chống Gian Lận (Black-Box Testing)

Vấn đề cốt tử của AI khi viết test: **AI thường đọc code vừa viết rồi tự chế ra test case cho vừa vặn với hàm đó để pass 100% (Confirmation Bias).** Khi có lỗi logic ngầm, test vẫn xanh lè nhưng app thực tế thì crash.

Khi kích hoạt skill này, Agent **BẮT BUỘC** tuân thủ quy trình kiểm thử khách quan dưới đây:

---

## 1. Nguyên Tắc Cốt Lõi (Anti-Cheating Principles)
1. **Lấy SPEC làm chân lý (Spec-Driven):** 
   - Test case phải viết dựa trên **tài liệu yêu cầu (`SPEC.md`) và luồng người dùng (User Flow)**, KHÔNG nhìn vào cách code đang triển khai (Black-box testing).
2. **Cấm Mock toàn bộ logic cốt lõi:**
   - Không được mock các hàm xử lý dữ liệu chính rồi tự assert kết quả của mock. State và Store phải được chạy thật để kiểm tra mutation.
3. **Mục tiêu là "Cố tình bẻ gãy code" (Red-Green-Refactor mindset):**
   - Người viết test giỏi là người nghĩ ra các trường hợp làm hàm bị crash hoặc trả về dữ liệu sai, chứ không phải tìm cách làm bài test pass nhanh.

---

## 2. Checklist Bắt Buộc Trong Mọi File Test

Mỗi khi viết test cho một Store, Service hay Component, **PHẢI có đủ 4 nhóm test cases**:

### Nhóm 1: Happy Path (Luồng chuẩn)
- Luồng hoạt động bình thường với dữ liệu hợp lệ.
- Kiểm tra kết quả trả về và state cập nhật đúng như mong đợi.

### Nhóm 2: Boundary & Edge Cases (Dữ liệu biên & Dữ liệu bẩn)
- **Chuỗi rỗng / Khoảng trắng:** Tiêu đề task chỉ có khoảng trắng (`"   "`) $\rightarrow$ Phải báo lỗi hoặc không cho tạo.
- **Null / Undefined:** Gọi hàm với tham số rỗng hoặc thiếu ID.
- **Mảng rỗng:** Xóa task khi cột không có task nào, hoặc kéo thả trong cột rỗng.
- **Dữ liệu cực lớn:** Nhập mô tả 5.000 ký tự, tên cột 500 ký tự.

### Nhóm 3: State Mutation & Race Condition (Tính toàn vẹn của dữ liệu)
- **Thử nghiệm kéo thả / đổi cột:** Chuyển Task từ Cột A sang Cột B $\rightarrow$ Task phải có mặt ở Cột B và **BIẾN MẤT HOÀN TOÀN** khỏi Cột A (không được bị nhân đôi task).
- **Tính bất biến (Immutability):** Đảm bảo mảng gốc trong Store không bị mutate trực tiếp (`state.tasks.push(...)` là cấm).
- **Thao tác dồn dập:** Thêm 3 task liên tiếp trong cùng 1 tick $\rightarrow$ ID có bị trùng nhau không? Cả 3 task có được lưu đủ vào `localStorage` không?

### Nhóm 4: Persistence Test (Lưu trữ)
- Giả lập tải lại trang (F5 / reload): Nạp lại Store từ `localStorage` $\rightarrow$ Dữ liệu có giữ nguyên vẹn cấu trúc không?

---

## 3. Quy Trình Thực Thi:
1. **Bước 1 - Lập danh sách Test Cases:** Đọc `docs/SPEC.md`, liệt kê ra danh sách các kịch bản kiểm thử (kèm kịch bản lỗi biên) trước khi viết code test.
2. **Bước 2 - Viết Test độc lập:** Viết file `.test.ts` / `.spec.tsx`.
3. **Bước 3 - Chạy Test thực tế:** Chạy lệnh `npm test` hoặc `npx vitest run`.
4. **Bước 4 - Xử lý khi Test Fail:**
   - Nếu test fail: ĐỌC LẠI SPEC. Nếu test đúng spec mà code chạy sai $\rightarrow$ **Sửa code trong source, TUYỆT ĐỐI không được sửa tiêu chí của bài test để ép nó pass.**

