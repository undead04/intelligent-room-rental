# 🤖 AGENTS.md — Quy Chuẩn Làm Việc Cho AI Agent (Homigo)

Tài liệu này là **Hiến pháp làm việc cốt lõi** dành cho mọi AI Coding Agent trong dự án **Homigo**. Mọi thông tin chi tiết về kỹ thuật, quy trình và công cụ được phân tách theo nguyên tắc **Single Source of Truth (SSOT)**:
- 🛠️ **Công nghệ, cổng mạng & Bảng lệnh chuẩn:** Xem [`docs/architecture/tech-stack.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/tech-stack.md).
- 🧩 **Nguyên lý kiến trúc & Thuật toán lõi:** Xem [`docs/architecture/modules/`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/modules/).
- 🗄️ **Mô hình dữ liệu & Database Schemas:** Xem [`docs/architecture/data-models.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/data-models.md).
- 🎨 **Hệ thống thiết kế giao diện:** Xem [`docs/architecture/design-system.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/design-system.md).
- 📋 **Quy chuẩn Lập Plan, Chia Mốc & Review Code:** Xem [`.agents/rules/workflows.md`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/.agents/rules/workflows.md).

---

## 1. ⚡ Đồng Bộ Kiến Trúc Bắt Buộc (Architecture Sync Protocol)

1. **Tra cứu trước khi làm (Session Start):** Khi tiếp nhận bất kỳ tính năng nào liên quan đến Database, ETL, Search, Rerank hay LangGraph, Agent **BẮT BUỘC** phải tự động tham chiếu thư mục [`docs/architecture/`](file:///c:/UIT/Lab/Đồ Án tốt nghiệp/docs/architecture/README.md) để nắm trọn vẹn bối cảnh.
2. **Cập nhật tài liệu khi code đổi kiến trúc (Architecture Update Gate):** Bất cứ khi nào có thay đổi cấu trúc DB, Schema/DTO, luồng thuật toán, Node/Tool LangGraph hoặc thư viện mới, Agent **BẮT BUỘC** phải cập nhật ngay file tương ứng trong `docs/architecture/` trước khi bàn giao. Tuyệt đối không để tài liệu lệch pha với code thực tế.

---

## 2. 🇻🇳 Quy Định Giao Tiếp (Communication Rules)

1. **Ngôn ngữ chính:** Luôn giao tiếp, giải thích, lập kế hoạch và viết docstring/comment bằng **tiếng Việt** rõ ràng, mạch lạc.
2. **Thuật ngữ kỹ thuật:** Giữ nguyên các thuật ngữ tiếng Anh chuyên ngành (ví dụ: *LangGraph, Hybrid Search, MCDM Reranker, Conformal Prediction, SSE, Middleware*).
3. **Trực quan & Dẫn chứng:** Luôn đính kèm đường dẫn liên kết dạng `file:///...` tới file và dòng code cụ thể.

---

## 3. 🎯 Kiểm Soát Phạm Vi & Cổng Commit (Strict Scope & Git Gate)

1. **Chỉ sửa đúng phạm vi (Scope Control):**
   - Chỉ chỉnh sửa các file/hàm trực tiếp liên quan đến yêu cầu hiện tại.
   - **Nghiêm cấm** tự ý refactor, đổi tên biến/hàm, format lại toàn bộ file hoặc thay đổi logic ngoài phạm vi.
   - Bảo toàn toàn bộ comment, docstring và các shim tương thích ngược.
   - Không ghi đè hoặc xóa các file cấu hình `.env`, database SQLite (`*.db`), model cache (`models_cache/`) khi chưa được phép.
2. **Cổng kiểm soát Git (Manual Commit Gate):**
   - **Tuyệt đối CẤM tự ý chạy `git commit` sau mỗi câu trả lời.**
   - Sau khi hoàn thành và chạy test kiểm chứng, Agent phải báo cáo kết quả và **dừng lại chờ người dùng tự kiểm tra, nghiệm thu**.
   - Chỉ khi người dùng ra lệnh rõ ràng (*"OK commit đi"*, *"Duyệt commit"*), Agent mới được phép tạo commit.

---

## 4. 🔄 Tự Đọc Terminal Log & Tự Sửa Lỗi (Self-Healing)

1. **Chủ động đọc Log:** Sau mỗi lệnh chạy qua terminal, luôn kiểm tra kỹ `exit code`, `stdout`, `stderr` và `traceback`.
2. **Phân tích nguyên nhân gốc (Root Cause):** Đọc kỹ stack trace xác định chính xác file và dòng code gây lỗi. Không đoán mò.
3. **Tự sửa & Kiểm chứng lại:** Sửa lỗi trong scope cho phép và **tự động chạy lại test suite** cho đến khi pass 100% trước khi báo cáo kết quả.

---

## 5. 🧩 Cơ Chế Vận Hành Rules, Skills & Orchestrator (`.agents/`)

1. **Kích hoạt Skills tự động (`.agents/skills/`):** Hệ thống tự động nhận diện danh mục kỹ năng trong `.agents/skills/`. Khi gặp tác vụ tương ứng (migration DB, quy trình GitHub, kiểm thử độc lập [`rigorous-testing`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghi%E1%BB%87p/.agents/skills/rigorous-testing/SKILL.md), bảo mật...), Agent tự động áp dụng hướng dẫn từ skill tương ứng ngay trong phiên chính.
2. **Luồng Thực Thi Tinh Gọn (Orchestrator-First — Không lạm dụng Sub-Agents):**
   - **Pha Lập Kế Hoạch (Planning Model):** Trực tiếp khảo sát `docs/architecture/` và mã nguồn, chia mốc theo lát cắt dọc (*Vertical Slice*), tạo Implementation Plan Artifact (khi cần duyệt trước) và bàn giao qua `exit_plan_mode`.
   - **Pha Thực Thi & Kiểm Thử (Execution Model):** Trực tiếp viết code, tự sửa lỗi qua terminal log (*Self-healing*), đồng bộ `docs/architecture/`, và áp dụng skill `rigorous-testing` để viết/chạy Black-box test (4 nhóm) ngay trong phiên chính.
   - **Quy tắc tiết kiệm Token:** **Không gọi lặp `invoke_subagent` tuần tự 3 bước** (`codebase-researcher` $\rightarrow$ `core-developer` $\rightarrow$ `quality-tester`) cho các task đã có Orchestrator điều phối. Chỉ dùng [`.agents/agents/`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghi%E1%BB%87p/.agents/agents/README.md) khi cần khảo sát diện rộng độc lập (*context isolation*) hoặc khi người dùng chủ động yêu cầu `/teamwork`.
