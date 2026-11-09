# ISSUE-0001: Bộ Ba Lỗi Logic Kiến Trúc Cốt Lõi Ảnh Hưởng Đến Chất Lượng Gợi Ý & Eval

- **Mã sự cố:** `ISSUE-0001`
- **Trạng thái:** `IN_PROGRESS` (Đang triển khai)
- **Mức độ:** 🔴 `CRITICAL`
- **Phạm vi ảnh hưởng:** `backend` (repository, service, schema) & `ai-agent` (schemas, nlu, grounding)

---

## 1. 📊 Bối Cảnh & Đo Lường Hiện Trạng (Baseline)
- Đợt đo lường 40 Queries qua 5 Persona cho thấy:
  - `Precision@3`: **63.33%**
  - `Distance Compliance`: **82.67%** (Nhiều phòng ngoài bán kính lọt vào kết quả)
  - `RoomType Compliance`: **75.00%** (Tụt mạnh nhất do thiếu tập đa loại phòng & lọt Sleepbox)

---

## 2. 🔍 Phân Tích Nguyên Nhân Gốc Rễ (Root Cause Analysis - RCA)

### A. Lỗi Hình Học Bounding Box Vuông vs Bán Kính Tròn Haversine
- **Vị trí:** `backend/app/repositories/listing_repository.py`, `backend/app/services/listing_service.py`
- **Nguyên nhân:** SQL chỉ lọc `lat/lng` theo hình chữ nhật `± delta`. Tin ở góc chéo có khoảng cách $R\sqrt{2} \approx 1.414 R$, vượt xa bán kính tròn người dùng mong muốn.

### B. Thiếu Hỗ Trợ Tập Đa Loại Phòng (`allowed_room_types`)
- **Vị trí:** `backend/app/schemas/listing.py`, `ai-agent/domain/schemas.py`, `ai-agent/safety/grounding.py`
- **Nguyên nhân:** Chỉ hỗ trợ 1 loại phòng đơn trị `room_type`. Khi người dùng muốn tìm *"phòng trọ hoặc căn hộ dịch vụ"*, hệ thống không biểu diễn được nên bỏ qua hoàn toàn bộ lọc.

### C. Lẫn Lộn Giường Tầng KTX (`SLEEPBOX`) vs Không Gian Phòng Riêng
- **Vị trí:** `ai-agent/intelligence/nlu.py`
- **Nguyên nhân:** Sleepbox có giá rất rẻ và an ninh tòa nhà tốt nên điểm MCDM rất cao, chiếm đoạt Top 1 khi người dùng tìm phòng riêng.

---

## 3. 🛠 Giải Pháp Kiến Trúc Tổng Quát (Zero Hardcoding)
1. **Hình học không gian:** Giữ Bounding Box làm Pre-filter tốc độ cao ở SQL, bổ sung công thức tính mặt cầu Haversine trực tiếp trong SQL và kiểm tra kép tại `check_hard_constraints`.
2. **Tập loại phòng:** Bổ sung `room_types: Optional[list[str | int]]` tại Backend (`room_type_id.in_(...)`) và `allowed_room_types: list[RoomType]` tại AI Agent.
3. **Phân tách Sleepbox:** Tự động loại trừ Sleepbox khi người dùng yêu cầu diện tích $\ge 15m^2$ hoặc tiện ích không gian riêng (`private_wc`, `kitchen`, `window_balcony`).

---

## 4. 🧪 Kế Hoạch Kiểm Thử & Tiêu Chí Đóng Issue
- `backend/tests`: Bổ sung test kiểm thử Bounding Box góc chéo và query đa loại phòng.
- `ai-agent/tests`: Bổ sung test kiểm thử `check_hard_constraints` với `allowed_room_types` và loại trừ Sleepbox.
- Chạy lại recommendation eval 40 queries: `Distance Compliance` và `RoomType Compliance` phải đạt $\ge 90\%$.

