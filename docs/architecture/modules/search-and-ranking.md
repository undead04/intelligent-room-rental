# 🔍 Tìm Kiếm & Tái Xếp Hạng Đa Tiêu Chí (Search & Ranking Module)

Tài liệu này đặc tả chi tiết kiến trúc của phân hệ **Hybrid Search & MCDM Reranker** (`backend/app/repositories/` & `backend/app/services/`).

---

## 1. Cơ Chế Tìm Kiếm Lai (Hybrid Search: Dense + Sparse FTS Không Dấu + RRF Multi-Source)

Hệ thống kết hợp 2 nhánh tìm kiếm với tỉ trọng **70% Dense / 30% Sparse** ($\alpha = 0.7$) qua **Reciprocal Rank Fusion (`RRF`, `k = 60`)** và hợp nhất đa nguồn trước khi đưa vào MCDM Reranker:

$$\text{RRF Score} = \frac{\alpha}{60 + \text{rank}_{\text{dense}}} + \frac{1 - \alpha}{60 + \text{rank}_{\text{sparse}}}$$
$$\text{Hybrid Similarity (Semantic Fit)} = \alpha \times \text{Dense Sim} + (1 - \alpha) \times \text{Sparse Norm}$$

```mermaid
flowchart TD
    Query["Câu truy vấn người dùng<br/>'phong tro co may giat gan DHQG'"] --> Dense["Dense Branch (pgvector)<br/>Cosine trên E5 vector 768d (alpha = 0.7)"]
    Query --> Sparse["Sparse Branch (PostgreSQL FTS)<br/>ts_rank_cd + public.f_unaccent + GIN idx_listings_fts_unaccent (0.3)"]
    
    Dense --> RRF["RRF Fusion (k=60, 60% slot budget)"]
    Sparse --> RRF
    GeoPrice["Nhánh phụ Vị trí gần (20%) & Giá hời price_score (20%)"] --> Pool["Multi-source Candidate Pool (limit >= 250)"]
    RRF --> Pool
    Pool --> Rerank["MCDM Multi-Criteria Reranker"]
```

* **Dense Branch:** Đo lường Cosine Distance trên bảng `listing_embeddings` (`pgvector` HNSW index `idx_listing_embeddings_vector_hnsw`).
* **Sparse Branch (hỗ trợ tiếng Việt không dấu):** Đánh giá `ts_rank_cd` trên `to_tsvector('simple', public.f_unaccent(title || ' ' || address_raw || ' ' || description))` kết hợp GIN index `idx_listings_fts_unaccent` (Migration `002_add_unaccent_fts.sql`) và `OR-tsquery` không dấu.
* **Multi-source Candidate Pool (`candidate_limit >= 250`):** `ListingService.vector_search` lấy pool rộng (`max(limit * 20, 250)`) với slot dự phòng riêng cho Top RRF (60%), Top khoảng cách gần nhất (20% khi có tọa độ) và Top `price_score` (phần còn lại), tránh tình trạng phòng gần/giá hời bị cắt mất trước khi vào MCDM Reranker.

---

## 2. Cơ Chế Lọc Không Gian & Ràng Buộc Cứng (Spatial & Hard Filtering)

- **Spatial Pre-filter & Exact Haversine Filter (Lọc không gian 2 lớp):**
  1. *Lớp 1 (Bounding Box SQL Pre-filter):* Khung giới hạn toạ độ hộp chữ nhật (`lat BETWEEN lat_min AND lat_max`, `lng BETWEEN lng_min AND lng_max`) tại CSDL để loại bỏ nhanh các tin đăng ngoài vùng và tận dụng index B-tree.
  2. *Lớp 2 (Exact Haversine Great-Circle Filter):* Tính khoảng cách đường cong mặt cầu chính xác theo toạ độ địa lý (`haversine_km(lat, lng) <= max_distance_km`), loại bỏ triệt để các tin nằm ở 4 góc chéo của Bounding Box.
- **Lọc Tập Đa Loại Phòng (`room_type` / `allowed_room_types`):** Hỗ trợ tìm kiếm đồng thời nhiều loại hình phòng qua điều kiện SQL `Listing.room_type_id.in_(type_ids)` linh hoạt.
- **Ánh Xạ Ngữ Nghĩa Cho Tiện Ích Tổng Hợp:**
  - `safe_area`: Ánh xạ từ tổ hợp an ninh (`camera`, `guard`, `fingerprint_lock`) và khu dân trí cao.
  - `furniture`: Thỏa mãn khi có các tiện nghi thiết yếu (`bed`, `wardrobe`, `air_conditioner`).

---

## 3. Bộ Tái Xếp Hạng Đa Tiêu Chí (MCDM Reranker 5 Tiêu Chí)

Sắp xếp lại tập ứng viên ban đầu theo 5 trụ cột:

