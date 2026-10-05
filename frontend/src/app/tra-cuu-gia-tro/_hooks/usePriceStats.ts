import { useEffect, useMemo, useState } from "react";
import type { CityDto, DistrictDto, PriceStatsDto } from "@shared/dto";
import { locationsApi, priceStatsApi } from "@/lib/api/client";
import { toPriceStatRows } from "@/lib/utils/priceStats";

const DEFAULT_CITY_NAME = "Hồ Chí Minh";

export function usePriceStats() {
  const [selectedCity, setSelectedCity] = useState(DEFAULT_CITY_NAME);
  const [cities, setCities] = useState<CityDto[]>([]);
  const [cityId, setCityId] = useState<number | undefined>();
  const [districtId, setDistrictId] = useState<number | undefined>();
  const [districts, setDistricts] = useState<DistrictDto[]>([]);
  const [stats, setStats] = useState<PriceStatsDto | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    locationsApi
      .cities()
      .then((result) => {
        setCities(result);
        const city = result.find((item) => item.name.includes(DEFAULT_CITY_NAME)) || result[0];
        if (city) {
          setSelectedCity(city.name);
          setCityId(city.id);
        }
      })
      .catch(() => setApiError("Không thể tải danh sách thành phố."));
  }, []);

  useEffect(() => {
    if (cityId === undefined) return;
    setDistrictId(undefined);
    setDistricts([]);
    locationsApi
      .districts({ city_id: cityId })
      .then(setDistricts)
      .catch(() => setApiError("Không thể tải danh sách quận/huyện."));
  }, [cityId]);

  useEffect(() => {
    if (cityId === undefined) return;
    setIsLoading(true);
    priceStatsApi
      .get({ city_id: cityId, district_id: districtId })
      .then(setStats)
      .catch(() => {
        setApiError("Không thể tải thống kê giá từ máy chủ.");
        setStats(null);
      })
      .finally(() => setIsLoading(false));
  }, [cityId, districtId]);

  const selectCity = (cityName: string) => {
    const city = cities.find((item) => item.name === cityName);
    setSelectedCity(cityName);
    setCityId(city?.id);
  };

  const rows = useMemo(() => toPriceStatRows(stats), [stats]);

  return {
    stats,
    rows,
    cities,
    selectedCity,
    selectCity,
    districts,
    districtId,
    selectDistrict: setDistrictId,
    apiError,
    isLoading,
  };
}