import { useEffect, useState } from "react";
import type { ListingCardData } from "@/types";
import { listingsApi } from "@/lib/api/client";
import { toListingCard } from "@/lib/utils/listing";

const HOME_LISTING_LIMIT = 8;

export function useHomeListings() {
  const [listings, setListings] = useState<ListingCardData[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    listingsApi
      .list({ limit: HOME_LISTING_LIMIT })
      .then((apiListings) => setListings(apiListings.map(toListingCard)))
      .catch(() => setListings([]))
      .finally(() => setIsLoading(false));
  }, []);

  return { listings, isLoading };
}