import { useEffect, useState } from "react";
import type { ListingDetailDto } from "@shared/dto";
import { listingsApi } from "@/lib/api/client";

export function useListingDetail(listingId: string | undefined) {
  const [listing, setListing] = useState<ListingDetailDto | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!listingId) {
      setApiError("Không tìm thấy mã tin đăng.");
      setIsLoading(false);
      return;
    }

    listingsApi
      .getById(listingId)
      .then(setListing)
      .catch((error: unknown) =>
        setApiError(error instanceof Error ? error.message : "Không thể tải tin đăng."),
      )
      .finally(() => setIsLoading(false));
  }, [listingId]);

  return { listing, apiError, isLoading };
}