"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import SiteLayout from "@/components/SiteLayout";
import PropertyGallery from "@/components/PropertyGallery";
import LocationMap from "@/components/LocationMap";
import DetailBreadcrumb from "./_components/DetailBreadcrumb";
import LandlordCard from "./_components/LandlordCard";
import AmenitiesGrid from "./_components/AmenitiesGrid";
import ListingDescription from "./_components/ListingDescription";
import ListingKeyDetails from "./_components/ListingKeyDetails";
import ListingPriceHeader from "./_components/ListingPriceHeader";
import { useListingDetail } from "./_hooks/useListingDetail";
import {
  FALLBACK_LISTING_AREA,
  FALLBACK_LISTING_LOCATION,
  FALLBACK_LISTING_TITLE,
} from "./_constants/fallbackListing";
import DetailPageSkeleton from "@/components/skeleton/DetailPageSkeleton";
import { DEFAULT_PROPERTY_IMAGE } from "@/lib/constants/property";
import { formatPrice, resolveListingImages } from "@/lib/utils/listing";
import { toAmenities, toFurnishingLabel } from "@/lib/utils/amenities";

export default function PropertyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [showPhone, setShowPhone] = useState(false);
  const [isSaved, setIsSaved] = useState(false);
  const [selectedImgIdx, setSelectedImgIdx] = useState(0);

  const { listing, apiError, isLoading } = useListingDetail(params.id);

  const images = resolveListingImages(listing?.images);
  const title = listing?.title || FALLBACK_LISTING_TITLE;
  const location = listing?.address_raw || FALLBACK_LISTING_LOCATION;
  const price = listing?.price_string || formatPrice(listing?.price_vnd);
  const area = listing?.area_m2 ? `${listing.area_m2} m²` : FALLBACK_LISTING_AREA;

  if (isLoading) {
    return <SiteLayout className="bg-[#FAF8F4]"><DetailPageSkeleton /></SiteLayout>;
  }

  return (
    <SiteLayout className="bg-[#FAF8F4]">

      <DetailBreadcrumb listing={listing} title={title} />

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
            <PropertyGallery
              images={images}
              selectedIndex={selectedImgIdx}
              onSelect={setSelectedImgIdx}
            />

            <ListingPriceHeader
              title={title}
              location={location}
              price={price}
              isSaved={isSaved}
              onToggleSave={() => setIsSaved(!isSaved)}
            />

            <LocationMap address={location} latitude={listing?.lat} longitude={listing?.lng} />

            <ListingKeyDetails
              area={area}
              roomType={listing?.room_type?.name || "Phòng trọ"}
              furnishing={toFurnishingLabel(listing?.furnishing_code)}
              deposit={formatPrice(listing?.deposit)}
            />

            <AmenitiesGrid amenities={toAmenities(listing?.concept_scores)} />

            <ListingDescription description={listing?.description} />
          </div>

          <LandlordCard
            listing={listing}
            defaultImage={DEFAULT_PROPERTY_IMAGE}
            showPhone={showPhone}
            onTogglePhone={() => setShowPhone(!showPhone)}
          />
        </div>
      </main>

    </SiteLayout>
  );
}