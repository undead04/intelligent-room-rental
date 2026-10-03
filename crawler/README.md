# Hệ thống hỗ trợ ra quyết định lựa chọn phòng trọ thông minh

> **Đề tài**: Xây dựng hệ thống hỗ trợ ra quyết định lựa chọn phòng trọ thông minh dựa trên Học máy (Machine Learning) và Mô hình ngôn ngữ lớn (LLM).

## 📌 Module Thu Thập Dữ Liệu (Web Crawler)

Module thực hiện thu thập, chuẩn hóa và lưu trữ dữ liệu tin đăng phòng trọ từ nguồn **Chợ Tốt (NhaTot)** thông qua API công khai (`gateway.chotot.com`).

### 🌟 Tính năng nổi bật
- **Thu thập trực tiếp qua API JSON**: Không cần trình duyệt headless (Playwright/Selenium), tối ưu tốc độ và độ ổn định.
- **Thu thập 1 tầng (Single-tier Crawling)**: API danh sách chứa đầy đủ các trường thông tin (giá, diện tích, tọa độ lat/lng, thông tin người đăng, bài viết chi tiết).
- **Cơ chế Checkpoint tự động**: Lưu mốc cào dữ liệu (`checkpoint.json`), cho phép dừng/chạy lại không mất tiến độ.
- **Hỗ trợ 2 chế độ chạy thông qua CLI**:
  - `resume`: Cào nối tiếp dữ liệu lịch sử từ mốc checkpoint.
  - `update`: Quét tin mới từ Trang 1, tự động dừng sớm (Early Stopping) khi phát hiện trang toàn tin cũ.
- **Trích xuất dữ liệu đa mục đích**: Thu thập các trường riêng biệt phục vụ cả Machine Learning Training và hiển thị giao diện Website (UI).

---

## 📁 Cấu trúc thư mục Module Crawler

```text
crawler/
├── config/
│   └── settings.py          # Cấu hình User-Agent, API parameters, timeouts
├── utils/
│   ├── http.py              # Xử lý HTTP request với Retry/Backoff
│   └── parser.py            # Bóc tách và chuẩn hóa dữ liệu từ Chợ Tốt API
├── spiders/
│   └── nhatot.py            # Script cào dữ liệu chính (hỗ trợ CLI parameters)
├── etl/
│   └── clean.py             # Làm sạch, khử trùng lặp và tổng hợp thành CSV
├── data/
│   ├── raw/                 # Dữ liệu JSON thô & file checkpoint
│   │   └── listings/
│   └── processed/           # Dữ liệu sạch dạng CSV/Parquet sẵn sàng nạp DB
└── requirements.txt         # Các thư viện phụ thuộc (requests, pandas)
```

---

## 🚀 Hướng dẫn cài đặt và sử dụng

### 1. Cài đặt môi trường
Yêu cầu Python 3.11+.

```bash
pip install -r crawler/requirements.txt
```

### 2. Chạy Crawler

#### 🔹 Chế độ 1: Cào dữ liệu lịch sử (Resume mode)
Sử dụng khi cào số lượng lớn. Nếu bị gián đoạn (mất mạng, ngắt Ctrl+C), chạy lại lệnh này sẽ tiếp tục cào từ mốc cũ.

```bash
# Cào tiếp từ checkpoint, quét thêm 50 trang
python crawler/spiders/nhatot.py --mode resume --pages 50
```

#### 🔹 Chế độ 2: Cập nhật tin mới hằng ngày (Update mode)
Dùng cho lệnh chạy tự động (Cronjob/Task Scheduler). Quét từ Trang 1 và tự động dừng khi gặp tin cũ.

```bash
# Quét tin mới nhất, tối đa 10 trang
python crawler/spiders/nhatot.py --mode update --pages 10
```

### 3. Tổng hợp & Làm sạch dữ liệu (ETL)
Sau khi cào xong, chạy script để gom các file JSON thô thành file `listings_clean.csv`:

```bash
python crawler/etl/clean.py
```

File CSV kết quả sẽ nằm tại `crawler/data/processed/listings_clean.csv`.

---

## 📊 Schema Dữ Liệu Đã Thu Thập

| Trường Dữ Liệu | Kiểu Dữ Liệu | Mục Đích | Mdescription / Mô tả |
|---|---|---|---|
| `listing_id` | String | Định danh | ID duy nhất (ví dụ: `nhatot_134814511`) |
| `title` | String | UI | Tiêu đề tin đăng |
| `price_string` | String | UI | Chuỗi giá hiển thị (ví dụ: `3,5 triệu/tháng`) |
| `price_vnd` | Number | ML Train | Giá thuê chuẩn hóa theo VNĐ/tháng |
| `area_m2` | Number | ML Train | Diện tích (m²) |
| `price_million_per_m2` | Number | ML Train | Đơn giá triệu VNĐ/m² |
| `deposit` | Number | ML Train | Tiền cọc (VNĐ) |
| `poster_name` | String | UI | Tên người đăng |
| `poster_avatar` | String | UI | URL ảnh đại diện người đăng |
| `poster_live_ads` | Number | UI/Trust | Số bài đang đăng của người dùng |
| `is_company_ad` | Boolean | ML/UI | Phân biệt môi giới/công ty hay cá nhân |
| `address_raw` | String | UI | Địa chỉ thô đầy đủ |
| `lat` / `lng` | Number | ML/Map | Tọa độ địa lý |
| `description` | String | LLM/RAG | Nội dung mô tả chi tiết bài đăng |

