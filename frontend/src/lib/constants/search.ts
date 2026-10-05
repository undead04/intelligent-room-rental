import type { SortOptions } from "@/types";

export interface SortConfig {
  sort_desc: boolean;
  order_by: string;
}

// Map từ ID (number) sang Config
export const SORT_MAP: Record<number, SortConfig> = {
  1: {
    sort_desc: true,
    order_by: "posted_date",
  },
  2: {
    sort_desc: false,
    order_by: "price_vnd",
  },
  3: {
    sort_desc: true,
    order_by: "price_vnd",
  },
};

export const DEFAULT_SORT_ID = 1;

export const SORT_OPTIONS: SortOptions[] = [
  { value: 1, label: "Tin mới nhất" },
  { value: 2, label: "Giá thấp → cao" },
  { value: 3, label: "Giá cao → thấp" },
];