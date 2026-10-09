// View-model dùng chung cho mọi nơi render tin đăng (trang chủ, tìm kiếm, ...)
export interface ListingCardData {
  id: string;
  title: string;
  location: string;
  price: string;
  badge: string;
  source: string;
  image: string;
  time: string;
  area?: string;
}

export interface FilterValues {
  province: number|null;
  district: number|null;
  ward: number|null;
  roomType: number|null;
  minPrice: number;
  maxPrice: number;
  sort: number;
}

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface SortOptions {
  label: string;
  value: number;
}

export * from "./dto";