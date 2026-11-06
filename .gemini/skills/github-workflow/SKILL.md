---
name: github-workflow
description: Quy trình Git chuẩn kiểm soát chặt chẽ: Tạo branch, tuyệt đối cấm tự ý commit khi người dùng chưa test và duyệt, hỏi ý kiến trước khi Push/PR, và tự động Merge + Dọn dẹp branch khi người dùng xác nhận.
---

# Skill: Git Workflow Kiểm Soát Chặt Chẽ (Manual Commit, PR & Merge Gate)

Quy tắc cốt lõi: **Agent chỉ là trợ lý gõ lệnh Git ở local. Mọi thao tác Commit, Push, Mở PR, Merge và Xóa Branch đều BẮT BUỘC phải qua sự kiểm tra và phê duyệt của người dùng. TUYỆT ĐỐI CẤM tự ý commit sau mỗi câu trả lời.**

---

## 0. Khởi Đầu Tính Năng Mới (Tạo Branch)
- Luôn đảm bảo đứng từ nhánh `main` mới nhất trước khi tách nhánh:
  ```bash
  git checkout main
  git pull origin main
  git checkout -b feat/<ten-feature>
  ```
- ❌ **CẤM** viết code trực tiếp trên nhánh `main`.

---

## 1. Trong Quá Trình Làm Việc (Giai đoạn Code, Test & Nghiệm Thu Trước Commit)
- **Quy trình chuẩn sau khi code / sửa file:**
  1. Agent chủ động chạy test / linter / parser để tự kiểm chứng kỹ thuật trước.
  2. Trình bày rõ ràng các thay đổi, file đã chỉnh sửa và hướng dẫn kiểm thử cho người dùng.
  3. **DỪNG LẠI (WAITING GATE) — Để người dùng tự tay test và nghiệm thu.**
  4. Giữ nguyên working tree (trạng thái uncommitted), **TUYỆT ĐỐI CẤM tự ý gõ `git commit`**.
- **Khi nào mới được phép commit?**
  - **CHỈ KHI** người dùng kiểm tra xong và ra lệnh rõ ràng bằng văn bản (ví dụ: *"OK commit đi"*, *"Duyệt commit"*, *"Thấy ổn rồi commit đi"*).
  - Lúc đó mới chạy:
    ```bash
    git add <cac-file-thay-doi>
    git commit -m "feat/fix/docs: <thông điệp rõ ràng>"
    ```
- **ĐIỀU CẤM TUYỆT ĐỐI:** 
  - ❌ **CẤM tự ý `git commit` sau mỗi câu trả lời của Agent.**
  - ❌ **CẤM commit khi người dùng chưa kịp test và xác nhận.**
  - ❌ **CẤM tự ý `git push`.**
  - ❌ **CẤM tự ý tạo Pull Request hoặc Merge.**
  - Giữ toàn bộ thay đổi ở local và chỉ commit khi có lệnh.

---

## 2. Khi Nào Mới Được Phép Tạo Pull Request?
Chỉ kích hoạt quy trình Push & PR khi thỏa mãn **MỘT TRONG HAI ĐIỀU KIỆN**:
1. Người dùng ra lệnh đích danh bằng văn bản: *"Đẩy code lên GitHub"* hoặc *"Tạo PR cho tính năng này đi"*.
2. Hoặc Agent nhận thấy đã hoàn thành trọn vẹn feature/mốc lớn, Agent **PHẢI DỪNG LẠI VÀ HỎI Ý KIẾN**:
   > *"Tính năng X đã hoàn thành với N commits ở local. Bạn đã test ưng ý chưa để tui đẩy lên GitHub và mở Pull Request?"*
   👉 **Chỉ khi người dùng gõ "OK / Đồng ý" thì mới được phép push và tạo PR.**

---

## 3. Quy Trình Thực Hiện Khi Được Phép Tạo PR:
1. Đẩy nhánh lên remote:
   ```bash
   git push -u origin <tên-branch>
   ```
2. Nếu máy có `gh` (GitHub CLI):
   ```bash
   gh pr create --base main --head <tên-branch> --title "..." --body "..."
   ```
3. Nếu máy chưa có `gh`: Gửi đường link web GitHub để người dùng bấm tạo PR.

---

## 4. Quy Trình Merge & Xóa Branch Cũ (Merge & Branch Cleanup)
Sau khi PR đã được tạo (hoặc khi người dùng yêu cầu gộp nhánh luôn):
1. **Hỏi xác nhận trước khi Merge:**
   - ❌ **CẤM tự ý merge PR hoặc xóa branch** khi người dùng chưa duyệt.
   - Chỉ thực hiện khi người dùng ra lệnh (*"Merge PR và xóa branch đi"*, *"Gộp vào main luôn nhé"*) hoặc xác nhận đồng ý.
