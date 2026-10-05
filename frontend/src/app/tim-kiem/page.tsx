"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import ListingCard from "@/components/ListingCard";
import Breadcrumbs from "@/components/Breadcrumbs";
import ListingCardSkeleton from "@/components/skeleton/ListingCardSkeleton";
import SearchToolbar from "@/app/tim-kiem/_components/SearchToolbar";
import { useDistrictOptions } from "@/hooks/useLocations";
import { useFilterOptions } from "@/hooks/useFilterOptions";
import { useSearchResults } from "@/app/tim-kiem/_hooks/useSearchResults";
import type { FilterValues } from "@/types";
import { buildSearchParams, countActiveFilters, parseSearchParams } from "@/lib/utils/filter";
import { SORT_OPTIONS } from "@/lib/constants/search";
import { Pagination } from "@/components/pagination/Pagination";

function SearchPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const paramsKey = searchParams.toString();

  // URL là nguồn dữ liệu duy nhất
  const { search, filters, page } = useMemo(
    () => parseSearchParams(new URLSearchParams(paramsKey)),
    [paramsKey],
  );

  const [isFilterOpen, setIsFilterOpen] = useState(false);

  // Ô tìm kiếm gắn với từ khóa trên URL: back/forward hoặc áp dụng bộ lọc sẽ tự về giá trị của URL
  const [searchInput, setSearchInput] = useState({ search, value: search });
  const searchText = searchInput.search === search ? searchInput.value : search;
  const handleSearchInputChange = (value: string) => setSearchInput({ search, value });

  const { cities, roomTypes } = useFilterOptions();
  const districtOptions = useDistrictOptions(filters.province);

  const { results, totalListings, totalPages, currentPage, apiError, isLoading } =
    useSearchResults({ search, filters, page });

  const activeFilterCount = countActiveFilters(filters);

  // Đổi từ khóa/bộ lọc thì về trang 1, chỉ đổi trang thì giữ nguyên bộ lọc
  const navigate = (query: string, values: FilterValues, nextPage = 1) => {
    const qs = buildSearchParams(query, values, nextPage).toString();
    router.push(`/tim-kiem${qs ? `?${qs}` : ""}`);
  };

  const selectedDistrictName = districtOptions.find((d) => d.id === filters.district)?.name;

  return (
    <SiteLayout className="bg-[#FAF8F4]">
      <main className="w-full flex-1 max-w-[1500px] mx-auto px-4 lg:px-8 py-6">
        <Breadcrumbs
          className="mb-3"
          items={[{ label: "Trang chủ", href: "/" }, { label: "TP. Hồ Chí Minh" }]}
        />

        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] mb-4">
          Phòng trọ, nhà ở, căn hộ TP. Hồ Chí Minh
        </h1>

        <SearchToolbar
          query={searchText}
          placeholder={`Hồ Chí Minh · ${selectedDistrictName ?? "Tất cả"}`}
          activeFilterCount={activeFilterCount}
          onQueryChange={handleSearchInputChange}
          onSubmit={(event) => {
            event.preventDefault();
            navigate(searchText, filters);
          }}
          onOpenFilter={() => setIsFilterOpen(true)}
        />

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
              : results.map((item) => <ListingCard key={item.id} item={item} />)}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={(nextPage) => navigate(search, filters, nextPage)}
          />
        )}
      </main>

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        provinces={cities}
        roomTypes={roomTypes}
        sortOptions={SORT_OPTIONS}
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