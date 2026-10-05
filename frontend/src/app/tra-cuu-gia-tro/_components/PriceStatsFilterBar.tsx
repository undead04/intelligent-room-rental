import type { CityDto } from "@shared/dto";

const ROOM_TYPE_OPTIONS = [
  "Tất cả loại phòng",
  "Phòng trọ / KTX",
  "Căn hộ dịch vụ",
  "Chung cư mini",
  "Nhà nguyên căn",
];

interface PriceStatsFilterBarProps {
  cities: CityDto[];
  selectedCity: string;
  selectedRoomType: string;
  onCityChange: (cityName: string) => void;
  onRoomTypeChange: (roomType: string) => void;
}

export default function PriceStatsFilterBar({
  cities,
  selectedCity,
  selectedRoomType,
  onCityChange,
  onRoomTypeChange,
}: PriceStatsFilterBarProps) {
  return (
    <div className="bg-white rounded-2xl p-4 border border-[#E8E4DC] shadow-xs mb-6 flex flex-wrap items-center justify-between gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <SelectPill value={selectedCity} onChange={onCityChange} isBold>
          {cities.length > 0
            ? cities.map((city) => <option key={city.id}>{city.name}</option>)
            : <option>Đang tải...</option>}
        </SelectPill>

        <SelectPill value={selectedRoomType} onChange={onRoomTypeChange}>
          {ROOM_TYPE_OPTIONS.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </SelectPill>
      </div>

      <div className="text-xs text-gray-500 font-medium">
        Thời gian: <strong>30 ngày gần nhất</strong>
      </div>
    </div>
  );
}

interface SelectPillProps {
  value: string;
  onChange: (value: string) => void;
  isBold?: boolean;
  children: React.ReactNode;
}

function SelectPill({ value, onChange, isBold = false, children }: SelectPillProps) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`custom-select px-4 py-2.5 pr-10 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs outline-none ${
          isBold ? "font-bold text-[#0F5F4A]" : "font-semibold text-gray-700"
        }`}
      >
        {children}
      </select>
      <span className="material-symbols-outlined pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[18px] text-[#0F5F4A]">
        expand_more
      </span>
    </div>
  );
}