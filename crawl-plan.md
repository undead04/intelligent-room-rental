# Kế hoạch triển khai: Thu thập dữ liệu (Web Crawling) — Hệ thống hỗ trợ ra quyết định lựa chọn phòng trọ

> Dùng file này làm ngữ cảnh/spec cho AI coding agent (Antigravity) triển khai module crawl dữ liệu.
> Đề tài: Xây dựng hệ thống hỗ trợ ra quyết định lựa chọn phòng trọ thông minh dựa trên học máy và LLM.

## 1. Mục tiêu

Thu thập, chuẩn hóa và lưu trữ dữ liệu tin đăng phòng trọ (vị trí, giá, diện tích, tiện ích, hình ảnh...) từ nhiều nguồn để phục vụ:
- Huấn luyện mô hình dự đoán giá thuê (Random Forest, XGBoost)
- Tính MatchScore xếp hạng phòng
- Xây dựng embedding cho tìm kiếm ngữ nghĩa (RAG + Sentence-BERT + FAISS/pgvector)

## 2. Phạm vi nguồn dữ liệu

| Nguồn | Vai trò | Ghi chú kỹ thuật |
|---|---|---|
| **Chợ Tốt (chotot.com / nhatot.com)** | **Chính** | Có **public API trả JSON sạch**, không cần render JS, không bị Cloudflare/anti-bot chặn như các site khác → nhanh, ổn định, dễ resume. Đây là lý do chọn làm nguồn chính. |
| Phongtro123.com | Phụ (tùy chọn) | Dùng làm tập đối chiếu/validate giá thị trường nếu còn thời gian (crawl HTML tĩnh với `requests` + `BeautifulSoup`) |
| Batdongsan.com.vn | Không ưu tiên | Chặn bot bằng Cloudflare, chi phí crawl cao, không cần thiết khi đã có Chợ Tốt |
| Group Facebook/Zalo | Bỏ qua | Chống bot mạnh, yêu cầu đăng nhập, dữ liệu phi cấu trúc |

### Ghi chú kỹ thuật về API Chợ Tốt

- Chợ Tốt expose API JSON công khai cho trang tìm kiếm (bắt được qua tab **Network → Fetch/XHR** khi search "phòng trọ" trên chotot.com/nhatot.com), không cần đăng nhập, không cần browser headless.
- Có tham số **mã vùng** (`region_v2`, ví dụ `13000` = TP. Hồ Chí Minh) và **mã danh mục** (`cg`, ví dụ `1000` = bất động sản) — cần lọc thêm để chỉ lấy danh mục con "phòng trọ" trong nhóm cho thuê (không lấy nhầm bán nhà/đất).
- API thường giới hạn **~20 tin/trang** → cần phân trang qua `offset`/`limit` hoặc tham số tương đương.
- **Bắt buộc tự xác minh lại endpoint + params hiện tại qua DevTools trước khi code**, vì cấu trúc API có thể thay đổi theo thời gian và không có tài liệu chính thức công khai.
- Vẫn cần rate-limit hợp lý dù API "dễ tính" hơn — tránh gửi request dồn dập gây nghi ngờ bị lạm dụng.

## 3. Việc cần khảo sát trước khi code

- [ ] Mở DevTools → tab Network (filter Fetch/XHR) trên chotot.com/nhatot.com khi search "phòng trọ", bắt đúng endpoint API, method, headers cần thiết, params (`region_v2`, `cg`, phân trang...)
- [ ] Gọi thử endpoint đó bằng `requests`/Postman ngoài browser để xác nhận không cần cookie/token đặc biệt
- [ ] Ghi lại đầy đủ field trả về trong JSON response của trang danh sách và trang chi tiết, map sang schema ở mục 4
- [ ] Kiểm tra `robots.txt` của chotot.com để chắc chắn endpoint API không nằm trong phần bị cấm crawl
- [ ] (Nếu làm thêm Phongtro123) Test crawl 1 tin mẫu, xác định `requests`+`BeautifulSoup` có đủ hay cần `Playwright`

## 4. Schema dữ liệu thô (raw listing)

```json
{
  "listing_id": "string (unique, theo source + id gốc)",
  "source": "phongtro123 | nhatot | batdongsan",
  "url": "string",
  "title": "string",
  "price_vnd": "number (đã chuẩn hóa về VNĐ/tháng)",
  "area_m2": "number",
  "address_raw": "string",
  "ward": "string | null",
  "district": "string | null",
  "city": "string",
  "lat": "number | null",
  "lng": "number | null",
  "room_type": "string (phòng trọ | nhà nguyên căn | chung cư mini | ...)",
  "amenities": ["gác lửng", "máy lạnh", "chỗ để xe", "..."],
  "images": ["url1", "url2"],
  "posted_date": "ISO date | null",
  "description": "string",
  "crawled_at": "ISO datetime"
}
```

**Lưu ý riêng tư/pháp lý:** không lưu số điện thoại/thông tin định danh cá nhân của người đăng trong dataset dùng để công bố/báo cáo.

## 5. Kiến trúc crawl (2 tầng, ưu tiên gọi API Chợ Tốt trực tiếp)

1. **Tầng danh sách (listing fetcher)**
   - Gọi API tìm kiếm của Chợ Tốt theo `region_v2` (khu vực TP.HCM và lân cận) + `cg` (danh mục phòng trọ/cho thuê)
   - Duyệt qua các trang bằng `offset`/`limit` cho đến khi hết kết quả hoặc đạt số lượng mục tiêu
   - Thu thập `listing_id` (+ `list_id` nếu API trả riêng) → ghi vào `data/raw/listing_ids.csv`
   - Hỗ trợ resume: bỏ qua ID đã có trong file

