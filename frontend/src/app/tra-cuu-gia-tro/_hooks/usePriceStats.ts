import { useEffect, useMemo, useState } from "react";
import type { CityDto, PriceStatsDto } from "@shared/dto";
import { locationsApi, priceStatsApi } from "@/lib/api/client";
import { toPriceStatRows } from "@/lib/utils/priceStats";

const DEFAULT_CITY_NAME = "Hồ Chí Minh";

interface StatsSnapshot {
  queryKey: string;
  stats: PriceStatsDto | null;
  apiError: string | null;
}

export function usePriceStats() {
  const [cities, setCities] = useState<CityDto[]>([]);
  const [cityId, setCityId] = useState<number | undefined>();
  const [loadError, setLoadError] = useState<string | null>(null);

  // Quận đang chọn gắn với thành phố: đổi thành phố là tự bỏ chọn, không cần effect
  const [districtSelection, setDistrictSelection] = useState<{
    cityId: number | undefined;
    districtId: number | undefined;
  }>({ cityId: undefined, districtId: undefined });
  const districtId =
    districtSelection.cityId === cityId ? districtSelection.districtId : undefined;

  const [statsSnapshot, setStatsSnapshot] = useState<StatsSnapshot | null>(null);

  useEffect(() => {
    locationsApi
      .cities()
      .then((result) => {
        setCities(result);
        const city = result.find((item) => item.name.includes(DEFAULT_CITY_NAME)) || result[0];
        if (city) setCityId(city.id);
      })
      .catch(() => setLoadError("Không thể tải danh sách thành phố."));
  }, []);

  const statsQueryKey = `${cityId ?? ""}|${districtId ?? ""}`;

  useEffect(() => {
    if (cityId === undefined) return;
    let cancelled = false;

    priceStatsApi
      .get({ city_id: cityId, district_id: districtId })
      .then((stats) => !cancelled && setStatsSnapshot({ queryKey: statsQueryKey, stats, apiError: null }))
      .catch(() =>
        !cancelled &&
        setStatsSnapshot({
          queryKey: statsQueryKey,
          stats: null,
          apiError: "Không thể tải thống kê giá từ máy chủ.",
        }),
      );

    return () => {
      cancelled = true;
    };
  }, [cityId, districtId, statsQueryKey]);

  const selectCity = (nextCityId: number) => {
    setCityId(nextCityId);
  };

  const selectDistrict = (nextDistrictId: number | undefined) => {
    setDistrictSelection({ cityId, districtId: nextDistrictId });
  };

  // Chỉ dùng thống kê của request hiện tại: đổi bộ lọc là loading và không còn lỗi cũ
  const snapshot = Boolean(cityId) && statsSnapshot?.queryKey === statsQueryKey ? statsSnapshot : null;

  const stats = snapshot?.stats ?? null;
  const rows = useMemo(() => toPriceStatRows(stats), [stats]);

  return {
    stats,
    rows,
    cities,
    cityId,
    selectCity,
    districtId,
    selectDistrict,
    apiError: loadError ?? snapshot?.apiError ?? null,
    isLoading: snapshot === null,
  };
}