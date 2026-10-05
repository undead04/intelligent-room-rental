import { useEffect, useState } from "react";
import type { DistrictDto, WardDto } from "@shared/dto";
import { locationsApi } from "@/lib/api/client";

const NO_DISTRICTS: DistrictDto[] = [];
const NO_WARDS: WardDto[] = [];

interface ListSnapshot<T> {
  parentId: number | null;
  items: T[];
}

// loadAllWhenEmpty = true: chưa chọn tỉnh thì lấy tất cả quận (dùng để hiện tên quận ở trang tìm kiếm)
// loadAllWhenEmpty = false: chưa chọn tỉnh thì không gọi API (dùng cho bộ lọc phân cấp trong modal)
function useDistrictList(cityId: number | null, loadAllWhenEmpty: boolean): DistrictDto[] {
  const [snapshot, setSnapshot] = useState<ListSnapshot<DistrictDto> | null>(null);

  useEffect(() => {
    if (!cityId && !loadAllWhenEmpty) return;
    let cancelled = false;

    locationsApi
      .districts(cityId ? { city_id: cityId } : undefined)
      .then((items) => !cancelled && setSnapshot({ parentId: cityId, items }))
      .catch(() => !cancelled && setSnapshot({ parentId: cityId, items: NO_DISTRICTS }));

    return () => {
      cancelled = true;
    };
  }, [cityId, loadAllWhenEmpty]);

  // Chỉ hiện danh sách của tỉnh đang chọn: đổi tỉnh là danh sách cũ không còn khớp
  return snapshot?.parentId === cityId ? snapshot.items : NO_DISTRICTS;
}

export function useCascadingLocations(province: number | null, district: number | null) {
  const districts = useDistrictList(province, false);
  const [wardSnapshot, setWardSnapshot] = useState<ListSnapshot<WardDto> | null>(null);

  useEffect(() => {
    if (!district) return;
    let cancelled = false;

    locationsApi
      .wards({ district_id: district })
      .then((items) => !cancelled && setWardSnapshot({ parentId: district, items }))
      .catch(() => !cancelled && setWardSnapshot({ parentId: district, items: NO_WARDS }));

    return () => {
      cancelled = true;
    };
  }, [district]);

  const wards = wardSnapshot?.parentId === district ? wardSnapshot.items : NO_WARDS;

  return { districts, wards };
}

export function useDistrictOptions(cityId: number | null): DistrictDto[] {
  return useDistrictList(cityId, true);
}