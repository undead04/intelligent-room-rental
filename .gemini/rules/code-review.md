# Code Review & Quality Checklist

Khi thực hiện review code hoặc trước khi bàn giao một tính năng (tham chiếu quy chuẩn dự án tại [`AGENTS.md`](../../AGENTS.md)):

1. **Security & Validation:**
   - Kiểm tra rò rỉ secret, token, API key, thông tin nhạy cảm.
   - Validate đầy đủ dữ liệu đầu vào từ người dùng (tránh XSS, SQLi, Prompt/Command Injection, SSRF).
2. **Edge Cases & Type Safety:**
   - Xử lý đầy đủ các trường hợp `null`/`None`/`undefined`, mảng rỗng, timeout hoặc lỗi mạng.
   - Đảm bảo khớp 100% kiểu dữ liệu/DTO/Schema theo quy định trong `AGENTS.md`.
3. **Format & Cleanup:**
   - Loại bỏ debug log thừa (`console.log`, `print` tạm), dead code, import thừa và comment rác.

