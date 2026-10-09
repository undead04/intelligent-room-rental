import { useEffect, useMemo, useState } from "react";
import type { FilterValues, ListingCardData } from "@/types";
import type { ListingQueryDto } from "@/types/dto";
import { listingsApi } from "@/lib/api/client";
import { toListingCard } from "@/lib/utils/listing";
import { MAX_PRICE_MILLION } from "@/lib/utils/filter";
import { DEFAULT_SORT_ID, SORT_MAP } from "@/lib/constants/search";

const SEARCH_PAGE_SIZE = 20;
const PRICE_UNIT_VND = 1_000_000;

// Kết quả của một request, gắn kèm key để biết nó còn khớp query hiện tại hay không
interface ListingsSnapshot {
  requestKey: string;
  results: ListingCardData[];
  apiError: string | null;
}

interface UseSearchResultsParams {
  search: string;
  filters: FilterValues;
  page: number;
}

export function useSearchResults({ search, filters, page }: UseSearchResultsParams) {
  const [snapshot, setSnapshot] = useState<ListingsSnapshot | null>(null);
  const [totalListings, setTotalListings] = useState<number | null>(null);

  const query = useMemo<ListingQueryDto>(
    () => ({
      search: search || undefined,
      city_id: filters.province ?? undefined,
      district_id: filters.district ?? undefined,
      ward_id: filters.ward ?? undefined,
      room_type_id: filters.roomType ?? undefined,
      min_price: filters.minPrice > 0 ? filters.minPrice * PRICE_UNIT_VND : undefined,
      max_price:
        filters.maxPrice < MAX_PRICE_MILLION ? filters.maxPrice * PRICE_UNIT_VND : undefined,
    }),
    [search, filters],
  );

  // totalListings vừa đổi có thể làm page vượt quá totalPages -> kẹp lại để không hỏi offset vượt
  const totalPages = getTotalPages(totalListings);
  const currentPage = Math.min(Math.max(page, 1), totalPages);
  const offset = (currentPage - 1) * SEARCH_PAGE_SIZE;

  const listParams = useMemo<ListingQueryDto>(() => {
    const sort = SORT_MAP[filters.sort] || SORT_MAP[DEFAULT_SORT_ID];
    return { ...query, ...sort, limit: SEARCH_PAGE_SIZE, offset };
  }, [query, filters.sort, offset]);

  const requestKey = JSON.stringify(listParams);

  useEffect(() => {
    let cancelled = false;

    listingsApi
      .list(listParams)
      .then((listings) => {
        if (!cancelled) {
          setSnapshot({ requestKey, results: listings.map(toListingCard), apiError: null });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setSnapshot({
            requestKey,
            results: [],
            apiError: error instanceof Error ? error.message : "Không thể kết nối API.",
          });
        }
      });

    listingsApi
      .count(query)
      .then((response) => {
        if (!cancelled) setTotalListings(response.total_listings);
      })
      .catch(() => {
        if (!cancelled) setTotalListings(null);
      });

    return () => {
      cancelled = true;
    };
  }, [listParams, query, requestKey]);

  // Chỉ dùng dữ liệu của request hiện tại: đổi query là loading và không còn lỗi cũ
  const isCurrent = snapshot?.requestKey === requestKey;

  return {
    results: isCurrent ? snapshot.results : [],
    totalListings,
    totalPages,
    currentPage,
    apiError: isCurrent ? snapshot.apiError : null,
    isLoading: !isCurrent,
  };
}

function getTotalPages(totalListings: number | null): number {
  if (!totalListings || totalListings <= 0) return 1;
  return Math.ceil(totalListings / SEARCH_PAGE_SIZE);
}