---
name: csv-quality
description: Kiểm tra chất lượng file CSV danh sách công việc (cột task_id, owner, hours), tính tổng giờ theo người và xác định người quá tải theo ngưỡng giờ người dùng cung cấp bằng script có sẵn, rồi ghi báo cáo Markdown dưới output/. Dùng khi người dùng yêu cầu kiểm tra, rà soát chất lượng dữ liệu CSV công việc, tính tổng giờ theo người hoặc kiểm tra ai bị quá tải, ví dụ "Kiểm tra data/workload.csv, người nào vượt 8 giờ? Ghi báo cáo vào output/workload.md". Phải đọc skill này TRƯỚC khi mở hoặc đọc bất kỳ file CSV nào.
---

# CSV quality

Hướng dẫn kiểm tra chất lượng CSV công việc, tính tổng giờ theo người và tìm người quá tải bằng script; không tự đếm hay tự cộng bằng mắt.

## Nguyên tắc bắt buộc (đọc trước khi làm bất cứ việc gì)

- Đọc xong skill này rồi mới được đụng vào file dữ liệu.
- KHÔNG mở file CSV bằng `cat`, `head`, `tail`, `less`, `read_file` hay bất kỳ tool đọc file nào, kể cả để "xem thử cấu trúc". File có thể rất lớn và sẽ làm tràn context. Script đã tự đọc, kiểm tra cột và báo lỗi.
- Mọi thông tin về dữ liệu (số dòng, lỗi, tổng giờ, người quá tải) chỉ lấy từ JSON của script.
- Chỉ khi người dùng hỏi riêng về một dòng cụ thể mới được xem tối đa vài dòng đó (theo line number trong `issues`/`excluded_rows`), không đọc cả file.

## Các bước

1. Lấy ngưỡng giờ và đường dẫn file từ yêu cầu của người dùng trong cuộc trò chuyện hiện tại (ví dụ "người nào vượt 8 giờ" → ngưỡng là 8).
   - Nếu chưa có ngưỡng (kể cả khi chỉ hỏi "ai quá tải" hoặc "tính tổng giờ theo người"): hỏi lại ngưỡng và dừng; chưa chạy script, chưa kết luận ai quá tải.
   - Ngưỡng phải là số hữu hạn không âm. Nếu người dùng đưa giá trị khác (âm, chữ...), hỏi lại.
   - Không tự chọn ngưỡng mặc định, không dùng ngưỡng từ cuộc trò chuyện cũ hoặc từ báo cáo cũ trong `output/`. Truyền đúng giá trị người dùng đưa, không làm tròn hay đổi đơn vị.
2. Chạy script bằng tool `bash` (cwd là workspace), đây là lần đầu tiên file CSV được động tới:
```
   python skills/csv-quality/scripts/check_csv.py --input <đường dẫn CSV> --max-hours <ngưỡng>
```
   Ví dụ với yêu cầu "Kiểm tra data/workload.csv, người nào vượt 8 giờ?": `python skills/csv-quality/scripts/check_csv.py --input data/workload.csv --max-hours 8`. Không cần đọc source script; chỉ đọc `scripts/check_csv.py` khi cần hiểu một hành vi không được mô tả ở đây.
3. Kiểm tra kết quả chạy:
   - `exit_code` 0: phân tích thành công, `stdout` là JSON. Dữ liệu có lỗi, có dòng bị loại hoặc có người quá tải vẫn là exit 0.
   - `exit_code` 1 (file không tồn tại, thiếu cột bắt buộc, lỗi parse) hoặc 2 (thiếu/sai `--max-hours`): đọc `stderr`, báo lỗi và dừng; không đưa ra tổng giờ, người quá tải hay thống kê, không ghi báo cáo như thể đã phân tích thành công. Không tự mở CSV để "tìm lỗi".
   - `timed_out` true hoặc `ok` false: báo lỗi và dừng, không suy đoán kết quả.
   - Phân biệt lỗi dữ liệu (nằm trong `issues`/`excluded_rows`) với lỗi thực thi (exit khác 0).
4. Đọc JSON và đối chiếu:
   - `max_hours` phải bằng ngưỡng người dùng yêu cầu.
   - Thống kê chất lượng (tính trên toàn bộ dòng dữ liệu): `row_count`, `missing_owner_count`, `invalid_hours_count`, `duplicate_id_count`, `duplicate_ids`, `issues`.
   - `hours_by_owner`: tổng giờ theo người, chỉ tính dòng hợp lệ.
   - `overloaded_owners`: danh sách `{owner, total_hours}` có tổng giờ lớn hơn ngưỡng (bằng ngưỡng không phải quá tải). Rỗng nghĩa là không ai quá tải.
   - `excluded_rows`: danh sách `{line, task_id, reasons}` các dòng không được cộng vào tổng giờ.
5. Dùng quy tắc của script để giải thích, không tự tính lại:
   - `task_id`, `owner`, `hours` được bỏ khoảng trắng đầu/cuối; owner khác hoa/thường là hai người khác nhau.
   - Mỗi `task_id` chỉ giữ lần xuất hiện đầu tiên; các lần sau bị loại, kể cả khi lần đầu không hợp lệ.
   - Chỉ cộng dòng có đúng số trường, `task_id` và `owner` không rỗng, `hours` là số hữu hạn không âm (0 hợp lệ).
   - Mã lý do loại dòng: `wrong_field_count` (sai số trường), `missing_task_id` (thiếu task_id), `duplicate_id` (task_id trùng), `missing_owner` (thiếu owner), `invalid_hours` (hours không hợp lệ).
6. Đọc template `references/report-template.md` trong thư mục skill này, tức `skills/csv-quality/references/report-template.md`.
7. Điền đúng các mục của template. Mọi con số lấy từ JSON của script. Mỗi issue ghi line number (header là line 1), cột và mô tả. Ghi rõ tổng giờ chỉ tính trên các dòng hợp lệ và liệt kê từng dòng bị loại kèm tất cả lý do. Nếu danh sách issue/dòng bị loại quá dài, vẫn liệt kê đầy đủ từ JSON, không đọc lại CSV. Không sửa file CSV khi người dùng chỉ yêu cầu kiểm tra; có thể đề xuất cách sửa trong mục khuyến nghị.
8. Ghi file bằng `write_file` vào đường dẫn người dùng yêu cầu (ví dụ `output/workload.md`; nếu không nêu thì mặc định `output/csv-quality.md`).
9. Trả lời người dùng: đường dẫn file đã ghi (theo kết quả `write_file`) và tóm tắt 2–3 dòng (ngưỡng, ai quá tải, số dòng bị loại). Nếu ghi lỗi, báo lỗi.