# ISSUE-0001: Bộ Ba Lỗi Logic Kiến Trúc Cốt Lõi Ảnh Hưởng Đến Chất Lượng Gợi Ý & Eval

- **Mã sự cố:** `ISSUE-0001`
- **Trạng thái:** ✅ `RESOLVED` (Đã xử lý, kiểm thử & nghiệm thu xong ngày `2026-11-14`)
- **Mức độ:** 🔴 `CRITICAL`
- **Phạm vi ảnh hưởng:** `backend` (repository, service, schema) & `ai-agent` (schemas, nlu, grounding, eval)

---

## 1. 📊 Bối Cảnh & Đo Lường Hiện Trạng (Baseline)
- Đợt đo lường Baseline ban đầu trên 40 Queries qua 5 Persona cho thấy:
  - `Precision@3`: **63.33%**
  - `Distance Compliance`: **82.67%** (Nhiều phòng ngoài bán kính lọt vào kết quả)
  - `RoomType Compliance`: **75.00%** (Tụt mạnh nhất do thiếu tập đa loại phòng & lọt Sleepbox)

---

## 2. 🔍 Phân Tích Nguyên Nhân Gốc Rễ (Root Cause Analysis - RCA)

### A. Lỗi Hình Học Bounding Box Vuông vs Bán Kính Tròn Haversine
- **Vị trí:** [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/backend/app/repositories/listing_repository.py), [`backend/app/services/listing_service.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/backend/app/services/listing_service.py)
- **Nguyên nhân:** SQL chỉ lọc `lat/lng` theo hình chữ nhật `± delta`. Tin ở góc chéo có khoảng cách $R\sqrt{2} \approx 1.414 R$, vượt xa bán kính tròn người dùng mong muốn.

### B. Thiếu Hỗ Trợ Tập Đa Loại Phòng (`allowed_room_types`)
- **Vị trí:** [`backend/app/schemas/listing.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/backend/app/schemas/listing.py), [`ai-agent/domain/schemas.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/domain/schemas.py), [`ai-agent/safety/grounding.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/safety/grounding.py)
- **Nguyên nhân:** Chỉ hỗ trợ 1 loại phòng đơn trị `room_type`. Khi người dùng muốn tìm *"phòng trọ hoặc căn hộ dịch vụ"*, hệ thống không biểu diễn được nên bỏ qua hoàn toàn bộ lọc.

### C. Lẫn Lộn Giường Tầng KTX (`SLEEPBOX`) vs Không Gian Phòng Riêng
- **Vị trí:** [`ai-agent/intelligence/nlu.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/intelligence/nlu.py)
- **Nguyên nhân:** Sleepbox có giá rất rẻ và an ninh tòa nhà tốt nên điểm MCDM rất cao, chiếm đoạt Top 1 khi người dùng tìm phòng riêng.

---

## 3. 🛠 Giải Pháp Kiến Trúc Đã Triển Khai (Zero Hardcoding)
1. **Hình học không gian:** Giữ Bounding Box làm Pre-filter tốc độ cao ở SQL, bổ sung công thức tính mặt cầu Haversine trực tiếp trong SQL (`ListingRepository.vector_search`) và kiểm tra kép tại `check_hard_constraints`.
2. **Tập loại phòng:** Bổ sung `room_types: Optional[list[str | int]]` tại Backend (`Listing.room_type_id.in_(...)`) và `allowed_room_types: list[RoomType]` tại AI Agent.
3. **Phân tách Sleepbox:** Tự động loại trừ `SLEEPBOX` trong `nlu.py` khi người dùng yêu cầu diện tích $\ge 15m^2$, ở nhiều người, hoặc tiện ích/từ khóa không gian riêng (`private_wc`, `window_balcony`, `mezzanine`, `pet_allowed`, `phòng trọ`...).
4. **Đồng bộ suy luận tiện ích & tương đương ngữ nghĩa:** Bổ sung quy tắc tòa nhà tự quản (`free_hours >= 0.5` & `fingerprint_lock >= 0.5`) tương đương `no_shared_landlord` ở cả `ListingRepository.vector_search`, `check_hard_constraints` và `eval/ir_metrics.py`, đồng bộ `G1_05` (`allowed_room_types=["SLEEPBOX", "ROOM"]`).

---

## 4. ✅ Kết Quả Kiểm Thử & Nghiệm Thu Cuối Cùng (Verified 2026-11-14)
- **Unit & Integration Tests:**
  - `backend/tests/test_vector_search_constraints.py`: Kiểm thử Bounding Box góc chéo Haversine, query đa loại phòng `room_types` và tương đương ngữ nghĩa `no_shared_landlord` pass 100%.
  - `ai-agent/tests/test_grounding.py`, `test_ir_metrics.py`: Kiểm thử `check_hard_constraints` với `allowed_room_types`, loại trừ Sleepbox và tương đương ngữ nghĩa `no_shared_landlord` pass 100%.
- **Kết quả chạy lại Recommendation Benchmark 40 Queries (Offline NLU + Real Backend & PostgreSQL, [`2026-11-recommendation-eval-40queries.md`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/docs/evaluation/reports/2026-11-recommendation-eval-40queries.md)):**
  - `Precision@3`: **93.33%** *(tăng +30.00 điểm % so với Baseline 63.33%)*
  - `Precision@5`: **86.00%**
  - `MRR`: **0.9750** | `nDCG@5`: **0.9750** | `CSR`: **97.50%**
  - `Distance Compliance`: **97.50%** *(đạt & vượt mục tiêu $\ge 90\%$)*
  - `RoomType Compliance`: **97.50%** *(đạt & vượt mục tiêu $\ge 90\%$)*
  - `Price Compliance`: **97.50%** | `Amenities Compliance`: **97.50%**
  - `Judge Overall Score (rule)`: **4.85 / 5.0**
