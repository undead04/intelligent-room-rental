---
name: code-review
description: Tự động rà soát, kiểm tra chất lượng code, tìm bug tiềm ẩn và tối ưu hiệu năng trước khi commit hoặc hoàn thành task (tuân thủ AGENTS.md).
---

# Skill: Code Review

Kích hoạt skill này khi người dùng yêu cầu review code hoặc kiểm tra chất lượng trước khi bàn giao (kết hợp cùng quy chuẩn tại [`.agents/rules/code-review.md`](../../rules/code-review.md) và [`AGENTS.md`](../../../AGENTS.md)):

## Các bước thực hiện:
1. **Quét thay đổi:** Xem các file vừa sửa đổi hoặc code mới viết trong working tree (`git diff` hoặc file vừa tạo).
2. **Phân tích theo 3 mức độ:**
   - 🔴 **[Nghiêm trọng]:** Lỗi crash/panic, rò rỉ secret/API key, sai logic nghiệp vụ/ràng buộc cốt lõi, vi phạm hợp đồng Interface/DTO giữa các modules/services, SQL Injection / Command/Prompt Injection, mutate state trực tiếp.
   - 🟡 **[Cảnh báo Hiệu Năng & Kiến Trúc]:**
     - Rò rỉ tài nguyên / kết nối Database (thiếu đóng session, unclosed connection/file handle).
     - N+1 query trong ORM, thiếu index trên các trường query thường xuyên hoặc thiếu bộ lọc trạng thái active/soft-delete.
     - Re-render thừa trong UI components, thiếu xử lý ngoại lệ `null`/`None`/`undefined`.
     - Thiếu kiểu dữ liệu Type-safe, lạm dụng `any` / dynamic types bừa bãi.
   - 🟢 **[Gợi ý]:** Clean code, đặt tên biến/hàm rõ nghĩa, comment giải thích thuật toán phức tạp, dọn dead code / imports thừa.
3. **Đưa ra giải pháp:** Luôn đi kèm đoạn code sửa mẫu cụ thể thay vì chỉ nhận xét lý thuyết suông.