2. **Tầng chi tiết (detail fetcher)**
   - Nếu API danh sách đã trả đủ field cần thiết (giá, diện tích, địa chỉ, tiện ích...) → **không cần gọi thêm API chi tiết**, tiết kiệm request
   - Nếu thiếu field (vd: mô tả đầy đủ, ảnh chất lượng cao) → gọi thêm API/endpoint chi tiết theo từng `listing_id`
   - Lưu raw JSON vào `data/raw/listings/chotot_{listing_id}.json`
   - Đánh dấu ID đã xử lý để có thể resume khi bị gián đoạn

## 6. Công nghệ đề xuất

- Ngôn ngữ: Python 3.11+
- **Gọi API Chợ Tốt**: `requests` (hoặc `httpx`) — không cần trình duyệt/headless vì API trả JSON trực tiếp
- Crawl tĩnh (chỉ khi làm thêm Phongtro123): `requests` + `BeautifulSoup4`
- Crawl động (dự phòng, hiếm khi cần với Chợ Tốt): `Playwright`
- Quản lý pipeline (tùy chọn nếu volume lớn): `Scrapy` hoặc script tuần tự đơn giản (với API JSON thường không cần Scrapy)
- Lưu trữ trung gian: JSON/CSV theo từng file, KHÔNG ghi thẳng vào PostgreSQL lúc crawl
- ETL nạp DB: script Python riêng, chạy sau khi crawl xong và đã làm sạch dữ liệu

## 7. Cơ chế chống bị chặn

- `time.sleep(random.uniform(2, 5))` giữa các request
- Rotate User-Agent theo danh sách cấu hình sẵn
- Giới hạn concurrency (ví dụ tối đa 3-5 request đồng thời)
- Retry có backoff khi gặp lỗi mạng; log riêng các mã lỗi 403/429 để phát hiện bị chặn sớm
- Timeout hợp lý cho mỗi request (ví dụ 15s)

## 8. Làm sạch & chuẩn hóa dữ liệu (sau khi crawl xong)

- [ ] Chuẩn hóa đơn vị giá về VNĐ/tháng (loại "triệu", "tr", "đ", dấu phẩy/chấm)
- [ ] Chuẩn hóa diện tích về m²
- [ ] Tách địa chỉ → phường/quận/thành phố (phục vụ tính LocationFit)
- [ ] Chuẩn hóa danh sách tiện ích (map các từ đồng nghĩa: "gác lửng" = "gác xép"...)
- [ ] Khử trùng lặp (theo địa chỉ + giá + diện tích gần giống nhau, hoặc theo URL/ID gốc nếu trùng nguồn)
- [ ] Xử lý missing values (tiện ích không rõ, ảnh lỗi link, tọa độ null)
- [ ] Gắn nhãn `source` để phục vụ so sánh/đối chiếu sau này

## 9. Output mong đợi của giai đoạn crawl

- `data/raw/urls_queue.csv` — danh sách URL đã thu thập
- `data/raw/listings/*.json` — dữ liệu thô từng tin đăng
- `data/processed/listings_clean.csv` (hoặc `.parquet`) — dữ liệu đã làm sạch, sẵn sàng nạp PostgreSQL
- Script ETL nạp vào bảng `listings`, `amenities` theo ERD của hệ thống
- Báo cáo thống kê mô tả (EDA) ngắn: số lượng tin theo nguồn/khu vực, phân bố giá, tỉ lệ thiếu dữ liệu

## 10. Cấu trúc thư mục đề xuất

```
crawler/
├── config/
│   └── settings.py          # user-agent list, delay, target sources
├── spiders/
│   ├── phongtro123.py
│   ├── nhatot.py
│   └── batdongsan.py
├── data/
│   ├── raw/
│   │   ├── urls_queue.csv
│   │   └── listings/
│   └── processed/
│       └── listings_clean.csv
├── etl/
│   ├── clean.py              # làm sạch & chuẩn hóa
│   └── load_to_postgres.py   # nạp vào DB
├── utils/
│   ├── http.py                # session, retry, headers rotation
│   └── parser.py              # helper parse giá/diện tích/địa chỉ
└── requirements.txt
```

## 11. Timeline (Tháng 1, khớp đề cương)

| Tuần | Công việc |
|---|---|
| 1 | Khảo sát cấu trúc web, viết crawler thử nghiệm 1 nguồn, test 50-100 tin |
| 2 | Hoàn thiện crawler cho 2 nguồn chính, chạy full crawl, mục tiêu 2.000–5.000 tin |
| 3 | Làm sạch, chuẩn hóa, khử trùng lặp, nạp PostgreSQL |
| 4 | EDA dữ liệu, kiểm tra phân bố giá/khu vực, chuẩn bị cho huấn luyện mô hình |

## 12. Ràng buộc / lưu ý cho agent khi code

- Tuân thủ `robots.txt` của từng site, không crawl phần bị cấm
- Giới hạn tốc độ crawl để không gây tải cho server nguồn
- Không thu thập/lưu trữ thông tin định danh cá nhân (SĐT, tên chủ trọ) trong dataset công bố
- Code cần có khả năng resume khi bị gián đoạn (không crawl lại từ đầu)
- Log đầy đủ lỗi/URL thất bại để review thủ công sau
