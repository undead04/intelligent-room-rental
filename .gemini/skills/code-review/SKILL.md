---
name: code-review
description: Tự động rà soát, kiểm tra chất lượng code, tìm bug tiềm ẩn và tối ưu hiệu năng trước khi commit hoặc hoàn thành task (tuân thủ AGENTS.md).
---

# Skill: Code Review

Kích hoạt skill này khi người dùng yêu cầu review code hoặc kiểm tra chất lượng trước khi bàn giao (kết hợp cùng quy chuẩn tại [`.gemini/rules/code-review.md`](../../rules/code-review.md) và [`AGENTS.md`](../../../AGENTS.md)):

## Các bước thực hiện:
1. **Quét thay đổi:** Xem các file vừa sửa đổi hoặc code mới viết trong working tree.
2. **Phân tích theo 3 mức độ:**
   - 🔴 **[Nghiêm trọng]:** Lỗi crash, bảo mật, rò rỉ dữ liệu/secret, sai logic, vi phạm hợp đồng DTO/Schema.
   - 🟡 **[Cảnh báo]:** Đoạn code chạy chậm, re-render thừa, thiếu xử lý ngoại lệ (`null`/`None`/`undefined`), N+1 query.
   - 🟢 **[Gợi ý]:** Clean code, đặt tên biến rõ nghĩa, comment giải thích logic phức tạp.
3. **Đưa ra giải pháp:** Luôn đi kèm đoạn code sửa mẫu cụ thể thay vì chỉ nhận xét lý thuyết.

