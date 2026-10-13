---
name: search-room
description: Tìm và so sánh phòng trọ, căn hộ, nhà thuê theo nhu cầu (vị trí, ngân sách, diện tích, tiện nghi), rồi viết báo cáo 5 phòng kèm lý do chọn top 1. Dùng skill này mỗi khi người dùng nhắn tìm phòng, tìm trọ, thuê nhà, thuê căn hộ, tìm chỗ ở gần trường/công ty/một đường hay quận/phường nào đó, hoặc hỏi "có phòng nào khoảng X triệu ở Y không", kể cả khi họ không nói rõ "tìm phòng".
---

# Search Room

Skill này gọi một backend riêng (vector search + geocode + danh mục quận/phường) để tìm phòng thật. Kết quả chỉ đáng tin khi request khớp đúng schema của backend, nên bước đầu tiên luôn là đọc tài liệu API.

**Quy ước đường dẫn:** mọi đường dẫn tính từ thư mục gốc dự án, skill nằm ở `skills/search-room/`. Luôn chạy script bằng đường dẫn đầy đủ `python skills/search-room/scripts/<tên>.py`, không `cd`.

Base URL mặc định: `http://localhost:8000/api/v1` (đổi bằng biến môi trường `SEARCH_ROOM_API_BASE`). Script chỉ dùng thư viện chuẩn Python.

## Bước 0: Đọc tài liệu API (làm trước mọi việc khác)

Gọi tool `view` với path `skills/search-room/references/api.md` ngay khi skill được kích hoạt, trước cả khi phân tích nhu cầu hay chạy bất kỳ script nào, kể cả `--dry-run`.

Lý do: file này là nguồn duy nhất cho tên field, field bắt buộc, giá trị hợp lệ và cách dùng `--extra-json` / `--body-file`. Các ví dụ lệnh bên dưới chỉ minh họa luồng làm việc, schema thật có thể khác. Đoán schema thường dẫn đến lỗi 422 hoặc kết quả sai mà không báo lỗi.

Đầu file có một **mã xác nhận** (dòng `ACK-CODE: ...`). Mọi script đều yêu cầu `--ack <mã>` và sẽ từ chối chạy nếu thiếu hoặc sai. Mã này chỉ lấy được bằng cách đọc file.

Đọc xong, viết 2-3 dòng tóm tắt cho chính mình: field bắt buộc của `vector_search`, và các giá trị hợp lệ quan trọng (loại phòng, đơn vị giá, bán kính). Dùng tóm tắt này khi dựng lệnh ở các bước sau.

## Bước 1: Bóc tách nhu cầu

Ghi lại những gì người dùng đã nói, không hỏi lại:
- **Vị trí**: địa điểm cố định (trường, công ty, đường) hoặc quận/phường
- **Ngân sách**: đổi ra VNĐ/tháng ("3tr" = 3000000)
- **Diện tích, loại phòng**
- **Nhu cầu mềm**: gác lửng, nuôi thú cưng, yên tĩnh, an ninh, giờ giấc tự do...

Phân loại để dùng ở Bước 3: nhu cầu mềm đi vào `--query` của vector search (vì đó là ngữ nghĩa, không lọc cứng được). Giá, diện tích, loại phòng đi vào bộ lọc cứng theo đúng tên field trong `api.md`.

## Bước 2: Xác định vị trí

**Nhánh A: có địa điểm cố định → geocode**

```bash
python skills/search-room/scripts/geocode.py --ack <mã> --q "Trường ĐH Công nghệ Thông tin" --hint "Hồ Chí Minh"
```

Kiểm tra `formatted_address` có đúng nơi người dùng muốn không, rồi lấy `lat`, `lon`. Nếu 404, thử viết đầy đủ hơn hoặc hỏi lại người dùng.

**Nhánh B: chỉ có quận/phường → tra ward id**

```bash
python skills/search-room/scripts/cities.py --ack <mã> --name "Hồ Chí Minh"
python skills/search-room/scripts/districts.py --ack <mã> --name "Thủ Đức" --city-id 1
python skills/search-room/scripts/wards.py --ack <mã> --name "Linh Xuân" --district-id 12
```

Script không phân biệt dấu. Lấy `id` phường khớp. Nếu người dùng chỉ nêu quận, lấy toàn bộ phường của quận và truyền nhiều `--ward-id`. Nếu còn nhập nhằng, hỏi lại.

**Nhánh C: không có thông tin vị trí** → hỏi đúng một câu: muốn ở khu vực nào hoặc gần đâu. Không đoán, vì vị trí sai làm cả báo cáo vô nghĩa.

## Bước 3: Vector search

```bash
python skills/search-room/scripts/vector_search.py --ack <mã> \
  --query "phòng trọ có gác lửng, yên tĩnh, cho nuôi mèo" \
  --lat 10.8690 --lng  106.8034 \
  --max-price 3000000 --limit 5
```

Với nhánh B dùng `--ward-id 27 --ward-id 28` thay cho `--lat/--lng`. Tên tham số trên là ví dụ, đối chiếu với tóm tắt từ `api.md` ở Bước 0.

- **Query**: viết nhu cầu mềm như một câu văn tự nhiên, bỏ địa điểm và giá (đã có bộ lọc riêng).
- **`--dry-run`**: xem request trước khi gửi, nên dùng lần đầu mỗi phiên.
- **Ít hơn 5 phòng**: báo đúng số có, không bịa thêm.
- **0 phòng**: nới ngân sách khoảng 20% hoặc tăng bán kính, đúng một lần, và nói rõ đã nới gì.
- **`ok: false`**: đọc `error`. Lỗi 422 thường do sai tên field, mở lại `api.md` và sửa. Backend không chạy thì báo người dùng, tuyệt đối không tự chế dữ liệu.

## Bước 4: Viết báo cáo

Đọc `skills/search-room/references/report-template.md` rồi viết theo đúng cấu trúc:

1. Tóm tắt nhu cầu và vị trí (kèm giả định nếu có)
2. Bảng 5 phòng tốt nhất, theo thứ tự kết quả
3. Vì sao top 1 được chọn: đối chiếu từng tiêu chí với dữ liệu thật, so với top 2, và nêu rõ điểm yếu
4. Gợi ý bước tiếp theo
5. Dùng tool write lưu báo cáo thành `output/search-room-report.md`

Chỉ dùng dữ liệu từ API. Field thiếu thì ghi "chưa có thông tin", không suy đoán, vì người dùng sẽ dựa vào báo cáo để đi xem phòng thật.