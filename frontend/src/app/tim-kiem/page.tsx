"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import SearchResultCard, { SearchResult } from "@/components/SearchResultCard";
import { listingsApi } from "@/lib/api/client";
import type { ListingDto } from "@shared/dto";

export default function SearchPage() {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedDistrict, setSelectedDistrict] = useState("Tất cả");
  const [apiError, setApiError] = useState<string | null>(null);

  const districts = [
    "Tất cả",
    "Quận 1",
    "Quận 3",
    "Quận 4",
    "Quận 7",
    "Quận 10",
    "Bình Thạnh",
    "TP. Thủ Đức",
    "Gò Vấp",
    "Tân Bình",
    "Phú Nhuận",
  ];

  const fallbackSearchResults: SearchResult[] = [
    {
      id: "phong-1",
      title: "Phòng Duplex gác lửng ban công full nội thất Thủ Đức",
      type: "Căn hộ dịch vụ",
      location: "Đặng Văn Bi, Trường Thọ, TP. Thủ Đức",
      price: "4.8 triệu",
      area: "28m²",
      verified: true,
      source: "Homigo Verified",
      time: "25 phút trước",
      image: "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?auto=format&fit=crop&w=600&q=80",
      tags: ["⚡ Mới", "Có gác", "Ban công", "Máy lạnh"]
    },
    {
      id: "phong-2",
      title: "Studio trung tâm Quận 1 full đồ - Giờ giấc tự do 24/7",
      type: "Studio",
      location: "Nguyễn Trãi, Phường Bến Thành, Quận 1",
      price: "7.5 triệu",
      area: "35m²",
      verified: true,
      source: "Homigo Verified",
      time: "40 phút trước",
      image: "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=600&q=80",
      tags: ["⚡ Mới", "Không chung chủ", "Thang máy"]
    },
    {
      id: "phong-3",
      title: "Phòng trọ sinh viên gần ĐH Hutech / Ngoại Thương",
      type: "Phòng trọ",
      location: "D2 (Nguyễn Gia Trí), Phường 25, Bình Thạnh",
      price: "3.5 triệu",
      area: "22m²",
      verified: false,
      source: "Chợ Tốt",
      time: "1 giờ trước",
      image: "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=600&q=80",
      tags: ["Gần ĐH", "Có gác lửng", "Cửa sổ"]
    },
    {
      id: "phong-4",
      title: "Căn hộ 1PN ban công view sông thoáng mát Quận 7",
      type: "Chung cư mini",
      location: "Nguyễn Thị Thập, Tân Phong, Quận 7",
      price: "6.2 triệu",
      area: "40m²",
      verified: true,
      source: "Homigo Verified",
      time: "1 giờ trước",
      image: "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=600&q=80",
      tags: ["Ban công", "Bếp riêng", "Bảo vệ 24/7"]
    },
    {
      id: "phong-5",
      title: "Phòng trọ cao cấp Gò Vấp - Gần ĐH Công Nghiệp IUH",
      type: "Phòng trọ",
      location: "Dương Quảng Hàm, Phường 5, Gò Vấp",
      price: "3.9 triệu",
      area: "25m²",
      verified: true,
      source: "Homigo Verified",
      time: "2 giờ trước",
      image: "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=600&q=80",
      tags: ["⚡ Mới", "Gần IUH", "Free Wifi"]
    },
    {
      id: "phong-6",
      title: "Nhà nguyên căn 2 tầng Tân Bình thích hợp nhóm sinh viên",
      type: "Nhà nguyên căn",
      location: "Cộng Hòa, Phường 13, Tân Bình",
      price: "11 triệu",
      area: "65m²",
      verified: false,
      source: "Chợ Tốt",
      time: "3 giờ trước",
      image: "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=600&q=80",
      tags: ["3 PN", "Chỗ để xe rộng", "Giờ tự do"]
    },
  ];
  const [searchResults, setSearchResults] = useState<SearchResult[]>(fallbackSearchResults);

  useEffect(() => {
    let cancelled = false;

    listingsApi
      .list({
        limit: 20,
        district: selectedDistrict === "Tất cả" ? undefined : selectedDistrict,
      })
      .then((listings) => {
        if (!cancelled && listings.length > 0) {
          setApiError(null);
          setSearchResults(listings.map(toSearchResult));
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setApiError(error instanceof Error ? error.message : "Không thể kết nối API.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedDistrict]);

  return (
    <SiteLayout className="bg-[#FAF8F4]" onOpenFilter={() => setIsFilterOpen(true)}>

      <main className="w-full flex-1 max-w-[1500px] mx-auto px-4 lg:px-8 py-6">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-2 text-xs text-gray-500 mb-3">
          <Link href="/" className="hover:text-[#0F5F4A]">Trang chủ</Link>
          <span>/</span>
          <span className="text-[#121E1A] font-semibold">TP. Hồ Chí Minh</span>
        </nav>

        {/* Page Title */}
        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] mb-4">
          Phòng trọ, nhà ở, căn hộ TP. Hồ Chí Minh
        </h1>

        {/* Horizontal District Filter Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-3 hide-scrollbar">
          {districts.map((d) => {
            const active = selectedDistrict === d;
            return (
              <button
                key={d}
                onClick={() => setSelectedDistrict(d)}
                className={`whitespace-nowrap px-4 py-2 rounded-full text-xs font-semibold transition-all shadow-2xs ${
                  active
                    ? "bg-[#0F5F4A] text-white"
                    : "bg-white text-[#3F4944] border border-[#E8E4DC] hover:border-[#0F5F4A]"
                }`}
              >
                {d}
              </button>
            );
          })}
        </div>

        {/* Sticky Search & Filter Bar */}
        <div className="sticky top-[72px] z-30 bg-[#FAF8F4]/95 backdrop-blur-md py-3 flex items-center gap-3">
          <Link
            href="/"
            className="w-11 h-11 shrink-0 rounded-full bg-white border border-[#E8E4DC] hover:bg-[#E9F7F0] flex items-center justify-center text-gray-700 shadow-xs transition-colors"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_back</span>
          </Link>

          <div className="flex-1 relative flex items-center bg-white border border-[#E8E4DC] rounded-full px-5 py-2.5 shadow-xs">
            <span className="material-symbols-outlined text-[#0F5F4A] mr-3 text-[20px]">search</span>
            <span className="text-sm font-semibold text-[#121E1A] flex-1 truncate">
              Hồ Chí Minh · {selectedDistrict} · Chính chủ
            </span>
          </div>

          <button
            onClick={() => setIsFilterOpen(true)}
            className="relative w-11 h-11 shrink-0 rounded-full bg-white border border-[#0F5F4A] hover:bg-[#E9F7F0] text-[#0F5F4A] flex items-center justify-center shadow-xs transition-all"
            title="Mở bộ lọc"
          >
            <span className="material-symbols-outlined text-[20px]">tune</span>
            <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold flex items-center justify-center">
              2
            </span>
          </button>
        </div>
        {/* Result Summary & Sorter */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-600">
            <span className="material-symbols-outlined text-[#0F5F4A] text-[18px]">bolt</span>
            <span className="text-[#0F5F4A] font-bold">206 tin mới hôm nay</span>
            <span>·</span>
            <span>
              Tìm thấy <strong className="text-[#121E1A] font-bold">4.752</strong> kết quả tại Hồ Chí Minh
            </span>
          </div>
          {apiError && (
            <p className="text-xs text-[#9A3412]">
              Đang hiển thị dữ liệu mẫu: {apiError}
            </p>
          )}
        </div>

        {/* Listings Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
          {searchResults.map((item) => <SearchResultCard key={item.id} item={item} />)}
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-center gap-2 mb-12">
          <button className="w-10 h-10 rounded-full border border-[#E8E4DC] bg-white flex items-center justify-center text-gray-600 hover:bg-[#E9F7F0]">
            <span className="material-symbols-outlined text-[18px]">chevron_left</span>
          </button>
          {[1, 2, 3, 4].map((p) => (
            <button
              key={p}
              className={`w-10 h-10 rounded-full text-xs font-bold transition-all ${
                p === 1
                  ? "bg-[#0F5F4A] text-white shadow-xs"
                  : "bg-white border border-[#E8E4DC] text-gray-700 hover:bg-[#E9F7F0]"
              }`}
            >
              {p}
            </button>
          ))}
          <span className="text-gray-400 px-1">...</span>
          <button className="w-10 h-10 rounded-full border border-[#E8E4DC] bg-white text-xs font-bold text-gray-700 hover:bg-[#E9F7F0]">
            158
          </button>
          <button className="w-10 h-10 rounded-full border border-[#E8E4DC] bg-white flex items-center justify-center text-gray-600 hover:bg-[#E9F7F0]">
            <span className="material-symbols-outlined text-[18px]">chevron_right</span>
          </button>
        </div>
      </main>

      <FilterModal isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} />
    </SiteLayout>
  );
}

function toSearchResult(listing: ListingDto): SearchResult {
  return {
    id: String(listing.list_id),
    title: listing.title,
    type: listing.room_type?.room_type || "Phòng trọ",
    location: listing.address_raw || listing.district?.name || "Đang cập nhật địa chỉ",
    price: listing.price_string || formatPrice(listing.price_vnd),
    area: listing.area_m2 ? `${listing.area_m2}m²` : "Đang cập nhật",
    verified: false,
    source: "Homigo",
    time: "Mới cập nhật",
    image: listing.main_image || "/stitch/5_property_detail_f282cfd03807476da64d2e1cd23ef2fc.png",
    tags: [],
  };
}

function formatPrice(priceVnd: number | null) {
  return priceVnd ? `${(priceVnd / 1_000_000).toFixed(1)} triệu` : "Liên hệ";
}
