# 🛠️ Sổ Tay Kiểm Toán & Quản Lý Sự Cố (Bug & Fix Management)

Thư mục này là **Sổ Tay Kiểm Toán Kỹ Thuật (Post-mortem & Issue Tracking Hub)** của dự án. Mọi sự cố logic phức tạp, bug bảo mật, hoặc kế hoạch tối ưu kiến trúc đều phải được đánh mã số định danh và lưu trữ tại đây theo vòng đời rõ ràng.

---

## 1. 🔄 Vòng Đời Xử Lý Sự Cố (Issue Lifecycle)

```text
[ PHÁT HIỆN BUG / SỰ CỐ ]
           │
           ▼
[ 1. docs/fix/in-progress/ ]   ─── Đang phân tích nguyên nhân gốc rễ (RCA) & triển khai fix
           │
           ▼
[ 2. docs/fix/resolved/ ]      ─── Đã fix xong, test pass 100%, ghi lại bài học & đóng issue
```

---

## 2. 📋 Bảng Theo Dõi Sự Cố (Issue Tracker Board)

| Mã Issue | Tiêu Đề Sự Cố | Mức Độ | Module Ảnh Hưởng | Trạng Thái | File Chi Tiết |
| :---: | :--- | :---: | :--- | :---: | :--- |
| `ISSUE-0001` | Lỗi Bounding Box, thiếu đa loại phòng & lọt Sleepbox | 🔴 CRITICAL | `backend`, `ai-agent` | 🟡 `IN_PROGRESS` | [`in-progress/ISSUE-0001-core-eval-architecture-fixes.md`](./in-progress/ISSUE-0001-core-eval-architecture-fixes.md) |

---

## 3. 📝 Quy Trình Tạo Issue Mới
Khi phát hiện một bug lớn hoặc lỗi logic kiến trúc:
1. Copy mẫu từ [`TEMPLATE.md`](./TEMPLATE.md) vào thư mục `docs/fix/in-progress/`.
2. Đặt tên file theo định dạng: `ISSUE-[SỐ_THỨ_TỰ]-[ten-ngan-gon].md` (ví dụ: `ISSUE-0002-memory-leak-crawler.md`).
3. Điền đủ 4 phần: Triệu chứng $\rightarrow$ Phân tích nguyên nhân gốc rễ (RCA) $\rightarrow$ Phương án sửa tổng quát $\rightarrow$ Kịch bản test kiểm chứng.
4. Cập nhật thêm 1 dòng vào bảng theo dõi ở Mục 2 của file này.
5. Sau khi test pass và người dùng duyệt nghiệm thu: Di chuyển file từ `in-progress/` sang `resolved/`.
