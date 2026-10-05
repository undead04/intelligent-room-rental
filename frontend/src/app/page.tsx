"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import ListingSection from "@/components/ListingSection";
import { FilterValues, Listing, SortOptions } from "@/types";
import { listingsApi, locationsApi, roomTypesApi } from "@/lib/api/client";
import { ListingSectionSkeleton } from "@/components/LoadingSkeleton";
import { toHomeListing } from "@/lib/utils/listing";
import { buildSearchParams, countActiveFilters, DEFAULT_FILTERS } from "@/lib/utils/filter";
import { CityDto, RoomTypeDto } from "@shared/dto/listing";

const sortOptions: SortOptions[] = [
  { value: 1, label: "Tin mới nhất" },
  { value: 2, label: "Giá thấp → cao" },
  { value: 3, label: "Giá cao → thấp" },
];

export default function HomePage() {
  const router = useRouter();
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [filters, setFilters] = useState<FilterValues>(DEFAULT_FILTERS);
  const [searchQuery, setSearchQuery] = useState("");
  const [apiListings, setApiListings] = useState<Listing[]>([]);
  const [apiCities, setApiCities] = useState<CityDto[]>([]);
  const [apiRoomTypes, setApiRoomTypes] = useState<RoomTypeDto[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const activeFilterCount = countActiveFilters(filters);

  const submitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const qs = buildSearchParams(searchQuery, filters).toString();
    router.push(`/tim-kiem${qs ? `?${qs}` : ""}`);
  };

  useEffect(() => {
    Promise.all([listingsApi.list({ limit: 8 }), locationsApi.cities(), roomTypesApi.list()])
      .then(([listings, cities, roomTypes]) => {
        setApiListings(listings.map(toHomeListing));
        setApiCities(cities);
        setApiRoomTypes(roomTypes);
      })
      .catch(() => {
        setApiListings([]);
        setApiCities([]);
        setApiRoomTypes([]);
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <SiteLayout className="bg-[#FAF8F4]" onOpenFilter={() => setIsFilterOpen(true)}>

      <main className="w-full flex-1">
        {/* HERO SEARCH AREA */}
        <section className="w-full bg-gradient-to-b from-[#EFFDF6] via-[#EFFDF6]/70 to-[#FAF8F4] pt-6 pb-4">
          <div className="max-w-4xl mx-auto px-4 flex flex-col items-center text-center">
            <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#0F5F4A] tracking-tight mb-2">
              Tìm phòng trọ, căn hộ ưng ý cùng AI
            </h1>
            <p className="text-sm sm:text-base text-[#3F4944] mb-6">
              Hàng ngàn tin đăng được xác thực mỗi ngày từ các nguồn uy tín
            </p>

            {/* Pill Search Bar */}
            <form onSubmit={submitSearch} className="w-full relative flex items-center bg-white rounded-full h-14 border border-[#E8E4DC] shadow-[0_4px_20px_rgba(15,95,74,0.06)] px-5 gap-3 transition-shadow focus-within:shadow-[0_6px_24px_rgba(15,95,74,0.12)]">
              <span className="material-symbols-outlined text-[#6F7974] text-[22px] shrink-0">search</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Bạn muốn tìm phòng ở đâu? (vd: gần ĐH Bách Khoa, dưới 4 triệu...)"
                className="w-full h-full bg-transparent text-sm text-[#121E1A] placeholder:text-[#6F7974] outline-none"
              />
              <button
                type="button"
                onClick={() => setIsFilterOpen(true)}
                className="relative flex items-center cursor-pointer justify-center w-10 h-10 rounded-full bg-[#E9F7F0] hover:bg-[#E3F1EA] text-[#0F5F4A] transition-colors shrink-0 "
                title="Mở bộ lọc nâng cao"
              >
                <span className="material-symbols-outlined text-[20px]">tune</span>
                {activeFilterCount > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold shadow-sm">
                    {activeFilterCount}
                  </span>
                )}

              </button>
              <button type="submit" className="px-5 py-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-sm font-semibold transition-all shrink-0 hidden sm:inline-flex items-center gap-1.5">
                <span>Tìm</span>
              </button>
            </form>
          </div>
        </section>

        <div className="max-w-[1500px] mx-auto px-4 lg:px-8 py-8">
          {isLoading ? (
            <ListingSectionSkeleton />
          ) : (
            <ListingSection
              title="Phòng trọ mới nhất"
              description="Những tin đăng được cập nhật gần đây nhất từ Homigo"
              listings={apiListings}
            />
          )}
          <section className="w-full mb-12 rounded-2xl border border-[#DCECE4] bg-[#F1FBF6] p-5 sm:p-7">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-11 h-11 rounded-full bg-[#0F5F4A] text-white flex items-center justify-center shrink-0">
                  <span className="material-symbols-outlined text-[22px]">auto_awesome</span>
                </div>
                <div>
                  <h2 className="font-['Plus_Jakarta_Sans'] font-extrabold text-lg text-[#121E1A]">
                    Tìm kiếm thông minh với AI
                  </h2>
                  <p className="text-xs sm:text-sm text-[#4A5550] mt-1">
                    Mô tả nhu cầu, Homigo sẽ giúp bạn tìm căn phòng phù hợp nhất.
                  </p>
                </div>
              </div>
              <Link
                href="/tim-kiem-ai"
                className="inline-flex items-center gap-1.5 rounded-full bg-[#FF6B4A] px-5 py-2.5 text-xs font-bold text-white hover:bg-[#e85b3d] transition-colors"
              >
                Thử ngay
                <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
              </Link>
            </div>
          </section>

          <section className="w-full mb-12">
            <div className="text-center mb-5">
              <h2 className="font-['Plus_Jakarta_Sans'] text-xl sm:text-2xl font-bold text-[#121E1A]">
                Tại sao người dùng tin chọn Homigo?
              </h2>
              <p className="text-xs sm:text-sm text-[#6F7974] mt-1">Tìm nhà dễ dàng, an tâm ở lâu dài.</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                ["verified", "100% tin thật", "Tin đăng được kiểm duyệt và cập nhật thường xuyên."],
                ["search", "Tìm kiếm thông minh", "Bộ lọc rõ ràng, tìm nhanh đúng nhu cầu."],
                ["shield", "An toàn & minh bạch", "Thông tin giá và vị trí được trình bày rõ ràng."],
                ["support_agent", "Đồng hành tận tâm", "Luôn sẵn sàng hỗ trợ bạn trong quá trình tìm nhà."],
              ].map(([icon, title, description]) => (
                <div key={title} className="rounded-2xl border border-[#E0EEE7] bg-white p-4 shadow-xs">
                  <span className="material-symbols-outlined text-[24px] text-[#0F5F4A]">{icon}</span>
                  <h3 className="mt-3 text-sm font-bold text-[#121E1A]">{title}</h3>
                  <p className="mt-1 text-xs leading-5 text-[#6F7974]">{description}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      </main>

      <FilterModal
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        provinces={apiCities}
        roomTypes={apiRoomTypes}
        sortOptions={sortOptions}
        initialValues={filters}
        onApply={(values) => {
          setFilters(values);
          const qs = buildSearchParams(searchQuery, values).toString();
          router.push(`/tim-kiem${qs ? `?${qs}` : ""}`);
        }}
      />
    </SiteLayout>
  );
}
