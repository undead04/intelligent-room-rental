"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import PropertyGallery from "@/components/PropertyGallery";
import LocationMap from "@/components/LocationMap";
import { listingsApi } from "@/lib/api/client";
import type { ListingDetailDto,AmenityKey } from "@shared/dto";
import { DetailPageSkeleton } from "@/components/LoadingSkeleton";
import DetailBreadcrumb from "./_components/DetailBreadcrumb";
import LandlordCard from "./_components/LandlordCard";
import SimilarListings from "./_components/SimilarListings";
import { formatPrice } from "@/lib/utils/listing";


const amenities_map: Record<
  AmenityKey,
  {
    icon: string;
    label: string;
  }
> = {
  private_wc: {
    icon: "wc",
    label: "WC riêng / khép kín",
  },
  aircon: {
    icon: "ac_unit",
    label: "Máy lạnh / điều hòa",
  },
  furniture: {
    icon: "chair",
    label: "Có nội thất",
  },
  window_balcony: {
    icon: "balcony",
    label: "Cửa sổ / ban công thoáng",
  },
  kitchen: {
    icon: "countertops",
    label: "Kệ bếp & chỗ nấu ăn",
  },
  mezzanine: {
    icon: "stairs",
    label: "Gác lửng / gác xép",
  },
  washing_machine: {
    icon: "local_laundry_service",
    label: "Máy giặt",
  },
  water_heater: {
    icon: "water_heater",
    label: "Máy nước nóng",
  },
  wifi: {
    icon: "wifi",
    label: "Wifi / Internet",
  },
  parking: {
    icon: "two_wheeler",
    label: "Chỗ để xe",
  },
};

