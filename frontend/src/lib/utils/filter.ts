import { FilterValues } from "@/types";
import { SORT_OPTIONS } from "@/lib/constants/search";

export const MAX_PRICE_MILLION = 15;

export const DEFAULT_FILTERS: FilterValues = {
  province: null,
  district: null,
  ward: null,
  roomType: null,
  minPrice: 0,
  maxPrice: MAX_PRICE_MILLION,
  sort: 1,
};

export function countActiveFilters(f: FilterValues): number {
  let n = 0;
  if (f.province) n++;
  if (f.district) n++;
  if (f.ward) n++;
  if (f.roomType) n++;
  if (f.minPrice > DEFAULT_FILTERS.minPrice || f.maxPrice < DEFAULT_FILTERS.maxPrice) n++;
  if (f.sort !== DEFAULT_FILTERS.sort) n++;
  return n;
}

export function buildSearchParams(
  search: string,
  f: FilterValues,
  page = 1,
): URLSearchParams {
  const params = new URLSearchParams();
  if (search.trim()) params.set("q", search.trim());
  if (f.province) params.set("city_id", String(f.province));
  if (f.district) params.set("district_id", String(f.district));
  if (f.ward) params.set("ward_id", String(f.ward));
  if (f.roomType) params.set("room_type_id", String(f.roomType));
  if (f.minPrice > DEFAULT_FILTERS.minPrice) params.set("min_price", String(f.minPrice));
  if (f.maxPrice < DEFAULT_FILTERS.maxPrice) params.set("max_price", String(f.maxPrice));
  if (f.sort !== DEFAULT_FILTERS.sort) params.set("sort", String(f.sort));
  if (page > 1) params.set("page", String(page));
  return params;
}

export const SEARCH_PATH = "/tim-kiem";

export function buildSearchUrl(search: string, f: FilterValues, page = 1): string {
  const qs = buildSearchParams(search, f, page).toString();
  return `${SEARCH_PATH}${qs ? `?${qs}` : ""}`;
}

const toId = (value: string | null): number | null => {
  const n = Number(value);
  return value && Number.isInteger(n) && n > 0 ? n : null;
};

const toPrice = (value: string | null, fallback: number): number => {
  if (value === null || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(Math.max(n, 0), MAX_PRICE_MILLION) : fallback;
};

export function parseSearchParams(
  params: URLSearchParams,
): { search: string; filters: FilterValues; page: number } {
  const sort = toId(params.get("sort"));
  const page = toId(params.get("page")) ?? 1;
  return {
    search: params.get("q") ?? "",
    filters: {
      province: toId(params.get("city_id")),
      district: toId(params.get("district_id")),
      ward: toId(params.get("ward_id")),
      roomType: toId(params.get("room_type_id")),
      minPrice: toPrice(params.get("min_price"), DEFAULT_FILTERS.minPrice),
      maxPrice: toPrice(params.get("max_price"), DEFAULT_FILTERS.maxPrice),
      sort: sort && sort <= SORT_OPTIONS.length ? sort : DEFAULT_FILTERS.sort,
    },
    page,
  };
}
