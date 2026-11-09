---
id: ISSUE-XXXX
title: Tiêu đề ngắn gọn mô tả sự cố hoặc bug
status: IN_PROGRESS # IN_PROGRESS | RESOLVED | WONT_FIX
severity: HIGH # CRITICAL | HIGH | MEDIUM | LOW
affected_modules:
  - backend/services
  - ai-agent/nlu
created_date: YYYY-MM-DD
resolved_date: null
---

# [MÃ_ISSUE]: [Tiêu Đề Sự Cố]

## 1. 🚨 Mô Tả Triệu Chứng (Symptoms)
- Hiện tượng xảy ra là gì?
- Xuất hiện lỗi ở API nào, endpoint nào hoặc câu query nào?
- Log traceback hoặc hình ảnh minh chứng.

---

## 2. 🔍 Phân Tích Nguyên Nhân Gốc Rễ (Root Cause Analysis - RCA)
- Lỗi nằm ở file nào, hàm nào, dòng code nào?
- Tại sao code cũ lại chạy sai trong trường hợp này? (Corner case, race condition, type mismatch, logic flaw...)

---

## 3. 🛠 Phương Án Khắc Phục (Resolution Plan)
- Giải pháp thiết kế tổng quát (tuyệt đối không fix cứng - Zero hardcoding):
- Các file cần chỉnh sửa:
  - `file_path_1`: Thay đổi gì?
  - `file_path_2`: Thay đổi gì?

---

## 4. 🧪 Kịch Bản Kiểm Thử & Nghiệm Thu (Verification)
- Câu lệnh chạy test kiểm chứng:
  ```bash
  pytest path/to/test -k "test_issue_name"
  ```
- Tiêu chí nghiệm thu (Acceptance Criteria):
  - [ ] Test case mô phỏng bug phải pass 100%.
  - [ ] Không gây ảnh hưởng tới các tính năng cũ (Regression check).

