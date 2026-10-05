import { useEffect, useState } from "react";
import type { DistrictDto } from "@shared/dto";
import { locationsApi } from "@/lib/api/client";

export function useDistrictOptions(cityId: number | null) {
  const [districts, setDistricts] = useState<DistrictDto[]>([]);

  useEffect(() => {
    locationsApi
      .districts(cityId ? { city_id: cityId } : undefined)
      .then(setDistricts)
      .catch(() => setDistricts([]));
  }, [cityId]);

  return districts;
}