import type { ListingDto } from "@shared/dto";
import type { Listing, SearchResult } from "@/types";
import { DEFAULT_PROPERTY_IMAGE } from "@/lib/constants/property";

export function formatPrice(priceVnd: number | null | undefined, emptyLabel = "Liên hệ") {
  return priceVnd ? `${(priceVnd / 1_000_000).toFixed(1)} triệu` : emptyLabel;
}

export function formatRelativeDate(value: string | null | undefined) {
  if (!value) return "Đang cập nhật";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Đang cập nhật";

  const diffInDays = Math.max(
    0,
    Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24)),
  );

  if (diffInDays === 0) return "Hôm nay";
  if (diffInDays === 1) return "Hôm qua";
  if (diffInDays < 7) return `${diffInDays} ngày trước`;
  if (diffInDays < 30) return `${Math.floor(diffInDays / 7)} tuần trước`;
  if (diffInDays < 365) return `${Math.floor(diffInDays / 30)} tháng trước`;
  return `${Math.floor(diffInDays / 365)} năm trước`;
}

export function formatPostedDate(value: string | null | undefined) {
  if (!value) return "Mới cập nhật";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Mới cập nhật";

  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function toHomeListing(listing: ListingDto): Listing {
  return {
    id: listing.id,
    title: listing.title,
    location: listing.address_raw || listing.district?.name || "Đang cập nhật địa chỉ",
    price: listing.price_string || formatPrice(listing.price_vnd),
    tag: "Mới",
    source: listing.source || "Homigo",
    image: listing.main_image || DEFAULT_PROPERTY_IMAGE,
    time: formatRelativeDate(listing.posted_date),
  };
}

export function toSearchResult(listing: ListingDto): SearchResult {
  return {
    id: listing.id,
    title: listing.title,
    type: listing.room_type?.name || "Phòng trọ",
    location: listing.address_raw || listing.district?.name || "Đang cập nhật địa chỉ",
    price: listing.price_string || formatPrice(listing.price_vnd),
    area: listing.area_m2 ? `${listing.area_m2}m²` : "Đang cập nhật",
    verified: false,
    source: listing.source || "Homigo",
    time: formatPostedDate(listing.posted_date),
    image: listing.main_image || DEFAULT_PROPERTY_IMAGE,
    tags: [],
  };
}

export function resolveListingImages(images: string[] | null | undefined): string[] {
  const validImages = images?.filter(Boolean) ?? [];
  return validImages.length > 0 ? validImages : [DEFAULT_PROPERTY_IMAGE];
}
