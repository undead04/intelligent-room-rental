---
name: db-migration
description: Quy trình thiết kế, viết script di chuyển (migration), cập nhật cấu trúc bảng (schema) và rollback an toàn cho cơ sở dữ liệu quan hệ (PostgreSQL, MySQL, SQLite).
---

# Skill: Database Migration An Toàn & Không Mất Dữ Liệu

Kích hoạt skill này khi người dùng yêu cầu:
- Thêm/sửa/xóa cột trong bảng.
- Tạo bảng mới, đánh index tối ưu truy vấn hoặc tạo foreign key.
- Chạy cập nhật dữ liệu (data migration).

---

## 4 BƯỚC TRIỂN KHAI MIGRATION CHUẨN DOANH NGHIỆP:

### BƯỚC 1: Phân Tích & Viết Script Ra File Trước (KHÔNG chạy trực tiếp)
1. Xác định thay đổi schema theo yêu cầu.
2. Viết file migration có đánh số thứ tự hoặc timestamp (ví dụ: `migrations/001_add_status_to_tasks.sql`).
3. Trong file migration, **BẮT BUỘC** phải có 2 phần:
   - **`-- UP MIGRATION`**: Câu lệnh thực hiện thay đổi mới.
   - **`-- DOWN MIGRATION (ROLLBACK)`**: Câu lệnh hoàn tác lại trạng thái cũ nếu bước Up gặp lỗi.

*Ví dụ cấu trúc chuẩn:*
```sql
-- UP
ALTER TABLE tasks ADD COLUMN priority VARCHAR(20) DEFAULT 'medium';
CREATE INDEX idx_tasks_priority ON tasks(priority);

-- DOWN (Rollback)
DROP INDEX IF EXISTS idx_tasks_priority;
ALTER TABLE tasks DROP COLUMN IF EXISTS priority;
```

### BƯỚC 2: Kiểm Tra Ảnh Hưởng Dữ Liệu (Impact Assessment)
- Thêm cột `NOT NULL` vào bảng đã có sẵn dữ liệu: Bắt buộc phải có giá trị mặc định (`DEFAULT`) hoặc chia làm 3 bước để tránh khóa bảng (table lock) làm sập hệ thống.
- Đổi kiểu dữ liệu của cột: Phải dùng mệnh đề `USING ...` để chuyển đổi an toàn (ví dụ: `ALTER COLUMN age TYPE INT USING age::integer`).

### BƯỚC 3: Yêu Cầu Người Dùng Xác Nhận (Confirmation Gate)
Trước khi thực thi script migration, Agent **PHẢI** hiển thị tóm tắt và dừng lại hỏi:
> *"Em vừa chuẩn bị xong script migration `xxx.sql`. Thao tác này sẽ [Thêm cột X / Tạo bảng Y]. Anh xem qua nội dung script bên trên đã đúng ý chưa để em tiến hành chạy?"*
👉 **Chỉ khi người dùng gõ "Đồng ý" hoặc "Chạy đi" thì mới được phép thực thi.**

### BƯỚC 4: Chạy Trong Transaction & Kiểm Chứng
1. Bọc câu lệnh trong `BEGIN; ... COMMIT;`.
2. Kiểm tra lại schema sau khi chạy (`\d tablename` hoặc query information_schema) để đảm bảo cấu trúc mới đã được cập nhật chính xác.
3. Nếu xảy ra lỗi: Tự động chạy lệnh `ROLLBACK;` và báo lỗi chi tiết, không để database rơi vào trạng thái lấp lửng.

