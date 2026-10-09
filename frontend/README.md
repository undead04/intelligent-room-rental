# Next.js Frontend - Smart Housing Decision Support System

Giao diện người dùng cho **Hệ Thống Hỗ Trợ Quyết Định Thuê Phòng Trọ Thông Minh** (Đồ án tốt nghiệp UIT), được xây dựng trên nền tảng **Next.js 16 (App Router)**, **React 19**, **Tailwind CSS v4** và **TypeScript**.

---

## 🛠 Công Nghệ Sử Dụng

* **Framework**: [Next.js 16](https://nextjs.org/) (App Router)
* **Thư viện UI**: [React 19](https://react.dev/)
* **Styling**: [Tailwind CSS v4](https://tailwindcss.com/)
* **Ngôn ngữ**: TypeScript 5
* **Font & Icon**: Plus Jakarta Sans, Google Material Symbols Outlined
* **API Communication**: Fetch API kết nối FastAPI backend

---

## 📁 Cấu Trúc Thư Mục

```text
frontend/
├── public/                      # Static assets (hình ảnh, icons, placeholder)
├── src/
│   ├── app/                     # App Router Pages & Layouts
│   │   ├── layout.tsx           # Root layout chung (Fonts, metadata)
│   │   ├── page.tsx             # Trang chủ (Hero search, tin mới đăng, khu vực hot)
│   │   ├── tim-kiem/            # Trang tìm kiếm & lọc phòng trọ
│   │   │   ├── page.tsx
│   │   │   ├── _components/     # SearchToolbar, ResultsList, Pagination
│   │   │   └── _hooks/          # useSearchResults
│   │   ├── phong-tro/[id]/      # Trang chi tiết phòng trọ
│   │   │   ├── page.tsx
│   │   │   ├── _components/     # DetailBreadcrumb, LandlordCard, SimilarListings...
│   │   │   └── _hooks/          # useListingDetail, useSimilarListings
│   │   └── tra-cuu-gia-tro/     # Trang tra cứu & phân tích thị trường giá trọ
│   │       ├── page.tsx
│   │       ├── _components/     # PriceStatsOverview, PriceStatsFilterBar, PriceStatsTable
│   │       └── _hooks/          # usePriceStats
│   ├── components/              # Các components tái sử dụng (SiteLayout, Header, Footer,
│   │                            # FilterModal, KpiCard, Breadcrumbs, ImageWithFallback...)
│   ├── hooks/                   # Custom React Hooks (useFilterOptions, useLocations...)
│   ├── lib/
│   │   ├── api/                 # API Client gọi đến FastAPI Backend (client.ts)
│   │   ├── constants/           # Hằng số (sort options, property defaults)
│   │   └── utils/               # Helper functions (formatPrice, filter, priceStats...)
│   └── types/                   # Định nghĩa kiểu dữ liệu TypeScript
│       ├── dto/                 # Data Transfer Objects từ backend (ListingDto, CityDto...)
│       └── index.ts             # View-models & types chung cho UI
├── .env.example                 # Mẫu cấu hình biến môi trường
├── package.json                 # Khai báo thư viện & scripts
├── tsconfig.json                # Cấu hình TypeScript
└── README.md                    # Tài liệu hướng dẫn Frontend
```

---

## 🌟 Các Tính Năng Chính

1. **Trang Chủ (`/`)**:
   - Hero banner tích hợp thanh tìm kiếm thông minh theo từ khóa và vị trí.
   - Thẻ hiển thị các phòng trọ mới nhất và danh mục phòng trọ theo khu vực.
2. **Tìm Kiếm & Bộ Lọc Nâng Cao (`/tim-kiem`)**:
   - Lọc đa tiêu chí: Tỉnh/Thành phố, Quận/Huyện, Phường/Xã, Loại phòng, Khoảng giá.
   - Sắp xếp linh hoạt: Tin mới nhất, Giá tăng dần/giảm dần, Diện tích.
   - Phân trang kết quả tìm kiếm với URL query params đồng bộ.
3. **Chi Tiết Phòng Trọ (`/phong-tro/[id]`)**:
   - Thư viện hình ảnh thực tế, mô tả chi tiết, giá thuê, tiền cọc.
   - **Đánh giá an toàn & Tiện ích thông minh**: Hiển thị điểm an toàn (Safety Score) và các concept tiện ích (máy lạnh, gác lửng, ban công, an ninh, wifi...).
   - Thông tin người đăng tin / chủ trọ.
   - **Gợi ý phòng tương tự (`SimilarListings`)**: Tự động gợi ý các phòng cùng khu vực và cùng loại phòng.
4. **Tra Cứu & Báo Cáo Biến Động Giá (`/tra-cuu-gia-tro`)**:
   - Báo cáo thời gian thực về giá trung bình thị trường.
   - Đo lường mức độ biến động giá tăng/giảm so với tháng trước.
   - Xác định khu vực sôi động nhất (Hotspot) kèm tỉ lệ tăng trưởng lượng tin đăng tuyển.
   - Bảng so sánh chi tiết giá min/max/trung bình và xu hướng theo từng quận/phường.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Ứng Dụng

### 1. Yêu cầu hệ thống
* **Node.js**: Phiên bản `>= 18.18.0` hoặc `20.x`
* **Package Manager**: `npm`, `yarn` hoặc `pnpm`

### 2. Cài đặt Dependencies

Từ thư mục `frontend/`:
```bash
npm install
```

### 3. Cấu hình biến môi trường

Tạo file `.env` (hoặc `.env.local`) từ `.env.example`:
```bash
cp .env.example .env.local
```

Nội dung file `.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```
*(Trỏ tới URL của FastAPI backend đang chạy)*

### 4. Khởi chạy Development Server

```bash
npm run dev
```

Mở trình duyệt và truy cập: [http://localhost:3000](http://localhost:3000)

---

## 📦 Scripts Khả Dụng

| Lệnh | Ý nghĩa |
| :--- | :--- |
| `npm run dev` | Khởi động Next.js ở chế độ Development (Hot reload tại port 3000) |
| `npm run build` | Build ứng dụng cho môi trường Production |
| `npm run start` | Khởi chạy server production sau khi đã build |
| `npm run lint` | Kiểm tra lỗi cú pháp và code style với ESLint |
| `npx tsc --noEmit` | Kiểm tra toàn bộ kiểu dữ liệu TypeScript không xuất file |

---

## 🔗 Liên Kết Với Backend

Frontend giao tiếp trực tiếp với Backend FastAPI thông qua module [`src/lib/api/client.ts`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/lib/api/client.ts). 
Đảm bảo Backend đang được khởi chạy ở cổng `8000` trước khi thao tác các tính năng tìm kiếm, phân tích và chi tiết phòng.