export default function PropertyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [apiListing, setApiListing] = useState<ListingDetailDto | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedImgIdx, setSelectedImgIdx] = useState(0);
  const [showPhone, setShowPhone] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  const defaultImage = "/property-placeholder.svg";
  const images = apiListing?.images?.filter(Boolean).length
    ? apiListing.images.filter(Boolean)
    : [defaultImage];
  const title = apiListing?.title || "DUPLEX MỚI DƯƠNG QUẢNG HÀM ĐI ĐÂU CŨNG TIỆN";
  const location = apiListing?.address_raw || "Đường Dương Quảng Hàm, Phường 5, Quận Gò Vấp, TP. Hồ Chí Minh";
  const price = apiListing?.price_string || formatPrice(apiListing?.price_vnd);
  const area = apiListing?.area_m2 ? `${apiListing.area_m2} m²` : "20 m²";

  useEffect(() => {
    if (!params.id) {
      setApiError("Không tìm thấy mã tin đăng.");
      setIsLoading(false);
      return;
    }
    listingsApi.getById(params.id)
      .then(setApiListing)
      .catch((error: unknown) => setApiError(error instanceof Error ? error.message : "Không thể tải tin đăng."))
      .finally(() => setIsLoading(false));
  }, [params.id]);



  if (isLoading) {
    return <SiteLayout className="bg-[#FAF8F4]"><DetailPageSkeleton /></SiteLayout>;
  }

  return (
    <SiteLayout className="bg-[#FAF8F4]">

      <DetailBreadcrumb listing={apiListing} title={title} />

      {/* Main Content Layout */}
      <main className="max-w-[1380px] mx-auto px-4 lg:px-8 py-6 w-full flex-1">
        {apiError && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Không thể tải dữ liệu mới nhất của tin đăng. Đang hiển thị thông tin mẫu.
          </div>
        )}
        <button
          type="button"
          onClick={() => {
            if (window.history.length > 1) router.back();
            else router.push("/tim-kiem");
          }}
          className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-[#DCECE4] bg-white px-4 py-2 text-xs font-semibold text-[#0F5F4A] shadow-xs transition-colors hover:bg-[#E6F4EE]"
        >
          <span className="material-symbols-outlined text-[17px]">arrow_back</span>
          Quay lại danh sách
        </button>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <PropertyGallery images={images} selectedIndex={selectedImgIdx} onSelect={setSelectedImgIdx} />

            {/* Title & Price Header */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className="px-3 py-1 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
                  Homigo Verified
                </span>
                <span className="px-3 py-1 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs text-gray-600">
                  Mã tin: HM-88294
                </span>
                <button
                  onClick={() => setIsSaved(!isSaved)}
                  className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-[#DCECE4] bg-[#F5FBF7] px-3 py-1.5 text-xs font-semibold text-[#0F5F4A]"
                >
                  <span className="material-symbols-outlined text-[16px]">{isSaved ? "bookmark_added" : "bookmark"}</span>
                  {isSaved ? "Đã lưu" : "Lưu tin"}
                </button>
              </div>

              <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl text-[#121E1A] mb-3">
                {title}
              </h1>

              <p className="text-xs sm:text-sm text-gray-600 flex items-center gap-1.5 mb-4">
                <span className="material-symbols-outlined text-[#0F5F4A] text-[18px]">location_on</span>
                <span>{location}</span>
              </p>

              <div className="p-4 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC] flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-baseline gap-2">
                  <span className="font-['Plus_Jakarta_Sans'] font-black text-3xl text-[#FF6B4A]">
                    {price}
                  </span>
                </div>
               
              </div>
            </div>

            <LocationMap
              address={location}
              latitude={apiListing?.lat}
              longitude={apiListing?.lng}
            />

            {/* Key details */}
            <section className="rounded-2xl border border-[#E8E4DC] bg-white p-6 shadow-xs">
              <h2 className="mb-4 font-['Plus_Jakarta_Sans'] text-lg font-bold text-[#121E1A]">Thông tin phòng</h2>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["square_foot", "Diện tích", area],
                  ["bed", "Loại phòng", apiListing?.room_type?.name || "Phòng trọ"],
                  ["chair", "Nội thất", formatFurnishing(apiListing?.furnishing_code)],
                  ["payments", "Đặt cọc", formatPrice(apiListing?.deposit)],
                ].map(([icon, label, value]) => (
                  <div key={label} className="rounded-xl bg-[#F5FBF7] p-3.5">
                    <span className="material-symbols-outlined text-[20px] text-[#0F5F4A]">{icon}</span>
                    <p className="mt-2 text-[11px] text-gray-500">{label}</p>
                    <p className="mt-0.5 text-sm font-bold text-[#121E1A]">{value}</p>
                  </div>
                ))}
              </div>
            </section>

            {/* Amenities Grid */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A] mb-4">
                Tiện ích & Trang thiết bị
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {formatAmenities(apiListing?.concept_scores).map((a) => (
                  <div
                    key={a.label}
                    className="flex items-center gap-2.5 p-3 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]"
                  >
                    <span className="material-symbols-outlined text-[#0F5F4A] text-[20px]">
                      {a.icon}
                    </span>
                    <span className="text-xs font-semibold text-gray-800">{a.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Description */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs space-y-3">
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A]">
                Mô tả chi tiết
              </h2>
              <div className="text-sm text-gray-700 space-y-2 leading-relaxed">
                <p>
                  {apiListing?.description || "Thông tin mô tả đang được cập nhật."}
                </p>
              </div>
            </div>
          </div>

          <LandlordCard
            listing={apiListing}
            defaultImage={defaultImage}
            showPhone={showPhone}
            onTogglePhone={() => setShowPhone(!showPhone)}
          />
        </div>

        <SimilarListings images={images} defaultImage={defaultImage} />
      </main>

    </SiteLayout>
  );
}

function formatAmenities(concept_scores: Record<AmenityKey, number> | null | undefined) {
  if (!concept_scores) return [{ icon: "block", label: "Không có tiện nghi" }];
  const activeAmenities: { icon: string; label: string }[] = [];

  for (const [key, value] of Object.entries(concept_scores)) {
    if (value > 0.5 && key in amenities_map) {
      activeAmenities.push(amenities_map[key as AmenityKey]);
    }
  }

  if (activeAmenities.length === 0) return [{ icon: "block", label: "Không có tiện nghi" }];
  return activeAmenities;
}

function formatFurnishing(furnishing_code: number | null | undefined) {
  switch (furnishing_code) {
    case 1:
      return "Không có nội thất";
    case 2:
      return "Nội thất đầy đủ";
    case 3:
      return "Nội thất cao cấp";
    default:
      return "Không xác định";
  }
}