import type { CityDto, RoomTypeDto } from "@/types/dto";
import FilterSelect from "@/components/FilterSelect";

interface PriceStatsFilterBarProps {
  cities: CityDto[];
  cityId: number | undefined;
  onCityChange: (cityId: number) => void;
  roomTypes?: RoomTypeDto[];
  roomTypeId?: number | undefined;
  onRoomTypeChange?: (roomTypeId: number | undefined) => void;
}

export default function PriceStatsFilterBar({
  cities,
  cityId,
  onCityChange,
  roomTypes = [],
  roomTypeId,
  onRoomTypeChange,
}: PriceStatsFilterBarProps) {
  return (
    <div className="bg-white rounded-2xl p-4 border border-[#E8E4DC] shadow-xs mb-6 flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <FilterSelect
          variant="pill"
          value={cityId ?? null}
          onChange={(next) => next !== null && onCityChange(next)}
          options={cities.map((city) => ({ value: city.id, label: city.name }))}
          emptyLabel={cities.length > 0 ? null : "Đang tải..."}
        />

        {roomTypes.length > 0 && onRoomTypeChange && (
          <FilterSelect
            variant="pill"
            value={roomTypeId ?? null}
            onChange={(next) => onRoomTypeChange(next ?? undefined)}
            options={roomTypes.map((rt) => ({
              value: rt.id,
              label: rt.name || rt.code || `Loại ${rt.id}`,
            }))}
            emptyLabel="Tất cả loại phòng"
          />
        )}
      </div>

      <div className="text-xs text-gray-500 font-medium">
        Thời gian: <strong>30 ngày gần nhất</strong>
      </div>
    </div>
  );
}
