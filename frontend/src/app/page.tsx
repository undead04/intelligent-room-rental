"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import ListingSection from "@/components/ListingSection";
import AiSearchPromo from "@/app/_components/AiSearchPromo";
import HeroSearch from "@/app/_components/HeroSearch";
import WhyChooseHomigo from "@/app/_components/WhyChooseHomigo";
import { useHomeListings } from "@/app/_hooks/useHomeListings";
import type { FilterValues } from "@/types";
import ListingSectionSkeleton from "@/components/skeleton/ListingSectionSkeleton";
import { buildSearchParams, countActiveFilters, DEFAULT_FILTERS } from "@/lib/utils/filter";
import { SORT_OPTIONS } from "@/lib/constants/search";

export default function HomePage() {
  const router = useRouter();
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [filters, setFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [searchQuery, setSearchQuery] = useState("");

  const { listings, cities, roomTypes, isLoading } = useHomeListings();

  const activeFilterCount = countActiveFilters(filters);

  const goToSearch = (query: string, values: FilterValues) => {
    const qs = buildSearchParams(query, values).toString();
    router.push(`/tim-kiem${qs ? `?${qs}` : ""}`);
  };

  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    goToSearch(searchQuery, filters);
  };

  return (
    <SiteLayout className="bg-[#FAF8F4]" onOpenFilter={() => setIsFilterOpen(true)}>

      <main className="w-full flex-1">
        <HeroSearch
          query={searchQuery}
          activeFilterCount={activeFilterCount}
          onQueryChange={setSearchQuery}
          onOpenFilter={() => setIsFilterOpen(true)}
          onSubmit={submitSearch}
        />

        <div className="max-w-[1500px] mx-auto px-4 lg:px-8 py-8">
          {isLoading ? (
            <ListingSectionSkeleton />
          ) : (
            <ListingSection
              title="Phòng trọ mới nhất"
              description="Những tin đăng được cập nhật gần đây nhất từ Homigo"
              listings={listings}
            />
          )}
          <AiSearchPromo />
          <WhyChooseHomigo />
        </div>
      </main>

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        provinces={cities}
        roomTypes={roomTypes}
        sortOptions={SORT_OPTIONS}
        initialValues={filters}
        onApply={(values) => {
          setFilters(values);
          goToSearch(searchQuery, values);
        }}
      />
    </SiteLayout>
  );
}