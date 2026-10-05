"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import SearchResultCard from "@/components/SearchResultCard";
import Breadcrumbs from "@/components/Breadcrumbs";
import { ListingCardSkeleton } from "@/components/LoadingSkeleton";
import type { FilterValues, SearchResult, SortOptions } from "@/types";
import { listingsApi, locationsApi, roomTypesApi } from "@/lib/api/client";
import { toSearchResult } from "@/lib/utils/listing";
import {
  buildSearchParams,
  countActiveFilters,
  MAX_PRICE_MILLION,
  parseSearchParams,
} from "@/lib/utils/filter";
import type { CityDto, DistrictDto, RoomTypeDto } from "@shared/dto";

interface SortConfig {
  sort_desc: boolean;
  order_by: string;
}

// Map từ ID (number) sang Config
const SORT_MAP: Record<number, SortConfig> = {
  1: {
    sort_desc: true,
    order_by: 'posted_date',
  },
  2: {
    sort_desc: false,
    order_by: 'price_vnd',
  },
  3: {
    sort_desc: true,
    order_by: 'price_vnd',
  },
};

const sortOptions: SortOptions[] = [
  { value: 1, label: "Tin mới nhất" },
  { value: 2, label: "Giá thấp → cao" },
  { value: 3, label: "Giá cao → thấp" },
];

function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramsKey = searchParams.toString();

  // URL là nguồn dữ liệu duy nhất
  const { search, filters } = useMemo(
    () => parseSearchParams(new URLSearchParams(paramsKey)),
    [paramsKey],
  );

  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [searchInput, setSearchInput] = useState(search);
  const [cities, setCities] = useState<CityDto[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomTypeDto[]>([]);
  const [districtOptions, setDistrictOptions] = useState<DistrictDto[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [totalListings, setTotalListings] = useState<number | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const activeFilterCount = countActiveFilters(filters);

  const navigate = (q: string, f: FilterValues) => {
    const qs = buildSearchParams(q, f).toString();
    router.push(`/tim-kiem${qs ? `?${qs}` : ""}`);
  };

  // Đồng bộ ô tìm kiếm khi URL đổi (back/forward, áp dụng bộ lọc...)
  useEffect(() => setSearchInput(search), [search]);

  // Dữ liệu cho modal
  useEffect(() => {
    locationsApi.cities().then(setCities).catch(() => setCities([]));
    roomTypesApi.list().then(setRoomTypes).catch(() => setRoomTypes([]));
  }, []);

  // Danh sách quận cho chip
  useEffect(() => {
    locationsApi
      .districts(filters.province ? { city_id: filters.province } : undefined)
      .then(setDistrictOptions)
      .catch(() => setDistrictOptions([]));
  }, [filters.province]);


  const query = useMemo(
    () => ({
      search: search || undefined,
      city_id: filters.province ?? undefined,
      district_id: filters.district ?? undefined,
      ward_id: filters.ward ?? undefined,
      room_type_id: filters.roomType ?? undefined,
      min_price: filters.minPrice > 0 ? filters.minPrice * 1_000_000 : undefined,
      max_price: filters.maxPrice < MAX_PRICE_MILLION ? filters.maxPrice * 1_000_000 : undefined,
    }),
    [search, filters],
  );
  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setApiError(null);

    // Fetch listings
    let sort = SORT_MAP[filters.sort] || SORT_MAP[1];
    listingsApi
      .list({ ...query, ...sort, limit: 20 })
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
      .then((r) => !cancelled && setTotalListings(r.total_listings))
      .catch(() => !cancelled && setTotalListings(null));

    return () => {
      cancelled = true;
    };
  }, [query, filters.sort]);

  const selectedDistrictName = districtOptions.find((d) => d.id === filters.district)?.name;

  return (
    <SiteLayout className="bg-[#FAF8F4]" onOpenFilter={() => setIsFilterOpen(true)}>
      <main className="w-full flex-1 max-w-[1500px] mx-auto px-4 lg:px-8 py-6">
        <Breadcrumbs
          className="mb-3"
          items={[{ label: "Trang chủ", href: "/" }, { label: "TP. Hồ Chí Minh" }]}
        />

        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] mb-4">
          Phòng trọ, nhà ở, căn hộ TP. Hồ Chí Minh
        </h1>        

        {/* Sticky search & filter bar */}
        <div className="sticky top-[72px] z-30 bg-[#FAF8F4]/95 backdrop-blur-md py-3 flex items-center gap-3">
          <Link
            href="/"
            className="w-11 h-11 shrink-0 rounded-full bg-white border border-[#E8E4DC] hover:bg-[#E9F7F0] flex items-center justify-center text-gray-700 shadow-xs transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
          </Link>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              navigate(searchInput, filters);
            }}
            className="flex-1 relative flex items-center bg-white border border-[#E8E4DC] rounded-full px-5 py-2.5 shadow-xs"
          >
            <span className="material-symbols-outlined text-[#0F5F4A] mr-3 text-[20px]">search</span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={`Hồ Chí Minh · ${selectedDistrictName ?? "Tất cả"}`}
              className="flex-1 bg-transparent text-sm font-semibold text-[#121E1A] placeholder:text-[#6F7974] outline-none"
            />
          </form>

          <button
            onClick={() => setIsFilterOpen(true)}
            className="relative w-11 h-11 shrink-0 rounded-full bg-white border border-[#0F5F4A] hover:bg-[#E9F7F0] text-[#0F5F4A] flex items-center justify-center shadow-xs transition-all"
            title="Mở bộ lọc"
          >
            <span className="material-symbols-outlined text-[20px]">tune</span>
            {activeFilterCount > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold flex items-center justify-center">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {/* Result summary */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-600">
            <span className="material-symbols-outlined text-[#0F5F4A] text-[18px]">bolt</span>
            <span>
              Tìm thấy <strong className="text-[#121E1A] font-bold">{totalListings ?? "..."}</strong> kết quả
              tại Hồ Chí Minh
            </span>
          </div>
          {apiError && <p className="text-xs text-[#9A3412]">Lỗi tải dữ liệu: {apiError}</p>}
        </div>

        {/* Listings */}
        {!isLoading && results.length === 0 ? (
          <div className="py-16 text-center text-sm text-gray-500 mb-12">
            Không tìm thấy phòng phù hợp. Hãy thử bỏ bớt bộ lọc hoặc đổi từ khóa.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
            {isLoading
              ? Array.from({ length: 6 }, (_, i) => <ListingCardSkeleton key={i} />)
              : results.map((item) => <SearchResultCard key={item.id} item={item} />)}
          </div>
        )}

        {/* Pagination: giữ nguyên block cũ (hiện vẫn là số cứng) */}
      </main>

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        provinces={cities}
        roomTypes={roomTypes}
        sortOptions={sortOptions}
        initialValues={filters}
        onApply={(values) => navigate(search, values)}
      />
    </SiteLayout>
  );
}

export default function SearchPage() {
  return (
    <Suspense fallback={null}>
      <SearchPageContent />
    </Suspense>
  );
}