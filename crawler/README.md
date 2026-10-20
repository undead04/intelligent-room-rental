# Module Thu Thập, Trích Xuất & Xử Lý Dữ Liệu Phòng Trọ (Data Crawler, LLM Extractor & ETL Pipeline)

> **Đề tài**: Xây dựng hệ thống hỗ trợ ra quyết định lựa chọn phòng trọ thông minh dựa trên Học máy (Machine Learning) và Mô hình ngôn ngữ lớn (LLM).  
> **Trường**: Đại học Công nghệ Thông tin - ĐHQG-HCM (UIT).

---

## 📌 1. Giới Thiệu Tổng Quan

Module này đảm nhiệm toàn bộ chu trình kỹ thuật dữ liệu (Data Engineering Pipeline) cho đồ án, bao gồm:
1. **Thu thập dữ liệu web đa nguồn** (Web Scraping) với cơ chế resume và early-stopping.
2. **Khu vực đệm dữ liệu thô hiệu năng cao** (SQLite Staging DB) với hỗ trợ kiểm tra trùng lặp $O(1)$ và xử lý lũy tiến (Incremental Processing).
3. **Trích xuất thuộc tính chuyên sâu bằng LLM** (Gemini 2.5 Flash / 2.0 Flash Lite) kết hợp **xác thực bằng chứng (Evidence Verification)** chống ảo giác.
4. **Chuẩn hóa, làm sạch & làm giàu ngữ cảnh (Text Cleaner & Context Enricher)**.
5. **Sinh vector ngữ nghĩa ngoại tuyến (Batch Offline Embedding)** với mô hình mã nguồn mở hàng đầu `intfloat/multilingual-e5-base` (768 chiều).
6. **Nạp đa đích (Multi-Destination Loader)**: Xuất báo cáo CSV, nạp backend JSON, lưu trữ Parquet cho Machine Learning, và nạp trực tiếp vào **PostgreSQL + pgvector**.

---

## 🏗️ 2. Kiến Trúc Pipeline 4 Tầng (4-Stage Architecture)

```mermaid
flowchart TD
    subgraph S1["Tầng 1: Data Crawling (Web Scraping)"]
        A1["NhaTot API (gateway.chotot.com)"] --> B1["Crawler Engine (crawler/spiders/)"]
        A2["PhongTro123 / Đa nguồn"] --> B1
        B1 -->|Lưu vết Checkpoint| C1["checkpoint.json"]
    end

    subgraph S2["Tầng 2: Staging Area (SQLite WAL Storage)"]
        B1 -->|Upsert thô O(1)| D1[("staging.db\n(raw_listings)")]
        D1 -->|Theo dõi trạng thái| E1["is_processed: 0/1"]
    end

    subgraph S3["Tầng 3: LLM Intelligence Extraction & Verification"]
        D1 -->|Đọc tin thô| F1["Dynamic Chunker\n(~2500 tokens/chunk)"]
        F1 --> G1["Gemini Round-Robin\n(Multi-API Keys Manager)"]
        G1 --> H1["Pydantic Extraction\n(Amenities, Safety, Rules, Numbers)"]
        H1 --> I1{"Evidence Verifier\n(So khớp nguyên văn text gốc)"}
        I1 -->|Hợp lệ| J1["Tính Concept Scores\n(amenity_score, safety_score)"]
        I1 -->|Bịa bằng chứng| K1["Hạ cờ về unknown"]
        K1 --> J1
        J1 --> L1["LLM Checkpoint JSON"]
    end

    subgraph S4["Tầng 4: ETL, Embedding & Multi-Destination Load"]
        D1 & L1 --> M1["Text Cleaner\n(Xóa SĐT, URL, Emoji, Spam CTAs)"]
        M1 --> N1["Context Enricher\n(Tích hợp Embedding Metadata: 5-Block Rich Text + 'passage: ')"]
        N1 --> O1["Listing Transformer\n(Chuẩn hóa schema, tích hợp ML Price Score)"]
        O1 --> P1["Listing Embedder\n(intfloat/multilingual-e5-base 768-dim)"]
        P1 --> Q1["DataLoader"]
        Q1 --> R1[("PostgreSQL + pgvector\n(Listing, Embedding, Location)")]
        Q1 --> R2["Parquet (Huấn luyện ML)"]
        Q1 --> R3["CSV / JSON (Báo cáo & Phân tích)"]
        Q1 -->|Cập nhật| D1
    end
```

---