| Tiêu Chí | Trọng Số Cơ Sở Mặc Định | Cách Thức Đánh Giá |
| :--- | :--- | :--- |
| **Location Fit** | `0.25` | Khoảng cách đường chim bay (Haversine formula). Áp dụng suy giảm phi tuyến ($ratio^{1.5}$) trong khoảng `near_km = 0.8` đến `far_km = max_distance_km`. |
| **Price Fit** | `0.25` | Đánh giá mức độ hợp lý thị trường qua ML `price_score` kết hợp độ rẻ tiền danh nghĩa (`savings_ratio`). Mặc định ưu tiên giá trị hời theo thị trường (`80%` `ml_score` + `20%` `savings_ratio`); chỉ đẩy lên `85%` rẻ danh nghĩa khi bật tường minh `prefer_cheapest=True` (`multipliers['price'] > 1.0`). |
| **Safety Fit** | `0.20` | Điểm an ninh tổng hợp (`safety_score`) dựa trên camera, bảo vệ, khóa vân tay, an toàn PCCC. |
| **Amenity Fit** | `0.20` | Chấm độ khớp tiện ích mềm (`preferred_amenities`) 70% + điểm tổng thể (`amenity_overall`) 30%. Khi nói chung chung (không có tiện ích mềm), vẫn bật nền nhẹ (`0.10` ở Backend / `BASELINE_AMENITY_SCALE = 0.5` trên nền `0.20` ở Agent) theo `amenity_overall` (tin thiếu dữ liệu luôn nhận `0.0` trong `rerank()`). |
| **Semantic Fit** | `0.10` | Điểm tương đồng ngữ nghĩa từ Hybrid Search (`similarity_score`). |

### Cơ Chế Trọng Số Động (Dynamic Weights & L1 Normalization):
- **Đồng bộ Trọng Số Cơ Sở:** Cả `backend` (`reranker.DEFAULT_WEIGHTS`) và `ai-agent` (`intent_weights.DEFAULT_BASE_WEIGHTS`) dùng chung bộ cơ sở `location=0.25, price=0.25, safety=0.20, amenity=0.20, semantic=0.10`.
- **Luôn kích hoạt:** `price`, `safety`, `semantic`, và `amenity` (`amenity` dùng mức nền nhẹ theo `amenity_overall` khi người dùng nói chung chung hoặc chỉ có tiện ích bắt buộc; nâng lên mức đầy đủ khi có `preferred_amenities`, `include_amenity_overall=True`, hoặc nhấn mạnh tiện nghi `multipliers['amenity'] > 1.0`). Caller truyền vector `weights` tùy chỉnh vẫn được `_dynamic_weights` tôn trọng mà không làm kích hoạt nhầm điểm mặc định cho tin thiếu dữ liệu tiện nghi.
- **Kích hoạt có điều kiện:** `location` (chỉ bật khi có tọa độ điểm mốc).
- **Chuẩn hoá L1:** Tổng trọng số các tiêu chí đang bật luôn được chuẩn hóa để $\sum w_i = 1.0$. Không dùng trọng số `price` sau chuẩn hóa L1 để suy diễn `prefer_cheapest`.

---

## 4. Dịch Vụ Định Vị Tọa Độ Backend (`GET /api/v1/geocode/`)

Phân hệ Geocoding (`backend/app/services/geocoder.py`, `schemas/geocode.py`, `controllers/geocoding_controller.py`) phân giải tên địa điểm đầu vào kèm `hint` khu vực thành tọa độ chính xác hoặc danh sách ứng viên đa nghĩa:

- **Region Bounding-Box Guard (`REGION_BBOXES`):** Khai báo khung tọa độ cho 6 vùng hỗ trợ (`TP.HCM`, `Hà Nội`, `Đà Nẵng`, `Bình Dương`, `Đồng Nai`, `Cần Thơ`, giữ vùng giao thoa quanh Làng ĐH Thủ Đức – Dĩ An). Khi `hint` xác định được vùng, mọi ứng viên nằm ngoài vùng bị loại bỏ thay vì trả nhầm tỉnh khác.
- **Top-5, TrackAsia & Gom Cụm Đa Cơ Sở (`AMBIGUOUS_CLUSTER_KM = 0.5`, `BROAD_AREA_CLUSTER_KM = 3.5`):** Khi có `TRACKASIA_API_KEY`, ưu tiên **TrackAsia Place Text Search v2** (`new_admin=true`, `include_old_admin=true`), sau đó fallback sang **OpenStreetMap Nominatim**. Mọi ứng viên đều đi qua bộ lọc độ khớp token định danh riêng (`_is_candidate_relevant`) để loại bỏ kết quả rác khi tìm địa danh không tồn tại. Các điểm cách nhau $\le 500\text{ m}$ (hoặc $\le 3.5\text{ km}$ đối với khu đô thị/KCN/làng đại học rộng) được gộp thành 1 điểm; nếu còn $\ge 2$ cụm phân tán, hệ thống trả `ambiguous = True` kèm `candidates`.
- **Persistent SQLite Cache (`GeocodeCache`):** Lưu bền vững kết quả thành công trên đĩa (`backend/data/geocode_cache.sqlite`, chế độ SQLite WAL) theo khóa chuẩn hóa `(query_norm, hint_norm)` với TTL cấu hình được (`GEOCODE_CACHE_TTL_SECONDS`, mặc định 30 ngày), thay thế cho `@lru_cache` trên RAM.


