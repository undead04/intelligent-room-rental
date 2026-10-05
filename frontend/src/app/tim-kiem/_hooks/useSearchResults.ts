import { useEffect, useMemo, useState } from "react";
import type { FilterValues, SearchResult } from "@/types";
import type { ListingQueryDto } from "@shared/dto";
import { listingsApi } from "@/lib/api/client";
import { toSearchResult } from "@/lib/utils/listing";
import { MAX_PRICE_MILLION } from "@/lib/utils/filter";
import { DEFAULT_SORT_ID, SORT_MAP } from "@/lib/constants/search";

const SEARCH_PAGE_SIZE = 20;
const PRICE_UNIT_VND = 1_000_000;

interface UseSearchResultsParams {
  search: string;
  filters: FilterValues;
}

export function useSearchResults({ search, filters }: UseSearchResultsParams) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalListings, setTotalListings] = useState<number | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

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

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setApiError(null);

    const sort = SORT_MAP[filters.sort] || SORT_MAP[DEFAULT_SORT_ID];

    listingsApi
      .list({ ...query, ...sort, limit: SEARCH_PAGE_SIZE })
      .then((listings) => {
        if (!cancelled) setResults(listings.map(toSearchResult));
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResults([]);
          setApiError(error instanceof Error ? error.message : "Không thể kết nối API.");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
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
  }, [query, filters.sort]);

  return { results, totalListings, apiError, isLoading };
}