## 📁 3. Cấu Trúc Thư Mục

```text
crawler/
├── config/
│   └── settings.py              # Cấu hình User-Agent, API parameters, timeouts
├── data/
│   ├── raw/
│   │   └── staging.db           # SQLite Staging DB duy nhất (chế độ WAL, index O(1))
│   └── processed/               # Nơi chứa các file xuất (CSV, JSON, Parquet)
├── etl/
│   ├── extract.py               # Trích xuất dữ liệu từ staging.db (hỗ trợ incremental)
│   ├── text_cleaner.py          # Chuẩn hóa Unicode NFC, lọc SĐT, URL, Emoji, rác CTA
│   ├── enricher.py              # Xây dựng 5 khối ngữ cảnh giàu thông tin cho Embedding
│   ├── transform.py             # Chuẩn hóa schema, xử lý số liệu, tính đơn giá, tích hợp LLM report
│   ├── embed.py                 # Batch offline embedder dùng intfloat/multilingual-e5-base
│   ├── load.py                  # Bộ nạp đa đích: PostgreSQL (pgvector), Parquet, CSV, JSON
│   ├── db_models.py             # Định nghĩa ORM SQLAlchemy & kết nối PostgreSQL (pgvector) độc lập
│   └── pipeline.py              # CLI điều phối toàn bộ chu trình ETL (Extract -> Load)
├── model/
│   ├── llm/
│   │   ├── checkpoint.py        # Quản lý checkpoint bóc tách LLM theo từng chunk
│   │   ├── chunker.py           # Phân chunk động dựa trên số token (tiktoken)
│   │   ├── client.py            # Gemini Round-Robin quản lý xoay vòng nhiều API keys
│   │   ├── processor.py         # Xử lý kết quả trả về từ Gemini và cập nhật state
│   │   ├── prompt.py            # System prompt tối ưu hóa trích xuất thuộc tính phòng
│   │   └── pipeline.py          # Runner bóc tách LLM độc lập
│   └── ml/                      # Module huấn luyện Machine Learning (định giá, ranking)
├── schema/
│   ├── enums.py                 # Danh mục chuẩn canonical (RoomType, AmenityCode, Amenities)
│   ├── enum.py                  # Shim tương thích ngược (re-export từ schema/enums.py)
│   └── listing.py               # Pydantic schemas (Signal, Amenities, Safety, ConceptScores)
├── spiders/
│   ├── base.py                  # Lớp Base Spider trừu tượng
│   ├── nhatot.py                # Crawler Chợ Tốt / Nhà Tốt API (resume, update, verify)
│   └── phongtro123.py           # Crawler PhongTro123
├── utils/
│   ├── count_token.py           # Đếm token đầu vào cho LLM
│   ├── http.py                  # Client HTTP với Retry & Exponential Backoff
│   └── parser.py                # Bóc tách và chuẩn hóa dữ liệu thô từ payload API
├── tests/                       # Unit tests cho schema, staging DB, pipeline chunking, transform
├── main.py                      # CLI điều khiển chính của Crawler
├── README.md                    # Tài liệu hướng dẫn chi tiết
└── requirements.txt             # Danh sách thư viện phụ thuộc
```

---

## ⚙️ 4. Cài Đặt Môi Trường

### 4.1. Yêu cầu hệ thống
- Python `>= 3.11`
- RAM tối thiểu 8GB (khuyến nghị 16GB nếu chạy embedding trên GPU hoặc CPU)
- Khuyến nghị GPU hỗ trợ CUDA (nếu sinh embedding ngoại tuyến tốc độ cao)

### 4.2. Cài đặt thư viện
```bash
pip install -r crawler/requirements.txt
```

### 4.3. Cấu hình biến môi trường
Tạo file `.env` tại thư mục gốc dự án hoặc trong thư mục `crawler/`:
```env
# API Keys Google Gemini (lấy từ Google AI Studio, tiền tố AIzaSy..., ngăn cách bằng dấu phẩy để chạy xoay vòng round-robin)
GEMINI_API_KEYS="AIzaSyA...,AIzaSyB...,AIzaSyC..."

# Kết nối cơ sở dữ liệu PostgreSQL (chứa extension pgvector)
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/smart_room_db"
```

