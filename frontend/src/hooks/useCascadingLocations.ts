import { useEffect, useState } from "react";
import type { DistrictDto, WardDto } from "@shared/dto";
import { locationsApi } from "@/lib/api/client";

export function useCascadingLocations(province: number | null, district: number | null) {
  const [districts, setDistricts] = useState<DistrictDto[]>([]);
  const [wards, setWards] = useState<WardDto[]>([]);

  // Load quận theo tỉnh đang chọn trong modal
  useEffect(() => {
    if (!province) {
      setDistricts([]);
      return;
    }
    let cancelled = false;
    locationsApi
      .districts({ city_id: province })
      .then((data) => !cancelled && setDistricts(data))
      .catch(() => !cancelled && setDistricts([]));
    return () => {
      cancelled = true;
    };
  }, [province]);

  // Load phường theo quận đang chọn
  useEffect(() => {
    if (!district) {
      setWards([]);
      return;
    }
    let cancelled = false;
    locationsApi
      .wards({ district_id: district })
      .then((data) => !cancelled && setWards(data))
      .catch(() => !cancelled && setWards([]));
    return () => {
      cancelled = true;
    };
  }, [district]);

  return { districts, wards };
}