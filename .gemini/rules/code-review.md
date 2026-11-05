# Code Review & Quality Checklist

Khi thực hiện review code hoặc trước khi bàn giao một tính năng lớn:

1. **Security & Validation:**
   - Kiểm tra rò rỉ secret, token, key.
   - Validate đầy đủ dữ liệu đầu vào từ người dùng (tránh XSS, SQLi, injection).
2. **Edge Cases:**
   - Xử lý các trường hợp null, undefined, mảng rỗng, dữ liệu tải chậm hoặc timeout.
3. **Format & Cleanup:**
   - Loại bỏ `console.log` thừa, code thừa (dead code), comment rác.

