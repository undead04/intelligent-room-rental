import { useEffect, useState } from "react";
import type { ListingDetailDto } from "@/types/dto";
import { listingsApi } from "@/lib/api/client";

const MISSING_LISTING_ID_ERROR = "Không tìm thấy mã tin đăng.";

export function useListingDetail(listingId: string | undefined) {
  const [listing, setListing] = useState<ListingDetailDto | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!listingId) return;
    let cancelled = false;

    listingsApi
      .getById(listingId)
      .then((detail) => {
        if (cancelled) return;
        setListing(detail);
        setApiError(null);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setListing(null);
        setApiError(error instanceof Error ? error.message : "Không thể tải tin đăng.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [listingId]);

  if (!listingId) {
    return { listing: null, apiError: MISSING_LISTING_ID_ERROR, isLoading: false };
  }

  return { listing, apiError, isLoading };
}