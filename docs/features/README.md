# 🚀 Quản Lý Tính Năng (Features & Lifecycle Overview)

Thư mục này quản lý toàn bộ vòng đời của các tính năng kỹ thuật và nghiệp vụ trong hệ thống, phân chia theo 3 trạng thái rõ ràng:

---

## 1. Vòng Đời Tính Năng (Feature Lifecycle)

```text
[ Ý TƯỞNG / YÊU CẦU ]
         │
         ▼
[ 1. backlog/ ]       ─── Tài liệu đặc tả sơ bộ, chờ xếp lịch triển khai
         │
         ▼
[ 2. in-progress/ ]   ─── Đang được AI Agent & Team triển khai trong phiên/sprint hiện tại
         │
         ▼
[ 3. released/ ]      ─── Đã hoàn thành, test suite pass 100%, đã nghiệm thu & bàn giao
```

---

## 2. Danh Sách Tính Năng Theo Trạng Thái

### 🟢 3. Released (Đã phát hành & Vận hành ổn định)
1. [`released/listing-lifecycle-sync.md`](./released/listing-lifecycle-sync.md): Đồng bộ vòng đời tin đăng tự động, ẩn tin hết hạn, cập nhật trạng thái `is_active`.
2. [`released/ml-price-model-v2.md`](./released/ml-price-model-v2.md): Mô hình định giá phòng trọ và dự đoán khoảng giá tin cậy Conformal Prediction.
3. [`released/ai-agent-recommendation-eval.md`](./released/ai-agent-recommendation-eval.md): Bộ chỉ số và kịch bản đo lường chất lượng gợi ý phòng của AI Agent (IR metrics, Compliance, Rubric).

### 🟡 2. In Progress (Đang thực hiện)
- Hiện tại: Kiểm toán toàn diện & khắc phục lỗi logic kiến trúc (tham chiếu [`../fix/README.md`](../fix/README.md)).

### ⚪ 1. Backlog (Dự kiến phát triển)
- Tìm kiếm theo bán kính trạm xe buýt / Metro tuyến số 1.
- Tự động phát hiện tin đăng lặp/trùng lặp nội dung bằng MinHash LSH.

