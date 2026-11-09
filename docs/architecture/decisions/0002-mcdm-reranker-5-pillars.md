# 0002: Mô Hình Tái Xếp Hạng Đa Tiêu Chí (MCDM Reranker 5 Pillars)

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-10-20
- **Phạm vi:** `backend/app/services/reranker.py`, `ai-agent/intelligence/reranker.py`

---

## 1. Bối Cảnh (Context)
Các hệ thống tìm kiếm phòng thông thường chỉ sắp xếp theo giá tăng dần hoặc khoảng cách gần nhất. Tuy nhiên, quyết định thuê phòng của sinh viên và người đi làm phụ thuộc đồng thời vào nhiều yếu tố:
- Giá phòng và chi phí phụ (điện, nước, internet).
- Khoảng cách di chuyển đến trường học/nơi làm việc.
- Mức độ tiện nghi (điều hòa, máy giặt, gác lửng, tủ lạnh).
- An ninh & An toàn PCCC (thang thoát hiểm, camera, khóa vân tay).
- Môi trường & Chất lượng tin đăng (hình ảnh, độ tin cậy của chủ nhà).

---

## 2. Quyết Định (Decision)
Triển khai thuật toán **MCDM (Multi-Criteria Decision Making)** dựa trên chuẩn hóa Min-Max và hàm trọng số động thích ứng theo Persona người dùng:

$$\text{Rerank Score} = w_{\text{price}} \cdot S_{\text{price}} + w_{\text{loc}} \cdot S_{\text{loc}} + w_{\text{amenity}} \cdot S_{\text{amenity}} + w_{\text{safety}} \cdot S_{\text{safety}} + w_{\text{quality}} \cdot S_{\text{quality}}$$

- Các trọng số $w$ tự động điều chỉnh theo 5 nhóm Persona:
  1. `G1_BUDGET_STUDENT`: Ưu tiên giá ($w_{\text{price}} = 0.35$).
  2. `G2_SAFETY_AMENITY`: Ưu tiên an ninh PCCC & tiện nghi ($w_{\text{safety}} = 0.30$, $w_{\text{amenity}} = 0.30$).
  3. `G3_GROUP_FRIENDS`: Ưu tiên diện tích & số phòng.
  4. `G4_WORKER_COMMUTER`: Ưu tiên vị trí & tuyến đường di chuyển ($w_{\text{loc}} = 0.35$).
  5. `G5_BALANCED`: Phân bổ cân bằng.

---

## 3. Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực:** Tăng vượt bậc chỉ số nDCG@5 và mức độ hài lòng thực tế của người dùng theo từng nhóm đối tượng.
- **Đánh đổi:** Cần chuẩn hóa dữ liệu đầu vào nghiêm ngặt để các điểm số thành phần luôn nằm trong khoảng $[0, 1]$.

