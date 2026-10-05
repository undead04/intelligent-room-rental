export interface Listing {
  id: string;
  title: string;
  location: string;
  price: string;
  tag: string;
  source: string;
  image: string;
  time: string;
}

export interface SearchResult {
  id: string;
  title: string;
  type: string;
  location: string;
  price: string;
  area: string;
  verified: boolean;
  source: string;
  time: string;
  image: string;
  tags: string[];
}

export interface FilterQuery extends FilterValues {
  search: string|null;
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