import { useEffect, useState } from "react";
import type { Listing } from "@/types";
import { listingsApi, locationsApi, roomTypesApi } from "@/lib/api/client";
import { toHomeListing } from "@/lib/utils/listing";
import type { CityDto, RoomTypeDto } from "@shared/dto";

const HOME_LISTING_LIMIT = 8;

export function useHomeListings() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [cities, setCities] = useState<CityDto[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomTypeDto[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      listingsApi.list({ limit: HOME_LISTING_LIMIT }),
      locationsApi.cities(),
      roomTypesApi.list(),
    ])
      .then(([apiListings, apiCities, apiRoomTypes]) => {
        setListings(apiListings.map(toHomeListing));
        setCities(apiCities);
        setRoomTypes(apiRoomTypes);
      })
      .catch(() => {
        setListings([]);
        setCities([]);
        setRoomTypes([]);
      })
      .finally(() => setIsLoading(false));
  }, []);

  return { listings, cities, roomTypes, isLoading };
}