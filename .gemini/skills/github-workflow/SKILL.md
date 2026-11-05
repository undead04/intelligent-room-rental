---
name: github-workflow
description: Quy trình Git chuẩn kiểm soát chặt chẽ: Chỉ tạo branch và commit theo từng mốc nhỏ. TUYỆT ĐỐI KHÔNG tự ý push hoặc tạo Pull Request nếu người dùng chưa bấm xác nhận hoặc yêu cầu đích danh.
---

# Skill: Git Workflow Kiểm Soát Chặt Chẽ (Manual PR Gate)

Quy tắc cốt lõi: **Agent chỉ là trợ lý gõ lệnh Git ở local, quyền mở PR và Push thuộc về người dùng.**

---

## 1. Trong Quá Trình Làm Việc (Giai đoạn Code & Commit)
Một tính năng (feature) có thể có **rất nhiều commit nhỏ** (chưa hoàn thiện, sửa giao diện, sửa logic...).
- Mỗi khi xong một phần việc nhỏ hoặc hết 1 bước trong task:
  - Chỉ chạy: `git add .`
  - Tạo commit cục bộ: `git commit -m "feat/fix: ..."`
- **ĐIỀU CẤM:** 
  - ❌ **CẤM TỰ Ý `git push`**
  - ❌ **CẤM TỰ Ý tạo Pull Request**
  - Giữ toàn bộ commit ở máy local của người dùng.

---

## 2. Khi Nào Mới Được Phép Tạo Pull Request?
Chỉ kích hoạt quy trình Push & PR khi thỏa mãn **MỘT TRONG HAI ĐIỀU KIỆN**:
1. Người dùng ra lệnh đích danh bằng văn bản: *"Đẩy code lên GitHub"* hoặc *"Tạo PR cho tính năng này đi"*.
2. Hoặc Agent nhận thấy đã hoàn thành trọn vẹn feature lớn, Agent **PHẢI DỪNG LẠI VÀ HỎI Ý KIẾN**:
   > *"Tính năng X đã hoàn thành với N commits ở local. Bạn đã test ưng ý chưa để tui đẩy lên GitHub và mở Pull Request?"*
   👉 **Chỉ khi người dùng gõ "OK / Đồng ý" thì mới được phép push và tạo PR.**

---

## 3. Quy Trình Thực Hiện Khi Được Phép Tạo PR:
1. Đẩy nhánh lên remote:
   ```bash
   git push -u origin <tên-branch>
   ```
2. Nếu máy có `gh`: Tạo PR với tóm tắt các commit đã làm.
3. Nếu máy chưa có `gh`: Gửi đường link web để người dùng tự bấm tạo PR.
