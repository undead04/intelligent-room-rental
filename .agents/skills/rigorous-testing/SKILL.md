---
name: rigorous-testing
description: Quy trình viết Unit/Integration Test độc lập, chống gian lận (Anti-Cheating Black-Box Test). Test phải bám chặt vào tài liệu đặc tả (SPEC/DTO/Contract), kiểm thử biên (edge cases) và lỗi tiềm ẩn, TUYỆT ĐỐI không viết test xuôi theo code hiện tại.
---

# Skill: Viết Test Nghiêm Ngặt & Chống Gian Lận (Black-Box Testing)

Vấn đề cốt tử của AI khi viết test: **AI thường đọc code vừa viết rồi tự chế ra test case cho vừa vặn với hàm đó để pass 100% (Confirmation Bias).** Khi có lỗi logic ngầm, test vẫn xanh nhưng hệ thống thực tế lại lỗi.

Khi kích hoạt skill này, Agent **BẮT BUỘC** tuân thủ quy trình kiểm thử khách quan dưới đây (áp dụng cho mọi dự án, tham chiếu Tech Stack và lệnh chạy test tại [`AGENTS.md`](../../../AGENTS.md)):

---

## 1. Nguyên Tắc Cốt Lõi (Anti-Cheating Principles)
1. **Lấy SPEC & Contract làm chân lý (Spec-Driven):** 
   - Test case phải viết dựa trên **tài liệu đặc tả (`docs/`), Schema/DTO và luồng nghiệp vụ**, KHÔNG nhìn vào cách hàm đang triển khai nội bộ để nương theo (Black-box testing).
2. **Cấm Mock toàn bộ logic cốt lõi:**
   - Không được mock chính hàm/service cần test rồi tự assert kết quả của mock. Chỉ mock các phụ thuộc ngoại vi (external API bên thứ ba trả phí) khi thật sự cần thiết.
3. **Mục tiêu là "Cố tình bẻ gãy code" (Adversarial QA mindset):**
   - Người viết test giỏi là người nghĩ ra các trường hợp biên làm hàm văng lỗi hoặc trả về dữ liệu sai lệch, chứ không phải tìm cách viết bài test dễ dãi để pass nhanh.

---

## 2. Checklist 4 Nhóm Test Cases Bắt Buộc

Mỗi khi viết test cho một Module, Service, API, Pipeline hay UI Component, **BẮT BUỘC phải bao phủ đủ 4 nhóm**:

### Nhóm 1: Happy Path (Luồng chuẩn)
- Thực thi với bộ dữ liệu đầu vào hợp lệ tiêu chuẩn và đa dạng các phân loại/trạng thái hợp lệ.
- Kiểm tra cấu trúc đầu ra (Schema/DTO), kiểu dữ liệu, giá trị tính toán và trạng thái cập nhật đúng 100% theo đặc tả.

### Nhóm 2: Boundary & Edge Cases (Dữ liệu biên & Dữ liệu bẩn)
- **Chuỗi rỗng / Khoảng trắng / Ký tự đặc biệt:** `""`, `"   "`, Unicode đặc biệt, ký tự điều khiển.
- **Null / None / Undefined / Thiếu trường bắt buộc:** Gọi hàm hoặc API với tham số thiếu hoặc `null`/`None`.
- **Biên số học & Tập hợp rỗng:** Giá trị `0`, số âm, ngưỡng tối thiểu/tối đa (`min`/`max`), mảng/danh sách rỗng `[]`, object rỗng `{}`.
- **Dữ liệu cực lớn hoặc ngoài vùng hợp lệ (Out-of-Range):** Payload lớn, tọa độ/giá trị vượt ngưỡng cho phép.

### Nhóm 3: State Mutation, Immutability & Concurrency (Tính toàn vẹn trạng thái)
- **Tính bất biến (Immutability):** Đảm bảo hàm xử lý không vô tình làm biến đổi (mutate) object/dictionary/list đầu vào của caller nếu không được phép.
- **Chống rò rỉ trạng thái / dữ liệu (Zero Leakage):** Đảm bảo kết quả giữa các lần gọi hoặc giữa tập train/test không bị lẫn trạng thái ngầm.
- **Thao tác lặp / Đồng thời (Idempotency & Race Condition):** Gọi lặp lại hoặc cập nhật liên tiếp không sinh bản ghi trùng lặp hoặc hỏng state.

### Nhóm 4: Persistence & Integration Consistency (Lưu trữ & Đồng bộ dữ liệu)
- Kiểm tra chu trình đọc/ghi thực tế qua Database, Cache, File Artifact hoặc State Store của dự án: dữ liệu sau khi lưu và nạp lại phải bảo toàn đúng cấu trúc, kiểu dữ liệu và ràng buộc toàn vẹn.

---

## 3. Quy Trình Thực Thi:
1. **Bước 1 — Lập danh sách Test Cases:** Đọc tài liệu Spec và `AGENTS.md`, liệt kê các kịch bản kiểm thử theo đủ 4 nhóm trên trước khi viết code test.
2. **Bước 2 — Viết Test độc lập:** Tạo/cập nhật file test theo đúng framework kiểm thử của dự án quy định trong `AGENTS.md`.
3. **Bước 3 — Chạy Test thực tế:** Thực thi đúng câu lệnh chạy test tại Mục 6 của [`AGENTS.md`](../../../AGENTS.md).
4. **Bước 4 — Xử lý khi Test Fail:**
   - Nếu test fail: ĐỌC LẠI SPEC. Nếu bài test phản ánh đúng yêu cầu nghiệp vụ mà code chạy sai $\rightarrow$ **Bắt buộc sửa code trong source, TUYỆT ĐỐI CẤM hạ tiêu chuẩn hoặc sửa assertion của bài test để ép pass.**