> [!NOTE]
> - `GEMINI_API_KEYS`: Bắt buộc là API key hợp lệ lấy từ [Google AI Studio](https://aistudio.google.com/). Nếu chỉ có 1 key, bạn có thể gán `GEMINI_API_KEY="AIzaSy..."`.
> - Hệ thống có cơ chế Round-Robin tự động phát hiện chạm hạn ngạch (Rate Limit/429) để chuyển sang key tiếp theo.

---

## 🚀 5. Hướng Dẫn Sử Dụng Chi Tiết

Hệ thống hỗ trợ 2 cách vận hành: **Chạy trọn gói (End-to-End)** hoặc **Chạy tách biệt từng bước (Step-by-Step)**.

---

### 🌟 Lựa chọn 1: Chạy nhanh bằng Preset hoặc Menu tương tác (Khuyến nghị - Không cần nhớ cờ lệnh)

#### Cách 1.1: Bấm đúp chuột chạy Menu tương tác trên Windows
Chỉ cần bấm đúp chuột vào file [`run_crawler.bat`](run_crawler.bat) (hoặc gõ `.\run_crawler.bat` trong Terminal), hệ thống sẽ hiển thị Menu trực quan:
```text
================================================================
     HOMIGO - SMART HOUSING DECISION SUPPORT SYSTEM
            TRÌNH KHỞI CHẠY CRAWLER & ETL PIPELINE
================================================================

  [1] Cào cơ bản (5 trang TP.HCM -> Lưu Staging DB & Xuất CSV, Parquet)
  [2] Cào + Bóc tách tiện ích LLM Gemini (--llm)
  [3] Full Pipeline từ A-Z (Cào + LLM + Sinh Embedding E5 + Nạp DB) (--full)
  [4] Cào nhanh tin mới nhất (2 trang TP.HCM) (--quick)
  [5] Kiểm tra tin cũ còn hạn hay đã hết hạn (Verify 50 tin)
  [0] Thoát
```
👉 **Chỉ cần gõ `1`, `2`, `3` hoặc nhấn `Enter` là chạy ngay!**

#### Cách 1.2: Sử dụng các Preset ngắn gọn qua Terminal
Không cần phải nhớ cả dãy argument dài, bạn chỉ cần gõ:
```bash
# 1. Cào cơ bản (Mặc định: 5 trang TP.HCM, tự động lưu staging & xuất CSV, Parquet):
python crawler/main.py

# 2. Cào kèm bóc tách thuộc tính ngữ nghĩa qua LLM Gemini:
python crawler/main.py --llm

# 3. Trọn gói từ A-Z (Cào + LLM + ML Price Score + Embedding E5 + Nạp PostgreSQL & Parquet/CSV):
python crawler/main.py --full

# 4. Tùy chỉnh số trang hoặc khu vực:
python crawler/main.py --pages 10 --region hanoi
```

> **Bảng tham số tối giản `crawler/main.py`:**
> | Tham số | Ý nghĩa | Mặc định |
> |---|---|---|
> | `--full` | **Trọn gói A-Z**: Tự động bật **LLM Gemini** + **ML Price Score** + **Embedding E5** + **Nạp PostgreSQL** (`db`) & xuất CSV, Parquet | `False` |
> | `--llm` | **Bật LLM Gemini** bóc tách tiện ích, an ninh & kiểm định bằng chứng | `False` |
> | `--pages` | Số trang cần cào (mỗi trang ~50 tin) | `5` |
> | `--region` | Khu vực tỉnh/thành (`hcm`, `hanoi`, `danang`, `binhduong`...) | `hcm` |
> | `--mode` | Chế độ: `resume` (cào tiếp), `update` (tin mới), `verify` (kiểm tra tin cũ) | `resume` |
> | `--no-clean` | Tắt ETL (chỉ cào thô và lưu vào staging.db) | `False` |
> | `--limit` | Số lượng tin cũ kiểm tra khi chạy `--mode verify` | `50` |
> | `--source` | Nguồn dữ liệu (`nhatot`, `phongtro123`, `all`) | `nhatot` |

---

### 🧩 Lựa chọn 2: Chạy tách rời từng bước (Step-by-Step Modular)

Thích hợp khi muốn debug riêng lẻ từng module hoặc tiết kiệm token LLM:

#### 🔹 Bước 1: Thu thập dữ liệu thô (Data Crawling)
```bash
# Cào tin lưu vào crawler/data/raw/staging.db (tắt clean tự động để xử lý sau):
python crawler/main.py --source nhatot --mode resume --region hcm --pages 10 --no-clean

# Quét cập nhật tin mới hằng ngày (Update mode - tự dừng khi gặp tin cũ):
python crawler/main.py --source nhatot --mode update --region hcm --pages 5 --no-clean

# Kiểm tra tính khả dụng của tin cũ trong database (Verify mode):
python crawler/main.py --source nhatot --mode verify --limit 100
```

#### 🔹 Bước 2: Bóc tách thuộc tính ngữ nghĩa bằng LLM (LLM Extraction)
Sử dụng LLM (`gemini-2.5-flash` / `gemini-2.0-flash`) với Dynamic Token Chunking và Checkpoint chịu lỗi:
```bash
python -m crawler.model.llm.pipeline --max-tokens 2500 --rpm-delay 4.0
```
- **Dynamic Token Chunking**: Gom tự động các tin đăng thành từng chunk tối đa 2500 tokens để tối ưu chi phí và bám sát ngữ cảnh.
- **Round-Robin Multi-Key**: Xoay vòng các API key tự động khi chạm rate limit/quota.
- **Fault-Tolerant Checkpoint**: Lưu trạng thái vào `checkpoint_reports.json`. Nếu bị ngắt kết nối mạng hoặc tắt giữa chừng, lần chạy sau sẽ tự động bỏ qua các bài đã xong mà không tốn thêm token hay thời gian gọi lại.

#### 🔹 Bước 3: Chạy Pipeline ETL, Sinh Embedding & Nạp Dữ Liệu
Điều phối qua CLI `crawler/etl/pipeline.py`:
```bash
# Nạp đồng thời ra PostgreSQL, Parquet và CSV kèm sinh vector embedding:
python crawler/etl/pipeline.py --dest db parquet csv --embed

# Chế độ lũy tiến (Incremental): Chỉ xử lý các bài đăng MỚI chưa qua ETL:
python crawler/etl/pipeline.py --dest parquet csv --incremental

# Kèm trích xuất LLM và tích hợp checkpoint:
python crawler/etl/pipeline.py --dest db --embed --extract-llm --checkpoint crawler/data/processed/checkpoint_reports.json
```

> **Bảng tham số `crawler/etl/pipeline.py`:**
> | Tham số | Ý nghĩa | Mặc định |
> |---|---|---|
> | `--dest` | Danh sách đích nạp: `parquet`, `csv`, `json`, `db`, `postgres` | `parquet` |
> | `--embed` | Kích hoạt mô hình `intfloat/multilingual-e5-base` sinh vector 768 chiều | `False` |
> | `--extract-llm` | Tự động gọi LLM Gemini bóc tách ngữ nghĩa cho các bài thô | `False` |
> | `--incremental` | Chỉ xử lý các bài đăng chưa qua ETL (`is_processed == 0`) | `False` |
> | `--active-only` | Chỉ giữ các tin đang hoạt động (`is_active == True`) | `False` |
> | `--checkpoint` | Đường dẫn file JSON checkpoint chứa báo cáo trích xuất LLM | Tự động tìm |
> | `--eval-price` | Kích hoạt mô hình ML `PriceEvaluator` tự động tính điểm `price_score` | `False` |
> | `--output-parquet`| Tùy chỉnh đường dẫn file Parquet xuất ra | `crawler/data/processed/listings_clean.parquet` |
> | `--output-csv` | Tùy chỉnh đường dẫn file CSV xuất ra | `crawler/data/processed/listings_clean.csv` |
> | `--output-json` | Tùy chỉnh đường dẫn file JSON xuất ra | `crawler/data/processed/listings_clean.json` |

---

## 🧠 6. Mô Hình Embedding & Cơ Chế Biểu Diễn Ngữ Nghĩa

### 6.1. Mô hình được lựa chọn: `intfloat/multilingual-e5-base`
- **Kiến trúc**: Transformer-based encoder (12 layers, hidden size 768).
- **Kích thước vector**: **768 chiều** (tương thích chuẩn `vector(768)` trong PostgreSQL pgvector).
- **Lý do lựa chọn**:
  - Đứng top đầu bảng xếp hạng MTEB đa ngữ cho tác vụ Retrieval & Reranking.
  - Hiểu sâu sắc tiếng Việt thực tế (xử lý tốt từ ngữ viết tắt bất động sản như `p.trọ`, `kcc`, `ml`, `wc riêng`, `gác lửng`...).
  - Mã nguồn mở, chạy offline mượt mà trên CPU/GPU, không phụ thuộc API trả phí bên ngoài.

### 6.2. Quy tắc tiền tố E5 (Prefix Contract)
Mô hình E5 áp dụng kiến trúc bi-encoder bất đối xứng, bắt buộc sử dụng tiền tố chuẩn:
- **Khi lưu trữ dữ liệu phòng (Offline)**: Thêm tiền tố `passage: ` vào văn bản tài liệu.
- **Khi người dùng tìm kiếm (Online Query)**: Thêm tiền tố `query: ` vào câu truy vấn.

### 6.3. Cấu trúc văn bản làm giàu ngữ cảnh (5-Block Rich Text with Embedding Metadata)
Trước khi đưa vào mô hình embedding, dữ liệu được hàm `build_enriched_embedding_text` chuẩn hóa và đóng gói thành 5 khối ngữ cảnh. Đặc biệt, các **Embedding Metadata** (`landmarks_nearby`, `extra_amenities`, `rules_and_lifestyle`) được tự động khử trùng lặp bảo toàn thứ tự:
```text
passage: Vị trí: Đường Quang Trung, Phường 10, Quận Gò Vấp, Hồ Chí Minh (Gần: ĐH Văn Lang, Chợ Hạnh Thông Tây)
Loại phòng: Căn hộ chung cư | 2 phòng ngủ | 2 phòng tắm | Diện tích: 65.0m2 | Giá thuê: 8,500,000 VND/tháng
Tiện ích: máy lạnh, gác lửng, toilet riêng, kệ bếp, chỗ để xe, view Landmark 81
Quy định & Môi trường: giờ giấc tự do, không chung chủ, cho nuôi thú cưng
Mô tả chi tiết:
Căn hộ mới bàn giao sạch đẹp, giờ giấc tự do, có máy lạnh inverter tiết kiệm điện...
```

---

## 🛡️ 7. Cơ Chế Chống Ảo Giác & Đánh Giá Tiện Nghi (Concept Scores)

### 7.1. Evidence Verification (Kiểm Định Bằng Chứng)
Mỗi tín hiệu trích xuất bởi LLM (`Signal`) gồm 2 trường:
- `value`: `yes` | `no` | `unknown`
- `evidence`: Trích dẫn **nguyên văn** từ bài viết gốc.

Bộ xác thực `verify_evidence` so khớp trực tiếp đoạn `evidence` vào văn bản gốc:
$$\text{Nếu } \text{evidence} \notin \text{text\_gốc} \implies \text{hạ cờ } \text{value} = \text{"unknown"}$$
Cơ chế này loại bỏ hoàn toàn hiện tượng mô hình "suy đoán mò" hoặc bịa tiện ích không có thực.

### 7.2. Thang Điểm Tiện Nghi Tích Lũy (`amenity_overall_score`)
Để giải quyết bài toán **Score Flattening** (các phòng thiếu thông tin bị gán mặc định 0.4 điểm dẫn đến điểm số bị nén ở khoảng giữa), hệ thống sử dụng thang điểm tích lũy 100 điểm:

| Tiện ích | Trọng số điểm | Điều kiện ghi nhận |
|---|---|---|
| **WC riêng (khép kín)** | 20 điểm | Xác nhận `yes` |
| **Máy lạnh** | 20 điểm | Xác nhận `yes` |
| **Gác lửng** | 15 điểm | Xác nhận `yes` |
| **Bếp / Khu nấu ăn** | 15 điểm | Xác nhận `yes` |
| **Tủ lạnh** | 10 điểm | Xác nhận `yes` |
| **Máy giặt** | 10 điểm | Xác nhận `yes` |
| **Cửa sổ / Ban công** | 10 điểm | Xác nhận `yes` |
| **Nội thất cơ bản** | 5 điểm | Xác nhận `yes` |
| **Chỗ để xe** | 5 điểm | Xác nhận `yes` |
| **Thang máy** | 5 điểm | Xác nhận `yes` |

$$\text{amenity\_overall\_score} = \min\left(1.0, \frac{\sum \text{điểm đạt được}}{100}\right)$$

### 7.3. Thang Điểm An Ninh (`safety_score`)
Điểm an ninh tổng hợp được tính theo trọng số ưu tiên:
$$\text{safety\_score} = 0.30 \times S_{\text{camera}} + 0.30 \times S_{\text{bảo\_vệ}} + 0.25 \times S_{\text{khóa\_vân\_tay}} + 0.15 \times S_{\text{khu\_vực\_an\_ninh}}$$
Trong đó: $S_{\text{yes}} = 1.0$, $S_{\text{unknown}} = 0.0$, $S_{\text{no}} = 0.0$ (chỉ tính điểm cho các tiện ích/an ninh được xác nhận có bằng chứng `yes`, tránh làm phẳng điểm số Score Flattening).

### 7.4. Thang Điểm Thẩm Định Giá Thị Trường (`price_score` từ Machine Learning)
Thay vì sử dụng phép chia đơn giá thô ($price/m^2$) vốn không phản ánh đúng giá trị tiện nghi và vị trí vi mô, hệ thống tích hợp mô hình Machine Learning Conformal Prediction (`PriceEvaluator`):
1. **Dự đoán khoảng tin cậy giá thị trường**: $[price_{\text{low}}, price_{\text{high}}]$ và giá trị kỳ vọng $price_{\text{mid}}$.
2. **Tính độ lệch logarit (z-score)**:
   $$z = \frac{\ln(1 + \text{price}) - \text{center}}{\text{half}}$$
3. **Chuẩn hóa thang điểm `price_score` $\in [0.0, 1.0]$**:
   $$\text{price\_score} = \text{clip}\left(\frac{50.0 - 25.0 \times z}{100.0}, 0.0, 1.0\right)$$
   Kèm phân loại nhận định thị trường (`verdict`: *"Rất rẻ so với thị trường"*, *"Hợp lý"*, *"Đắt hơn thị trường"*...) phục vụ thuật toán Multi-Criteria Re-ranking.

---

## 🗄️ 8. Schema Cơ Sở Dữ Liệu PostgreSQL (pgvector)

Khi chạy `--dest db`, loader tự động nạp và liên kết các bảng:
- `cities`, `districts`, `wards`: Hệ thống địa danh phân cấp hành chính.
- `room_types`: Danh mục loại hình phòng (`ROOM`, `MINI_APARTMENT`, `HOUSE`, `STUDIO`...).
- `users`: Thông tin người đăng tin (chủ trọ/môi giới).
- `listings`: Thông tin cốt lõi bài đăng (giá, diện tích, tiền cọc, toạ độ, `price_score`, `concept_scores`, LLM extraction jsonb).
- `listing_embeddings`: Bảng chứa vector `vector(768)` liên kết `1-1` với `listings`, hỗ trợ lập chỉ mục **HNSW** (`vector_cosine_ops`) để tìm kiếm ngữ nghĩa theo Cosine Similarity dưới 10ms.

---

## 🧪 9. Kiểm Thử (Unit Tests)

Thư mục `crawler/tests/` cung cấp bộ kiểm thử toàn diện:
```bash
# Chạy toàn bộ test của module crawler
pytest crawler/tests -v
```

Danh sách các test case chính:
- `test_listing_schema.py`: Kiểm tra Pydantic validation, evidence verification và thang điểm concept scores.
- `test_staging_db.py`: Kiểm tra tính toàn vẹn SQLite WAL, khử trùng lặp và chuyển đổi trạng thái `is_processed`.
- `test_transform.py`: Kiểm tra làm sạch văn bản, chuyển đổi kiểu dữ liệu, khử trùng lặp, tích hợp embedding metadata và ML price score.
- `test_run_pipeline_chunking.py`: Kiểm tra bộ bóc tách token chunking và cơ chế checkpoint phục hồi.

---

## 🎓 10. Đóng Góp Kỹ Thuật Cho Báo Cáo Khóa Luận

1. **Kiến trúc Staging 2 tầng tách biệt**: Tách bạch hoàn toàn giữa tốc độ cào thô (I/O bounded) và tốc độ xử lý LLM/Embedding (Compute bounded).
2. **Kỹ thuật Dynamic Token Chunking**: Đóng gói danh sách phòng trọ vừa khít ngưỡng token cho phép xử lý lô lớn qua LLM mà không vượt quota.
3. **Evidence-based Factuality Verification**: Kỹ thuật xác thực nguồn gốc giúp đưa tỷ lệ ảo giác của LLM về $0\%$ đối với các tiện ích cốt lõi.
4. **Giải pháp Score Flattening Mitigation**: Đổi mới công thức tính điểm tích lũy giúp phân hóa độ hấp dẫn của phòng trọ rõ nét, phục vụ hiệu quả cho mô hình Machine Learning Ranking.
5. **Mô hình Thẩm Định Giá Conformal ML (`price_score`)**: Thay thế tư duy tính đơn giá thô bằng mô hình dự đoán khoảng tin cậy giá thị trường, nâng cấp hệ thống thành nền tảng hỗ trợ ra quyết định thông minh.

