import { useCallback, useEffect, useState } from "react";
import type { ListingCardData } from "@/types";
import { listingsApi } from "@/lib/api/client";
import { toListingCard } from "@/lib/utils/listing";

const HOME_LISTING_LIMIT = 8;

export function useHomeListings() {
  const [listings, setListings] = useState<ListingCardData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [apiError, setApiError] = useState<string | null>(null);

  const fetchListings = useCallback(() => {
    setIsLoading(true);
    setApiError(null);
    listingsApi
      .list({ limit: HOME_LISTING_LIMIT })
      .then((apiListings) => {
        setListings(apiListings.map(toListingCard));
        setApiError(null);
      })
      .catch((error: unknown) => {
        setListings([]);
        setApiError(
          error instanceof Error
            ? error.message
            : "Không thể kết nối đến máy chủ Backend.",
        );
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchListings();
  }, [fetchListings]);

  return { listings, isLoading, apiError, reload: fetchListings };
}