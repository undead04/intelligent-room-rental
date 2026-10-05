import { useEffect, useState } from "react";
import type { CityDto, RoomTypeDto } from "@shared/dto";
import { locationsApi, roomTypesApi } from "@/lib/api/client";

export function useFilterOptions() {
  const [cities, setCities] = useState<CityDto[]>([]);
  const [roomTypes, setRoomTypes] = useState<RoomTypeDto[]>([]);

  useEffect(() => {
    locationsApi.cities().then(setCities).catch(() => setCities([]));
    roomTypesApi.list().then(setRoomTypes).catch(() => setRoomTypes([]));
  }, []);

  return { cities, roomTypes };
}