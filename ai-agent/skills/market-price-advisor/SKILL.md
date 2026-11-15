---
name: market-price-advisor
description: Kỹ năng tra cứu thống kê giá phòng trọ thực tế (giá trung bình, giá thấp nhất, giá cao nhất, biến động giá và khu vực nổi bật) theo quận/huyện hoặc tỉnh/thành phố.
triggers:
  - giá trung bình
  - giá phòng trọ trung bình
  - mặt bằng giá
  - giá thuê trung bình
  - giá thuê khoảng bao nhiêu
  - giá phòng ở
  - giá trọ ở
  - thống kê giá
follow_ups:
  - Tìm phòng trọ ở khu vực này theo mức giá trung bình
  - Xem phòng trọ giá rẻ nhất tại khu vực này
---

# Kỹ Năng: Tra Cứu Mặt Bằng Giá Thị Trường (Market Price Advisor)

## 🎯 Mục Đích & Phạm Vi
Kỹ năng này giúp Homigo AI cung cấp số liệu thống kê giá thuê thực tế theo khu vực hành chính (Tỉnh/Thành phố, Quận/Huyện) hoặc khu vực lân cận dựa trên dữ liệu tin đăng thật từ hệ thống Backend (`/listings/price-stats`).

---

## 📊 Nguyên Tắc Trình Bày Số Liệu (Chống Ảo Giác)
1. **Tuyệt đối trung thực với `<market_stats>`:**
   - Chỉ sử dụng các con số có trong khối `<market_stats>` được công cụ `get_market_price_stats` trả về.
   - **KHÔNG** tự suy đoán, tự làm tròn quá lệch, hoặc tự bịa giá khu vực nếu hệ thống báo thiếu dữ liệu.
2. **Đầy đủ các chỉ số cốt lõi (nếu có):**
   - **Giá trung bình:** nêu rõ mức giá trung bình/tháng.
   - **Khoảng giá phổ biến (Thấp nhất – Cao nhất):** nêu mức tối thiểu và tối đa để người dùng hình dung biên độ thị trường.
   - **Quy mô mẫu (`total_listings`):** nêu rõ số lượng tin đăng đang được thống kê; nếu mẫu nhỏ (`< 20` tin), nhắc nhẹ người dùng số liệu chỉ mang tính tham khảo.
   - **Phân tích theo khu vực con (`price_stats_by_area` / phường nổi bật):** nếu có dữ liệu theo phường/quận con, tóm tắt ngắn gọn 2–3 khu vực tiêu biểu.
3. **Gợi ý hành động tiếp theo:**
   - Hỏi xem người dùng có muốn tìm phòng trực tiếp tại khu vực đó với ngân sách quanh mức trung bình (hoặc thấp hơn) hay không.
