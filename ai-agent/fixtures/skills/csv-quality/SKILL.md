---
name: csv-quality
description: Kiểm tra chất lượng file CSV danh sách công việc (cột task_id, owner, hours), tính tổng giờ theo người và xác định người quá tải theo ngưỡng giờ người dùng cung cấp bằng script có sẵn, rồi ghi báo cáo Markdown dưới output/. Dùng khi người dùng yêu cầu kiểm tra, rà soát chất lượng dữ liệu CSV công việc, tính tổng giờ theo người hoặc kiểm tra ai bị quá tải.
---

# CSV quality

Kiểm tra chất lượng CSV công việc, tổng giờ theo người và người quá tải bằng script, không tự đếm hay tự cộng bằng mắt.

## Ngưỡng giờ (bắt buộc)

Script luôn cần tham số `--max-hours <ngưỡng>`.

- Lấy ngưỡng **từ yêu cầu của người dùng trong cuộc trò chuyện hiện tại** (ví dụ "ai vượt X giờ" → ngưỡng là X). Truyền đúng giá trị đó vào lệnh, không làm tròn hay đổi đơn vị.
- Nếu người dùng chưa cho ngưỡng (kể cả khi chỉ hỏi "ai quá tải" hoặc "tính tổng giờ theo người"): **hỏi lại ngưỡng và dừng**, chưa chạy script, chưa kết luận ai quá tải.
- Không tự chọn ngưỡng mặc định, không dùng ngưỡng từ cuộc trò chuyện cũ hoặc từ báo cáo cũ trong `output/`.
- Ngưỡng phải là số hữu hạn không âm. Nếu người dùng đưa giá trị khác (âm, chữ...), hỏi lại.

## Chạy script

Dùng tool `bash` (cwd là workspace). Lệnh đầy đủ:

```
python skills/csv-quality/scripts/check_csv.py --input <đường dẫn CSV> --max-hours <ngưỡng>
```

Ví dụ với ngưỡng người dùng đưa là 40: `python skills/csv-quality/scripts/check_csv.py --input data/tasks.csv --max-hours 40`

Không cần đọc source script để chạy. Chỉ đọc `scripts/check_csv.py` khi cần hiểu một hành vi mà phần dưới không mô tả.

## Kiểm tra kết quả

- `exit_code` 0: phân tích thành công. `stdout` là JSON gồm:
  - Thống kê chất lượng (tính trên **toàn bộ** dòng dữ liệu): `row_count`, `missing_owner_count`, `invalid_hours_count`, `duplicate_id_count`, `duplicate_ids`, `issues`.
  - `max_hours`: ngưỡng script đã nhận. Phải bằng ngưỡng người dùng yêu cầu.
  - `hours_by_owner`: tổng giờ theo người, chỉ tính các dòng hợp lệ.
  - `overloaded_owners`: danh sách `{owner, total_hours}` có tổng giờ **lớn hơn** ngưỡng (bằng ngưỡng không phải quá tải). Rỗng nghĩa là không ai quá tải.
  - `excluded_rows`: danh sách `{line, task_id, reasons}` các dòng không được cộng vào tổng giờ.
  - Dữ liệu có lỗi, có dòng bị loại hoặc có người quá tải vẫn là exit 0.
- `exit_code` 1: **lỗi thực thi** (file không tồn tại, thiếu cột bắt buộc, lỗi parse). `exit_code` 2: sai tham số (thiếu hoặc sai `--max-hours`). Đọc `stderr`, báo lỗi cho người dùng. Không đưa ra tổng giờ, người quá tải hay thống kê; không ghi báo cáo như thể đã phân tích thành công.
- `timed_out` true hoặc `ok` false: lệnh không chạy xong; báo lỗi, không suy đoán kết quả.
- Phân biệt rõ **lỗi dữ liệu** (nằm trong `issues`/`excluded_rows`, script vẫn chạy thành công) với **lỗi thực thi** (exit khác 0).

## Quy tắc script dùng để tính tổng giờ

Dùng phần này để giải thích, không tự tính lại:

- `task_id`, `owner`, `hours` được bỏ khoảng trắng đầu/cuối; owner khác hoa/thường là hai người khác nhau.
- Mỗi `task_id` chỉ giữ lần xuất hiện **đầu tiên** trong file; các lần sau bị loại (`duplicate_id`), kể cả khi lần đầu không hợp lệ.
- Chỉ cộng dòng có đúng số trường, `task_id` và `owner` không rỗng, `hours` là số hữu hạn không âm (0 hợp lệ).
- Mã lý do loại dòng: `wrong_field_count` (sai số trường), `missing_task_id` (thiếu task_id), `duplicate_id` (task_id trùng), `missing_owner` (thiếu owner), `invalid_hours` (hours không hợp lệ).

## Viết báo cáo

1. Đọc template `references/report-template.md` trong thư mục skill này, tức `skills/csv-quality/references/report-template.md`.
2. Lấy mọi con số từ JSON của script: ngưỡng từ `max_hours`, tổng giờ từ `hours_by_owner`, người quá tải từ `overloaded_owners`, dòng bị loại từ `excluded_rows`. Mỗi issue ghi line number (header là line 1), cột và mô tả.
3. Ghi rõ tổng giờ chỉ tính trên các dòng hợp lệ và liệt kê từng dòng bị loại kèm **tất cả** lý do.
4. Không sửa file CSV khi người dùng chỉ yêu cầu kiểm tra. Có thể đề xuất cách sửa trong mục khuyến nghị.
5. Ghi báo cáo bằng `write_file` vào đường dẫn người dùng yêu cầu (mặc định `output/csv-quality.md`), rồi trả lời đường dẫn và tóm tắt ngắn (ngưỡng, ai quá tải, số dòng bị loại).
