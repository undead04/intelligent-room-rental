---
name: github-workflow
description: Quy trình Git chuẩn kiểm soát chặt chẽ: Phân biệt chế độ Solo Developer (chạy trọn gói Push -> PR -> Merge -> Cleanup sau khi duyệt) và Team Collaboration (chờ review từng cổng), tuyệt đối cấm tự ý commit khi người dùng chưa test.
---

# Skill: Git Workflow Kiểm Soát Chặt Chẽ (Solo Developer Fast-Track & Team Collaboration)

Quy tắc cốt lõi: **Agent chỉ là trợ lý gõ lệnh Git ở local. Điểm dừng duy nhất bắt buộc là CỔNG CHỜ NGHIỆM THU (Waiting Gate) để người dùng tự test. TUYỆT ĐỐI CẤM tự ý commit sau mỗi câu trả lời.**

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

## 1. Giai Đoạn Code, Test & Cổng Chờ Nghiệm Thu (Waiting Gate)
- **Quy trình chuẩn sau khi code / sửa file:**
  1. Agent chủ động chạy test / linter / parser để tự kiểm chứng kỹ thuật trước.
  2. Trình bày rõ ràng các thay đổi, file đã chỉnh sửa và hướng dẫn kiểm thử cho người dùng.
  3. **DỪNG LẠI (WAITING GATE) — Để người dùng tự tay test và nghiệm thu.**
  4. Giữ nguyên working tree (trạng thái uncommitted), **TUYỆT ĐỐI CẤM tự ý gõ `git commit`** khi người dùng chưa xác nhận.

---

## 2. Phân Biệt Hai Chế Độ Vận Hành: Solo Developer vs Team Collaboration

### 🚀 CHẾ ĐỘ 1: SOLO DEVELOPER (MẶC ĐỊNH HIỆN TẠI CỦA DỰ ÁN)
*Khi người dùng làm việc một mình, không cần rườm rà hỏi đi hỏi lại 3-4 lần cho các bước Push, PR, Merge và Xóa branch.*

- **Khi người dùng ra lệnh duyệt** (ví dụ: *"OK duyệt commit & gộp vào main"*, *"Duyệt Mốc X, đẩy lên main luôn nhé"*, *"Push PR đi"*):
  Agent **TỰ ĐỘNG CHẠY TRỌN VẸN CHU TRÌNH KHÉP KÍN (End-to-End Pipeline)** trong một lượt:
  1. **Commit tại local:**
     ```bash
     git add <cac-file-thay-doi>
     git commit -m "feat/fix/docs: <thông điệp rõ ràng>"
     ```
  2. **Push nhánh lên remote:**
     ```bash
     git push -u origin <tên-branch>
     ```
  3. **Tạo PR & Tự động Merge + Dọn dẹp Branch (Nếu có GitHub CLI `gh`):**
     ```bash
     gh pr create --base main --head <tên-branch> --title "feat: <tên-feature>" --body "Tự động merge theo phê duyệt của Solo Developer."
     gh pr merge --merge --delete-branch
     git checkout main
     git pull origin main
     ```
     *Hoặc nếu qua Git thuần (không dùng GitHub CLI):*
     ```bash
     git checkout main
     git pull origin main
     git merge --no-ff <tên-branch> -m "Merge branch '<tên-branch>' into main"
     git push origin main
     git branch -d <tên-branch>
     git push origin --delete <tên-branch>
     git fetch --prune
     ```
  4. **Báo cáo hoàn tất:** Thông báo nhánh `main` đã cập nhật code mới nhất và branch tạm đã được dọn sạch sẽ ở cả local lẫn GitHub. Không hỏi lắt nhắt từng bước con!

---

### 👥 CHẾ ĐỘ 2: TEAM COLLABORATION (CHỈ DÙNG KHI LÀM VIỆC NHÓM)
*Khi có nhiều thành viên cùng đóng góp vào repository, cần quy trình phê duyệt phân tán.*

1. **Push & Tạo PR (Không tự merge):**
   - Đẩy nhánh lên GitHub: `git push -u origin <tên-branch>`
   - Mở Pull Request: `gh pr create --base main --head <tên-branch> ...`
2. **Dừng lại chờ Review (Code Review Gate):**
   - Giữ nguyên PR ở trạng thái Open.
   - Gửi link PR để các thành viên khác trong team review, thảo luận và approve.
3. **Merge sau khi Team duyệt:**
   - Chỉ merge khi toàn bộ CI/CD pass và người dùng/lead xác nhận đồng ý gộp vào `main`.

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
