# 🎨 Hệ Thống Thiết Kế Giao Diện (Frontend Design System)

Tài liệu này là **Nguồn Sự Thật Duy Nhất (Single Source of Truth)** về phong cách thị giác, bảng màu, typography, và quy chuẩn component cho phân hệ **Frontend (Next.js 16 + Tailwind CSS)** và làm ngữ cảnh chuẩn mực khi sinh giao diện qua **Stitch UI (StitchMCP)**.

---

## 1. 🌿 Triết Lý Thiết Kế: Modern Housing & Clean Minimalist

Giao diện Homigo theo phong cách **Hiện đại, Tối giản & Thân thiện (Modern Housing UI)**:
- **Nền kem lúa mạch nhẹ nhàng (`#FAF8F4`):** Giúp mắt dễ chịu khi duyệt danh sách phòng lâu, không bị chói như nền trắng tinh công nghiệp.
- **Màu thương hiệu Xanh ngọc lục bảo (`#0F5F4A`):** Tượng trưng cho sự an tâm, tin cậy và chuyên nghiệp của một nền tảng tìm phòng thông minh.
- **Điểm nhấn Hổ phách ấm (`#E88C38`):** Làm nổi bật giá thuê, điểm số phù hợp và các ưu đãi quan trọng.
- **Bố cục dạng thẻ (Card-based layout):** Bo góc mềm mại (`rounded-2xl`), viền mảnh thanh lịch (`#D8E4DF`), tối ưu cho cả giao diện điện thoại và máy tính.

---

## 2. 🎨 Bảng Mã Màu Chuẩn (Color Tokens)

### 2.1. Màu Nền & Bề Mặt (Background & Surface)
| Tên Token | Mã Hex / Tailwind | Ý Nghĩa Sử Dụng |
| :--- | :--- | :--- |
| `bg-primary` | `#FAF8F4` | Nền chính của toàn trang (Base background). |
| `surface-card` | `#FFFFFF` | Nền của các thẻ (`ListingCard`, `KpiCard`, Modal). |
| `surface-soft` | `#F5F2EB` | Nền phụ, thanh search bar, dropdown container. |
| `surface-accent` | `#E6F4EE` | Nền badge tag xanh mạ nhạt, tag tiện ích nổi bật. |

### 2.2. Màu Thương Hiệu & Điểm Nhấn (Brand & Accents)
| Tên Token | Mã Hex / Tailwind | Ý Nghĩa Sử Dụng |
| :--- | :--- | :--- |
| `brand-primary` | `#0F5F4A` | Màu chủ đạo: Nút bấm chính, icon mốc bản đồ, active tab. |
| `brand-hover` | `#0B4A39` | Hover state cho các thành phần primary. |
| `accent-warm` | `#E88C38` | Giá thuê nổi bật, tag giá tốt, badge so sánh Top 1. |
| `status-warning` | `#D97706` / `bg-amber-50` | Cảnh báo backend, thông báo nhắc nhở nhẹ. |
| `status-danger` | `#DC2626` / `bg-red-50` | Lỗi kết nối, tin phòng đã hết hạn (`is_active = false`). |

### 2.3. Màu Văn Bản & Đường Viền (Typography & Borders)
| Tên Token | Mã Hex / Tailwind | Ý Nghĩa Sử Dụng |
| :--- | :--- | :--- |
| `text-main` | `#121E1A` | Chữ tiêu đề chính, tên phòng trọ, độ tương phản cao. |
| `text-muted` | `#4A5550` | Chữ nội dung mô tả, địa chỉ, thông tin phụ. |
| `text-subtle` | `#6F7974` | Chú thích nhỏ, ngày đăng, footer credit. |
| `border-subtle` | `#D8E4DF` | Viền thẻ card, đường kẻ phân cách, đường bao input. |
| `border-divider` | `#E8E4DC` | Đường viền trong các bảng thông số kỹ thuật. |

---

## 3. ✍️ Quy Chuẩn Typography & Phông Chữ

- **Font chữ chính (Main Font):** `'Be Vietnam Pro', sans-serif`  
  - Tối ưu hóa hoàn hảo cho dấu thanh Tiếng Việt, nét tròn trịa thân thiện.
- **Font chữ phụ (Accent Display):** `'Plus Jakarta Sans', sans-serif`  
  - Dùng cho các con số KPI, tiêu đề Hero Banner hoặc thẻ thống kê.
- **Phân cấp cỡ chữ (Type Scale):**
  - **H1 (Hero Heading):** `text-3xl sm:text-4xl font-extrabold tracking-tight`
  - **H2 (Section Heading):** `text-xl sm:text-2xl font-bold`
  - **H3 (Card Title):** `text-base sm:text-lg font-bold line-clamp-1`
  - **Body Text:** `text-sm leading-relaxed text-[#4A5550]`
  - **Caption / Meta:** `text-xs font-medium text-[#6F7974]`

---

## 4. 🧩 Quy Chuẩn Thành Phần (Component Patterns)

### 4.1. Nút Bấm (Buttons)
- **Primary Button:**  
  `bg-[#0F5F4A] hover:bg-[#0B4A39] text-white font-bold rounded-xl px-5 py-2.5 shadow-xs transition cursor-pointer`
- **Secondary / Filter Button:**  
  `bg-white hover:bg-[#F5F2EB] border border-[#D8E4DF] text-[#121E1A] font-semibold rounded-xl px-4 py-2 transition`
- **Pill Tag Button:**  
  `rounded-full px-3 py-1 text-xs font-semibold border`

### 4.2. Thẻ Tin Đăng (Listing Card)
- **Bo góc & Viền:** `rounded-2xl border border-[#D8E4DF] bg-white overflow-hidden shadow-xs hover:shadow-md transition duration-200`
- **Ảnh đại diện:** Tỉ lệ `aspect-4/3` hoặc `h-48 w-full object-cover` kèm `ImageWithFallback`.
- **Hộp giá (Price Badge):** Chữ đậm màu `#0F5F4A` hoặc `#E88C38` (`text-base sm:text-lg font-extrabold`).

### 4.3. Thanh Tìm Kiếm & Bộ Lọc (Search & Filters)
- **Container:** `bg-white/95 backdrop-blur-md rounded-2xl border border-[#D8E4DF] shadow-sm p-3`
- **Input Fields:** `bg-[#FAF8F4] border-transparent focus:border-[#0F5F4A] rounded-xl text-sm`

---

## 5. 🤖 Hướng Dẫn Tích Hợp Cho Stitch UI (Prompting Context)

Khi yêu cầu **Stitch UI** hoặc Sub-Agent thiết kế một màn hình mới (ví dụ: Trang chi tiết phòng, Modal so sánh phòng, Giao diện Chat AI):

```text
Prompt mẫu cho Stitch UI:
"Thiết kế màn hình [Tên Màn Hình] theo đúng Homigo Design System:
- Nền trang: #FAF8F4, thẻ card màu trắng bo góc rounded-2xl viền #D8E4DF.
- Màu chủ đạo: Xanh ngọc lục bảo #0F5F4A, điểm nhấn hổ phách #E88C38.
- Font chữ: Be Vietnam Pro, phong cách hiện đại tối giản, rõ ràng, thân thiện.
- Giữ nguyên các component chuẩn: Navbar, Footer, Tag tiện ích bo tròn."
```

