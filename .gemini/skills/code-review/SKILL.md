---
name: code-review
description: Tự động rà soát, kiểm tra chất lượng code, tìm bug tiềm ẩn và tối ưu hiệu năng trước khi commit hoặc hoàn thành task.
---

# Skill: Code Review

Kích hoạt skill này khi người dùng yêu cầu review code hoặc kiểm tra chất lượng trước khi bàn giao:

## Các bước thực hiện:
1. **Quét thay đổi:** Xem các file vừa sửa đổi hoặc code mới viết.
2. **Phân tích theo 3 mức độ:**
   - 🔴 **[Nghiêm trọng]:** Lỗi crash, bảo mật, rò rỉ dữ liệu, logic sai.
   - 🟡 **[Cảnh báo]:** Đoạn code chạy chậm, re-render thừa, thiếu xử lý ngoại lệ (null/undefined).
   - 🟢 **[Gợi ý]:** Clean code, đặt tên biến, comment giải thích.
3. **Đưa ra giải pháp:** Luôn đi kèm đoạn code sửa mẫu cụ thể thay vì chỉ nhận xét lý thuyết.

