# Template báo cáo tìm phòng

Dùng đúng cấu trúc dưới đây. Thay các phần `[...]` bằng dữ liệu thật từ API. Tên field của phòng có thể khác (`title`, `price`, `area`, `address`, `distance`, `score`...), hãy ánh xạ theo response thực tế.

---

## Báo cáo gợi ý phòng: [khu vực / địa điểm]

### 1. Tóm tắt nhu cầu

- **Vị trí**: [địa điểm hoặc phường/quận đã dùng]. [Nếu geocode ra địa điểm hơi khác ý người dùng, ghi giả định ở đây]
- **Ngân sách**: [khoảng giá] / tháng
- **Yêu cầu khác**: [diện tích, loại phòng, nhu cầu mềm]
- **Kết quả**: tìm được [N] phòng phù hợp (bán kính [x] km / trong [phường])

### 2. Bảng so sánh [N] phòng

| # | Phòng | Giá/tháng | Diện tích | Khoảng cách | Điểm nổi bật |
|---|-------|-----------|-----------|-------------|--------------|
| 1 | [tiêu đề + địa chỉ ngắn] | [giá] | [m²] | [km] | [1 ý chính] |
| 2 | ... | ... | ... | ... | ... |

Quy tắc:
- Giữ nguyên thứ tự API trả về (đã xếp theo độ phù hợp), không tự xáo trộn.
- Ô nào không có dữ liệu thì ghi "n/a".
- Giá viết dạng dễ đọc: `2.800.000đ`.

### 3. Vì sao phòng #1 được chọn

**[Tiêu đề phòng #1]** ([giá], [diện tích], [địa chỉ])

Đối chiếu từng tiêu chí của người dùng:

| Tiêu chí người dùng | Phòng #1 đáp ứng thế nào |
|---------------------|--------------------------|
| [Gần UIT] | [Cách điểm đến 0,8 km, đi bộ khoảng 10 phút] |
| [Ngân sách ≤ 3tr] | [2.800.000đ, thấp hơn trần 200.000đ] |
| [Cho nuôi mèo] | [Mô tả tin đăng ghi rõ cho nuôi thú cưng] |

**Hơn phòng #2 ở đâu**: [1-2 câu so sánh trực tiếp: rẻ hơn, gần hơn, hoặc khớp nhu cầu mềm hơn].

**Điểm cần lưu ý**: [điểm yếu thật của phòng #1, ví dụ không có chỗ để xe, giá điện cao, thông tin chưa đầy đủ]. Nêu trung thực để người dùng không bị bất ngờ khi đi xem.

### 4. Lựa chọn thay thế

Nêu 1-2 phòng trong danh sách phù hợp với một ưu tiên khác (rẻ nhất, gần nhất, rộng nhất), mỗi phòng một câu giải thích.

### 5. Bước tiếp theo

- Gợi ý đi xem [phòng #1, #2] trước và nên hỏi chủ nhà về [điểm cần xác minh].
- Hỏi người dùng có muốn nới/thu hẹp tiêu chí nào (bán kính, giá, khu vực) để tìm lại không.

---

## Nguyên tắc viết

- Chỉ dùng thông tin có trong kết quả API. Thiếu thì ghi "chưa có thông tin".
- Phần giải thích top 1 phải dựa trên số liệu cụ thể (giá, khoảng cách, tiện nghi), tránh những câu chung chung như "phòng này rất tốt".
- Nếu số phòng ít hơn 10, ghi đúng số lượng, không kéo dài cho đủ.
- Viết bằng tiếng Việt, giọng thân thiện, ngắn gọn.