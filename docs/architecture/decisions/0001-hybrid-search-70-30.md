# 0001: Kiến Trúc Tìm Kiếm Hỗn Hợp (Hybrid Search 70/30)

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-10-15
- **Phạm vi:** `backend/app/repositories/listing_repository.py`, `backend/app/services/listing_service.py`

---

## 1. Bối Cảnh (Context)
Tìm kiếm phòng trọ tại Việt Nam có đặc thù:
- Người dùng tìm kiếm ngữ nghĩa mờ: *"phòng yên tĩnh cho sinh viên ôn thi"*, *"studio gần công viên"*.
- Người dùng tìm kiếm từ khóa chính xác: địa danh (*"Gò Vấp"*, *"Bình Thạnh"*), đường sá (*"Phan Văn Trị"*), tiện ích (*"máy giặt"*, *"gác lửng"*).

Nếu chỉ dùng Dense Vector Search (`pgvector`), các truy vấn từ khóa cụ thể hoặc tên đường hay bị trôi thứ hạng. Nếu chỉ dùng Full-text Search (FTS), các truy vấn giàu cảm xúc hoặc mô tả lối sống không match được.

---

## 2. Quyết Định (Decision)
Áp dụng **Hybrid Search kết hợp tỉ lệ cố định 70/30**:
1. **70% Dense Score:** Tính bằng `1 - Cosine Distance` của vector embedding 768 chiều (`multilingual-e5-base`) lưu trên PostgreSQL qua extension `pgvector` (`HNSW index`).
2. **30% Sparse Score:** Tính bằng PostgreSQL Full-Text Search `ts_rank` trên trường `search_vector` (`tsvector` tiếng Việt).
3. **Pre-filter Bounding Box & Hard Constraints:** Lọc nhanh bằng kinh độ/vĩ độ, khoảng giá, và trạng thái `is_active = true` trước khi tính điểm xếp hạng kết hợp.

$$\text{Final Score} = 0.7 \times \text{Dense Score} + 0.3 \times \text{Sparse Score}$$

---

## 3. Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực:** Độ chính xác tìm kiếm cân bằng xuất sắc giữa hiểu ý định người dùng (Semantic) và bắt đúng từ khóa địa điểm (Keyword Match).
- **Đánh đổi:** Cần duy trì cả chỉ mục vector HNSW và cột `search_vector` (trigger đồng bộ FTS khi cập nhật tin). Thời gian truy vấn SQL cần được tối ưu bằng Bounding Box pre-filter.