2. **Thực hiện Merge & Dọn dẹp sạch sẽ (Local + Remote):**
   - **Cách 1 — Qua GitHub CLI (`gh`) (Khuyên dùng nếu có PR trên GitHub):**
     ```bash
     # Merge PR vào main và tự động xóa branch trên remote + local
     gh pr merge --merge --delete-branch
     git checkout main
     git pull origin main
     ```
   - **Cách 2 — Qua Git thuần (Nếu merge trực tiếp hoặc dọn dẹp thủ công):**
     ```bash
     # 1. Chuyển về main và cập nhật mới nhất
     git checkout main
     git pull origin main

     # 2. Merge nhánh tính năng vào main (nếu chưa merge trên web) và đẩy lên remote
     git merge --no-ff <tên-branch> -m "Merge branch '<tên-branch>' into main"
     git push origin main

     # 3. Xóa branch ở local
     git branch -d <tên-branch>

     # 4. Xóa branch trên remote GitHub (nếu đã push trước đó)
     git push origin --delete <tên-branch>
     git fetch --prune
     ```
3. **Báo cáo hoàn tất:** Xác nhận với người dùng nhánh `main` đã được đồng bộ code mới nhất và branch `<tên-branch>` đã được dọn dẹp sạch sẽ.

---

## 5. Quy Trình Xử Lý Xung Đột Khi Merge (Merge Conflict Resolution Protocol)

Trong quá trình merge (cả trên GitHub PR lẫn local), nếu xảy ra xung đột mã nguồn (Merge Conflict), Agent **BẮT BUỘC** phải tuân thủ nghiêm ngặt 5 bước sau:

### 5.1. Kiểm Tra Dự Phòng Trước Khi Merge (Pre-Merge Conflict Check)
- Trước khi gõ lệnh merge, Agent phải chủ động kiểm tra trạng thái xung đột:
  ```bash
  # Nếu kiểm tra qua GitHub CLI:
  gh pr view <số-PR> --json mergeable,mergeStateStatus
  # Trạng thái an toàn: mergeable="MERGEABLE", mergeStateStatus="CLEAN"
  # Trạng thái xung đột: mergeable="CONFLICTING", mergeStateStatus="DIRTY"
  ```
  Hoặc kiểm tra cục bộ:
  ```bash
  git fetch origin main
  git merge-tree $(git merge-base origin/main <tên-branch>) origin/main <tên-branch>
  ```

### 5.2. Khi Phát Hiện Xung Đột — Điều Cấm Tuyệt Đối:
- ❌ **DỪNG LẠI NGAY LẬP TỨC!**
- ❌ **CẤM TỰ Ý xóa code** của bất kỳ bên nào mà chưa hỏi ý kiến người dùng.
- ❌ **CẤM tự tiện chạy `git checkout --ours` hoặc `git checkout --theirs`** để ép pass.
- ❌ **CẤM dùng cờ ép buộc (`--force`)**.

### 5.3. Báo Cáo Xung Đột Minh Bạch Cho Người Dùng:
Agent lập tức phản hồi và trình bày rõ 3 thông tin:
1. **Danh sách file bị xung đột:** Liệt kê các file xuất hiện conflict marker (`<<<<<<<`, `=======`, `>>>>>>>`).
2. **Chi tiết đoạn code đụng độ:** Trích dẫn nội dung giữa 2 nhánh:
   - `<<<<<<< HEAD` (Code hiện tại trên nhánh đang đứng / `main`).
   - `=======`
   - `>>>>>>> <tên-branch>` (Code mới từ nhánh tính năng).
3. **Phân tích nguyên nhân & Đề xuất phương án giải quyết:**
   - Đưa ra các phương án cụ thể (ví dụ: Giữ bản mới của feature, hay giữ logic của main, hay kết hợp cả hai).

### 5.4. Chờ Người Dùng Quyết Định (Waiting Gate):
- Agent **DỪNG LẠI** và chờ người dùng chọn phương án xử lý xung đột.
- Tuyệt đối không tự ý quyết định thay người dùng.

### 5.5. Thực Hiện Gỡ Conflict & Kiểm Thử Kiểm Chứng:
Sau khi người dùng đồng ý phương án giải quyết:
1. Agent tiến hành sửa file, loại bỏ toàn bộ conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
2. **Bắt buộc chạy lại bộ lệnh kiểm thử / type-check / lint** của các module liên quan (tham chiếu bảng lệnh chuẩn tại Mục 6 của [`AGENTS.md`](../../../AGENTS.md)) để đảm bảo không gãy logic sau khi gộp.
3. Báo cáo kết quả test pass 100% cho người dùng trước khi thực hiện commit merge hoàn tất.
