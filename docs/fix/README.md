# 🛠 Báo Cáo Kiểm Toán & Kế Hoạch Cải Tiến Hệ Thống (`backend` & `ai-agent`)

> **Nhánh triển khai:** `fix/audit-backend-agent-eval` (tách từ `main`)  
> **Mục tiêu cốt lõi:** Kiểm toán lỗi logic, dọn dẹp code thừa / code phiên bản cũ (Clean Code), và cải tiến khách quan năng lực gợi ý của `ai-agent` thông qua hệ thống đo lường `eval` với nguyên tắc **100% tổng quát hóa kiến trúc — tuyệt đối không fix cứng (zero hardcoding)**.

---

## 1. 📊 Hiện Trạng Đo Lường Baseline (`eval` & Test Suites)

### 1.1. Kiểm thử Đơn vị & Tích hợp (Unit / Integration Tests)
- `backend/tests`: **45 passed**
- `ai-agent/tests`: **532 passed**

### 1.2. Chỉ số Recommendation Evaluation Baseline (40 Queries × 5 Nhóm Persona)
Nguồn đối chiếu: [`ai-agent/eval_results/recommendation_evaluation_report.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/eval_results/recommendation_evaluation_report.md)

| Nhóm Chỉ số | Chỉ số | Baseline | Nhận định Gốc rễ |
| :--- | :--- | :---: | :--- |
| **IR Metrics** | `Precision@3 (P@3)` | **63.33%** | Nhiều phòng vi phạm bán kính tròn hoặc sai tập loại phòng lọt vào Top 3 |
| **IR Metrics** | `Precision@5 (P@5)` | **58.00%** | Tụt mạnh ở nhóm `G3_GROUP_FRIENDS` (30.0%) và `G2_SAFETY_AMENITY` (57.5%) |
| **IR Metrics** | `MRR` | **0.7458** | `SLEEPBOX` giá siêu rẻ chiếm Top 1 ở các ca tìm phòng độc lập |
| **IR Metrics** | `nDCG@5` | **0.7779** | Thứ tự xếp hạng bị nhiễu bởi ứng viên ngoài bán kính tròn |
| **IR Metrics** | `CSR` | **65.17%** | Tỷ lệ thỏa mãn đồng thời mọi ràng buộc còn thấp |
| **Compliance** | `Price Compliance` | **92.50%** | Tốt (3/40 ca trả 0 phòng do giới hạn nguồn cung thực tế trong DB) |
| **Compliance** | `Distance Compliance` | **82.67%** | **Lỗi hình học Bounding Box** ($R\sqrt{2} \approx 1.414R$) lọt góc chéo |
| **Compliance** | `RoomType Compliance` | **75.00%** | **Điểm nghẽn lớn nhất:** thiếu tập `allowed_room_types` & lọt `SLEEPBOX` |
| **Compliance** | `Amenities Compliance` | **92.50%** | Tốt, cần đồng bộ ngữ nghĩa `safe_area` / `furniture` & đủ 17 tags |
| **Judge Rubric** | `Overall Score` | **3.98 / 5.0** | Relevance `3.53`, Ranking `3.80`, Faithfulness `4.78` |
| **Component Eval** | `Thesis 5 Pillars Rubric` | **100.0 / 100.0** | Guardrail, Grounding, Adaptive Radius, MCDM unit rubrics đạt chuẩn |

---

## 2. 🔍 Báo Cáo Kiểm Toán Chi Tiết (`backend/` & `ai-agent/`)

### 2.1. Nhóm Lỗi Logic Kiến Trúc Cốt Lõi (Ảnh hưởng trực tiếp tới Chất lượng Gợi ý & Eval)

1. **[CRITICAL] Thiếu hỗ trợ tập đa loại phòng cho phép (`allowed_room_types` / `room_types`) xuyên suốt Pipeline:**
   - **Vị trí:** [`backend/app/schemas/listing.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/schemas/listing.py#L156-L161), [`backend/app/api/v1/controllers/listings_controller.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/api/v1/controllers/listings_controller.py#L140-L165), [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/listing_service.py#L279-L305), [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py#L273-L294), [`ai-agent/domain/schemas.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/domain/schemas.py#L295-L302), [`ai-agent/intelligence/nlu.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/nlu.py#L112-L115), [`ai-agent/safety/grounding.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/safety/grounding.py#L87-L117).
   - **Hiện trạng:** Hệ thống chỉ có `room_type` đơn trị (1 loại) và `excluded_room_types`. Khi nhu cầu người dùng mở cho một tập loại phòng hợp lệ (ví dụ: *"phòng trọ hoặc căn hộ dịch vụ"*, *"studio hoặc chung cư"*), hệ thống không biểu diễn được `allowed_room_types` $\rightarrow$ mất hoàn toàn bộ lọc loại phòng! Đồng thời [`check_hard_constraints`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/safety/grounding.py#L87-L117) chỉ kiểm tra `excluded_room_types`, bỏ quên kiểm tra `room_type` và `allowed_room_types`.
   - **Giải pháp tổng quát:** Bổ sung `room_types: Optional[list[str | int]]` ở Backend (`Listing.room_type_id.in_(...)`) và `allowed_room_types: list[RoomType]` ở AI-Agent (`PreferencePatch`, `UserPreferenceState`, `retrieval_node`, `search_rooms_api`, `check_hard_constraints`), giữ tương thích ngược 100% với `room_type` đơn trị.

2. **[CRITICAL] Sai số Hình học Không gian (Bounding Box vuông vs Bán kính tròn Haversine):**
   - **Vị trí:** [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py#L306-L316), [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/listing_service.py#L300-L329), [`ai-agent/safety/grounding.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/safety/grounding.py#L75-L117).
   - **Hiện trạng:** SQL chỉ cắt theo hình chữ nhật `lat ± delta, lng ± delta`. Các tin đăng nằm ở 4 góc hình vuông có khoảng cách thực tế lên tới $R\sqrt{2} \approx 1.414 R$ (ví dụ bán kính 3.0 km nhưng trả về phòng cách 4.09 km). Thêm vào đó, `check_hard_constraints` chưa kiểm tra `max_distance_km`.
   - **Giải pháp tổng quát:** Giữ Bounding Box làm *Spatial Index Pre-filter* tốc độ cao, bổ sung công thức Haversine cầu mặt đất trực tiếp trong SQL (`ListingRepository.vector_search`), kiểm chứng kép ở `ListingService.vector_search` và `check_hard_constraints` (`safety/grounding.py`).

3. **[CRITICAL] Phân tách nguyên lý mô hình thuê giường cá nhân (`SLEEPBOX`) vs Không gian phòng độc lập:**
   - **Vị trí:** [`ai-agent/intelligence/nlu.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/nlu.py#L469-L491).
   - **Hiện trạng:** `SLEEPBOX` (giường tầng / hộp ngủ KTX) có giá danh nghĩa rất thấp (1.2–1.8 triệu/giường) và thường gắn camera/khóa vân tay chung của tòa nhà, nên đạt điểm `price_fit` và `safety_score` rất cao trong MCDM Reranker, dễ chiếm Top 1 khi người dùng tìm phòng riêng mà không nói câu phủ định *"không ở KTX"*. Logic hiện tại trong `_postprocess` mới bắt vài cụm từ rời rạc.
   - **Giải pháp tổng quát (Domain-driven):** Mô hình hóa đúng bản chất miền bài toán: `SLEEPBOX` là suất ngủ cá nhân dùng chung phòng. Khi truy vấn thể hiện nhu cầu **không gian phòng ở riêng biệt** (yêu cầu diện tích phòng `min_area >= 15`, tiện ích không gian riêng như `private_wc`, `kitchen`, `window_balcony`, `pet_allowed`, `no_shared_landlord`, hoặc tìm *phòng/căn hộ* mà không đề cập KTX/sleepbox/ở ghép giường), hệ thống tự động loại trừ `SLEEPBOX` trừ khi người dùng chủ động cho phép `SLEEPBOX` trong `room_type` / `allowed_room_types`.

4. **[HIGH] Bất đồng bộ Pipeline trong Offline Eval Runner & Thiếu 6 nhãn `_CONCEPT_TAGS`:**
   - **Vị trí:** [`ai-agent/eval/run_recommendation_eval.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/eval/run_recommendation_eval.py#L288-L355), [`ai-agent/domain/schemas.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/domain/schemas.py#L50-L63).
   - **Hiện trạng:**
     - Trong `_execute_offline_nlu_search`, sau khi chạy `valid, _ = check_hard_constraints(items, pref)` lại trả về `rooms=rooms[:5]` (danh sách thô chưa qua lọc) thay vì `valid_rooms[:5]` như `retrieval_node` thật, và bỏ qua `allowed_room_types` khi `len(rts) > 1`.
     - `_CONCEPT_TAGS` trong `domain/schemas.py` chỉ có 11/17 tiện ích, thiếu `washing_machine`, `no_shared_landlord`, `safe_area`, `fingerprint_lock`, `camera`, `guard`, làm `inferred_tags` và `compact_listing_detail` bị khuyết thông tin tiện ích an ninh/sinh hoạt.
     - Trong `ListingRepository.vector_search` và `safety/grounding.py`, tiêu chí tổng hợp `safe_area` cần xét đồng bộ `safe_area >= 0.5` hoặc có thiết bị/điểm an ninh tương đương (`camera >= 0.5`, `fingerprint_lock >= 0.5`, `guard >= 0.5`, `safety_score >= 0.7`), và `furniture` xét đồng bộ `furniture >= 0.5` hoặc `furnishing_code IN (1, 2)`.

### 2.2. Nhóm Lỗi Logic Phụ Trợ & Edge Cases (`backend/` & `ai-agent/`)

5. **[HIGH] Scope Binding trong `verify_answer_grounding` chưa nhận diện `"Top 1..N"`:**
   - [`ai-agent/safety/grounding.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/safety/grounding.py#L469-L491) chỉ tìm `r.id` trong câu văn để gắn scope kiểm tra giá/diện tích/khoảng cách từng phòng, trong khi prompt cấm LLM in `r.id` và yêu cầu gọi `"Top 1"`, `"Top 2"`. Cần map cả `"Top k"` / `"Phòng số k"` về đúng `RoomItem` có `rank == k`.
6. **[HIGH] Lỗi `strip_accents` lệch vế trong `understand.py` & Keyword Override mù phủ định:**
   - [`ai-agent/intelligence/understand.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/understand.py#L224-L322): So sánh chuỗi đã bỏ dấu (`clean_user_text`) với chuỗi có dấu (`am.label_vi.lower()`, `"thú cưng"`) khiến nhánh phát hiện tiện ích mới khi rollback luôn `False`. Nhánh bắt từ khóa `"phong xin hon"` chưa loại trừ ngữ cảnh phủ định (`"không cần..."`, `"đừng..."`).
7. **[MEDIUM] Phân giải địa chỉ `"Phường, Tỉnh/Thành"` & Geocoding `hint`:**
   - [`ai-agent/tools/location_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tools/location_service.py#L288-L347): Khi nhập `"Linh Trung, TP.HCM"` (bỏ qua cấp Quận/TP Thủ Đức), `resolve_admin` chỉ dò `district` thuộc `city` mà chưa fallback dò `ward` thuộc `city_id`; đồng thời geocoding `hint` chưa tận dụng đuôi cấp `district`.
8. **[MEDIUM] An toàn tham số Tool, DTO Serialization & Session Lifecycle:**
   - [`ai-agent/tools/housing_tools.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tools/housing_tools.py#L121-L185): Đảm bảo `query` mặc định an toàn nếu rỗng, clamp `max_distance_km` vào `[0.5, 50.0]`, hỗ trợ `room_types` và bổ sung tham số cho `@tool search_rooms`.
   - [`ai-agent/core/session_store.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/core/session_store.py#L71-L255): Đóng kết nối `sqlite3.Connection` bằng `contextlib.closing` để tránh rò rỉ file descriptor trên Windows; giới hạn kích thước `turn_snapshots` (giữ snapshot gốc lượt đầu + cửa sổ trượt các lượt gần nhất).
   - [`ai-agent/domain/budget.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/domain/budget.py#L24) & [`ai-agent/graph/replies.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/graph/replies.py#L129): Đồng bộ hằng số `GAP_RATIO` để không lệch thông báo thiếu ngân sách.
   - [`ai-agent/graph/nodes/retrieval.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/graph/nodes/retrieval.py#L222-L228): Không ghi đè `search_args["max_distance_km"]` trước khi xác nhận lần gọi mở rộng bán kính thành công.
   - [`ai-agent/intelligence/insights.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/insights.py#L44-L47): Bổ sung chủ ngữ rõ ràng cho `price_trade_off` khi hai phòng đồng giá nhưng chênh diện tích.
   - [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py) & [`location_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/location_repository.py): Lọc đồng bộ trạng thái tin đăng công khai (`is_active == True` kèm `status IS NULL OR lower(status) == 'active'`).
   - [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/listing_service.py#L20-L77): Dùng `datetime.now(timezone.utc)` chuẩn timezone-aware.

### 2.3. Nhóm Code Thừa / Dead Code & Code Version Cũ (Clean Code)

| Dịch vụ | File | Hạng mục Clean Code / Nâng cấp chuẩn mới |
| :--- | :--- | :--- |
| `backend` | [`app/core/database.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/core/database.py#L33) | Thay `declarative_base()` (SQLAlchemy 1.x legacy) bằng `class Base(DeclarativeBase): pass` chuẩn SQLAlchemy 2.0 |
| `backend` | [`app/services/geocoder.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/geocoder.py#L17-L21) | Xóa hàm dead code `_strip_accents`; tái sử dụng `requests.Session` & `@lru_cache(maxsize=256)` |
| `backend` | [`app/services/reranker.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/reranker.py#L80) | Xóa biến alias thừa `_NORMALIZE_AMENITY = _normalize_amenity` |
| `ai-agent` | [`core/config.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/core/config.py#L40) | Chuyển dict `model_config` sang `ConfigDict(frozen=True, extra="ignore")` chuẩn Pydantic v2 |
| `ai-agent` | [`api/sse.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/api/sse.py#L145) | Chuẩn hóa `final_resp.model_dump(mode="json", by_alias=True)` khi phát sự kiện SSE |
| `ai-agent` | [`api/routes.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/api/routes.py#L84-L89) | Dọn bỏ phương thức dead code `_build_decision_insights` không được gọi |
| `ai-agent` | [`intelligence/understand.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/understand.py#L348-L360) | Xóa bản sao trùng lặp của `route_after_understand`, thay bằng re-export từ `graph.routing`; cập nhật docstring cũ |
| `ai-agent` | [`tools/housing_tools.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tools/housing_tools.py#L392-L404) | Gọn hóa fallback trong `consult_skill` và xóa các dòng trống thừa |
| `ai-agent` | [`eval/run_recommendation_eval.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/eval/run_recommendation_eval.py#L59) | Import `compute_normalized_weights` trực tiếp từ `intelligence.intent_weights` |

> [!NOTE]
> Các shim tương thích ngược có chủ đích gồm [`ai-agent/service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/service.py) và [`backend/app/core/security_middleware.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/core/security_middleware.py) được **giữ nguyên 100%** theo Quy tắc Bảo toàn Tương thích Ngược tại `AGENTS.md` Mục 3.2.

---

## 3. 🗺 Kế Hoạch Triển Khai Chia Theo Mốc (Vertical Slices & Subagents `flash`)

Toàn bộ Subagents thực thi (`core-developer`, `quality-tester`) đều bắt buộc chạy với **`Model: "flash"`**.

### MỐC 1: Nâng cấp Backend Hybrid Search, Không gian Haversine, Đa loại phòng & Clean Code
- **Phạm vi file (`backend/`):**
  1. [`backend/app/core/database.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/core/database.py)
  2. [`backend/app/main.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/main.py)
  3. [`backend/app/schemas/listing.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/schemas/listing.py)
  4. [`backend/app/api/v1/controllers/listings_controller.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/api/v1/controllers/listings_controller.py)
  5. [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/listing_repository.py) & [`location_repository.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/repositories/location_repository.py)
  6. [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/listing_service.py), [`geocoder.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/geocoder.py), [`reranker.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/app/services/reranker.py)
- **Phân công Subagents (`Model: "flash"`):**
  - `[x]` `[codebase-researcher]` Hoàn tất kiểm toán toàn bộ `backend/`.
  - `[x]` `[core-developer]` Triển khai lọc `room_types`, lọc bán kính tròn Haversine SQL + Service, ánh xạ ngữ nghĩa `safe_area`/`furniture`, lọc `status` an toàn, `timezone.utc`, vá `jsonable_encoder` cho `RequestValidationError` (422) và Clean Code SQLAlchemy 2.0 / Geocoder / Reranker.
  - `[x]` `[quality-tester]` Viết Black-box tests đủ 4 nhóm tại [`backend/tests/test_vector_search_constraints.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/backend/tests/test_vector_search_constraints.py) và chạy `pytest backend/tests -q` đạt **56/56 passed (100%)**.

### MỐC 2: Nâng cấp AI-Agent Domain, Grounding, NLU/Retrieval Generalization & Clean Code
- **Phạm vi file (`ai-agent/` — Phần 2A: Domain, Safety, NLU, Understand):**
  1. [`ai-agent/domain/schemas.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/domain/schemas.py)
  2. [`ai-agent/safety/grounding.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/safety/grounding.py)
  3. [`ai-agent/intelligence/nlu.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/nlu.py)
  4. [`ai-agent/intelligence/understand.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/understand.py)
- **Phạm vi file (`ai-agent/` — Phần 2B: Tools, Retrieval, Session, Budget, API Clean Code):**
  5. [`ai-agent/tools/housing_tools.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tools/housing_tools.py) & [`ai-agent/tools/location_service.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tools/location_service.py)
  6. [`ai-agent/graph/nodes/retrieval.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/graph/nodes/retrieval.py) & [`ai-agent/graph/replies.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/graph/replies.py)
  7. [`ai-agent/core/session_store.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/core/session_store.py), [`ai-agent/core/config.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/core/config.py), [`ai-agent/intelligence/insights.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/intelligence/insights.py), [`ai-agent/api/sse.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/api/sse.py), [`ai-agent/api/routes.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/api/routes.py)
- **Phân công Subagents (`Model: "flash"`):**
  - `[x]` `[codebase-researcher]` Hoàn tất kiểm toán toàn bộ `ai-agent/`.
  - `[x]` `[core-developer]` Thực thi Phần 2A (Domain `allowed_room_types`, 17 `_CONCEPT_TAGS`, Grounding Haversine + Allowed RoomTypes + Scope Binding `Top k`, NLU Domain Generalization, Understand bugfix & Clean Code).
  - `[x]` `[core-developer]` Thực thi Phần 2B (Tools validation & `room_types`, Location fallback `ward` in `city`, Retrieval safe mutation, Session SQLite closing & snapshot cap, Budget `GAP_RATIO`, API/Config Clean Code).
  - `[x]` `[quality-tester]` Viết Black-box tests đủ 4 nhóm tại [`ai-agent/tests/test_generalized_constraints_and_clean_code.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/tests/test_generalized_constraints_and_clean_code.py) và chạy `pytest ai-agent/tests -q` đạt **543/543 passed (100%)**.

### MỐC 3: Đồng bộ Eval Pipeline, Đo Lường Thực Nghiệm Before/After & Đồng bộ Kiến Trúc
- **Phạm vi file:**
  1. [`ai-agent/eval/run_recommendation_eval.py`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/eval/run_recommendation_eval.py)
  2. [`docs/architecture/system-principles.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/system-principles.md) & [`docs/architecture/data-models.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/data-models.md)
  3. [`docs/fix/README.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/fix/README.md) (cập nhật bảng kết quả Eval Before vs After & phân tích điểm dừng tối ưu)
- **Phân công Subagents (`Model: "flash"`):**
  - `[x]` `[core-developer]` Đồng bộ `_execute_offline_nlu_search` khớp 100% pipeline `retrieval_node` (`allowed_room_types` + `valid_rooms[:5]`), dọn import sạch sẽ và cập nhật tài liệu kiến trúc.
  - `[x]` `[quality-tester]` Kiểm tra live Backend port `8000` nạp code mới, chạy bộ `eval` (`run_recommendation_eval.py`, `eval.run`, `thesis_eval_rubric`, `pytest` toàn hệ thống), xuất báo cáo đối chiếu số liệu Before vs After và chứng minh trần tối ưu hóa.

---

## 4. 📈 Kết Quả Thực Nghiệm Before vs After & Phân Tích Điểm Hội Tụ Tối Ưu (Oracle Ceiling)

### 4.1. Đối Chiếu Chỉ Số Recommendation Evaluation (40 Queries × 5 Nhóm Persona)
Nguồn báo cáo sau cải tiến: [`ai-agent/eval_results/recommendation_evaluation_report.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/ai-agent/eval_results/recommendation_evaluation_report.md)

| Chỉ số Đo lường | Baseline (Before) | Sau Cải tiến (After) | Thay đổi ($\Delta$) | Trần Vật Lý DB (Oracle Ceiling) |
| :--- | :---: | :---: | :---: | :---: |
| **`Precision@3 (P@3)`** | 63.33% | **82.50%** | **+19.17%** | ~83.33% |
| **`Precision@5 (P@5)`** | 58.00% | **76.00%** | **+18.00%** | **76.50%** *(Đạt 99.35% trần DB)* |
| **`MRR`** | 0.7458 | **0.8750** | **+0.1292** | **0.8750** *(Đạt 100.0% trần DB)* |
| **`nDCG@5`** | 0.7779 | **0.8750** | **+0.0971** | **0.8750** *(Đạt 100.0% trần DB)* |
| **`CSR` (Toàn tập 40 ca)** | 65.17% | **87.50%** | **+22.33%** | **87.50%** *(100% trên 35/35 ca có phòng)* |
| **`Distance Compliance`** | 82.67% | **87.50%** | **+4.83%** | **87.50%** *(0% rò rỉ góc chéo)* |
| **`RoomType Compliance`** | 75.00% | **87.50%** | **+12.50%** | **87.50%** *(0% rò rỉ sai loại phòng)* |
| **`Relevance Score`** | 3.53 / 5.0 | **4.50 / 5.0** | **+0.97** | — |
| **`Ranking Score`** | 3.80 / 5.0 | **4.32 / 5.0** | **+0.52** | — |
| **`Judge Overall Score`** | 3.98 / 5.0 | **4.48 / 5.0** | **+0.50** | — |

### 4.2. Cải Thiện Đột Phá Theo Nhóm Persona
- **`G2_SAFETY_AMENITY`:** `P@3` từ `58.3%` $\rightarrow$ **`100.0%`**, `P@5` từ `57.5%` $\rightarrow$ **`100.0%`**, `CSR` từ `57.5%` $\rightarrow$ **`100.0%`**, `Judge` từ `3.64` $\rightarrow$ **`4.91 / 5.0`**.
- **`G4_PREMIUM_STUDIO`:** `P@3` từ `66.7%` $\rightarrow$ **`91.7%`**, `P@5` từ `62.5%` $\rightarrow$ **`90.0%`**, `CSR` từ `76.2%` $\rightarrow$ **`100.0%`**, `Judge` từ `4.30` $\rightarrow$ **`4.92 / 5.0`**.
- **`G1_BUDGET`:** `P@3` từ `70.8%` $\rightarrow$ **`87.5%`**, `CSR` từ `70.6%` $\rightarrow$ **`87.5%`**, `Judge` từ `4.20` $\rightarrow$ **`4.51 / 5.0`**.
- **`G3_GROUP_FRIENDS`:** `P@3` từ `37.5%` $\rightarrow$ **`50.0%`**, `CSR` từ `41.5%` $\rightarrow$ **`62.5%`** (100% trên cả 5 ca thực sự có nguồn cung trong DB).

### 4.3. Chứng Minh Điểm Dừng Tối Ưu (Why Further Tuning Stops Here)
Quét vét cạn (Exhaustive Oracle Scan) trên toàn bộ **10,408 tin đăng active** trong PostgreSQL đối với 5 truy vấn trả về `0 phòng` (`G1_05`, `G3_02`, `G3_05`, `G3_07`, `G5_04`) xác nhận:
- Cả 5 truy vấn đều có **`TRUE DB MATCHES = 0`** trong cơ sở dữ liệu thực tế (ví dụ: tìm KTX Khu B dưới 1.2 triệu hoặc phòng $\ge 35\text{m}^2$ gần HUTECH có đồng thời gác lửng + kệ bếp + không chung chủ dưới 6 triệu).
- Trên toàn bộ **35/35 truy vấn có tồn tại nguồn cung trong DB**, hệ thống đã đạt **`RR = 1.00`**, **`nDCG@5 = 1.00`** và **`CSR = 1.00` (100% phòng trả về thỏa mãn trọn vẹn mọi ràng buộc cứng, không có phòng vi phạm lọt lưới)**.
- Việc dừng tối ưu tại đây đảm bảo hệ thống **không rơi vào Overfitting hay tự ý nới lỏng trái phép ràng buộc cứng của người dùng** khi nguồn cung thực tế bằng 0 (trong trường hợp đó `ai-agent` kích hoạt nhánh *Zero-result Market Advisory* để tư vấn mặt bằng giá và khu vực lân cận một cách trung thực).

### 4.4. Tổng Hợp Kiểm Thử Toàn Hệ Thống
- **Backend Pytest:** `56 passed` (tăng từ 45 tests).
- **AI-Agent Pytest:** `543 passed` (tăng từ 532 tests).
- **Thesis 5-Pillar Rubric:** `100.0 / 100.0` (`EXCELLENT`).
- **Guardrail & Answer Grounding Suite:** `0.0%` false positive trên câu sạch, `100.0% (480/480)` bắt trúng lỗi số liệu tiêm vào.
- **Frontend Lint & Type-Check (`npx tsc --noEmit`):** `0 errors`.

