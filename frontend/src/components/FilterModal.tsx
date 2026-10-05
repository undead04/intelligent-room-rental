"use client";

import { useEffect, useState } from "react";
import FilterSelect from "@/components/FilterSelect";
import PriceRangeFilter from "@/components/PriceRangeFilter";
import { CityDto, RoomTypeDto } from "@shared/dto/listing";
import { SortOptions, FilterValues } from "@/types";
import { useCascadingLocations } from "@/hooks/useCascadingLocations";
import { DEFAULT_FILTERS } from "@/lib/utils/filter";

interface FilterModalProps {
  isOpen: boolean;
  provinces: CityDto[];
  roomTypes: RoomTypeDto[];
  sortOptions: SortOptions[];
  initialValues: FilterValues;
  onClose: () => void;
  onApply: (values: FilterValues) => void;
}

export default function FilterModal({
  isOpen,
  provinces,
  roomTypes,
  sortOptions,
  initialValues,
  onClose,
  onApply,
}: FilterModalProps) {
  const [draft, setDraft] = useState<FilterValues>(initialValues);

  const { districts, wards } = useCascadingLocations(draft.province, draft.district);

  // Mỗi lần mở modal, đồng bộ lại với bộ lọc đã áp dụng
  useEffect(() => {
    if (isOpen) setDraft(initialValues);
  }, [isOpen, initialValues]);

  const handleReset = () => setDraft(DEFAULT_FILTERS);

  const handleApply = () => {
    onApply(draft);
    onClose();
  };

  if (!isOpen) return null;

  const selectedProvince = provinces.find((p) => p.id === draft.province);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0F201C]/60 backdrop-blur-sm p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="w-full max-w-[720px] bg-white rounded-[28px] shadow-[0_24px_60px_-12px_rgba(15,95,74,0.2)] border border-[#E8E4DC] overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="h-[72px] px-7 border-b border-[#F0ECE4] flex items-center justify-between shrink-0 bg-white relative">
          <button
            onClick={onClose}
            aria-label="Đóng bộ lọc"
            className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-[#FAF8F4] text-[#14201C] transition-colors focus:outline-none"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
          <h2 className="font-['Plus_Jakarta_Sans'] font-extrabold text-xl text-[#14201C] absolute left-1/2 -translate-x-1/2 tracking-tight">
            Bộ lọc tìm kiếm
          </h2>
          <button onClick={handleReset} className="text-xs text-[#0F5F4A] hover:underline font-semibold">
            Đặt lại
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-7 py-6 space-y-6">
          <div className="space-y-3.5">
            <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-base text-[#14201C] flex items-center justify-between">
              <span>Khu vực</span>
              <span className="text-xs text-[#0F5F4A] font-semibold">{selectedProvince?.name}</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
              <FilterSelect
                label="Tỉnh / Thành"
                value={draft.province}
                onChange={(v) => setDraft((d) => ({ ...d, province: v, district: null, ward: null }))}
                options={provinces.map((p) => ({ value: p.id, label: p.name }))}
              />
              <FilterSelect
                label="Quận / Huyện"
                value={draft.district}
                onChange={(v) => setDraft((d) => ({ ...d, district: v, ward: null }))}
                options={districts.map((d) => ({ value: d.id, label: d.name }))}
              />
              <FilterSelect
                label="Phường / Xã"
                value={draft.ward}
                onChange={(v) => setDraft((d) => ({ ...d, ward: v }))}
                options={wards.map((w) => ({ value: w.id, label: w.name }))}
              />
            </div>
          </div>

          <div className="border-t border-[#F0ECE4]" />

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
            <FilterSelect
              label="Loại phòng"
              value={draft.roomType}
              onChange={(v) => setDraft((d) => ({ ...d, roomType: v }))}
              options={roomTypes.map((r) => ({ value: r.id, label: r.name }))}
            />
            <FilterSelect
              label="Sắp xếp"
              value={draft.sort}
              onChange={(v) => setDraft((d) => ({ ...d, sort: v ?? DEFAULT_FILTERS.sort }))}
              options={sortOptions.map((o) => ({ value: o.value, label: o.label }))}
            />
          </div>

          <div className="border-t border-[#F0ECE4]" />

          <PriceRangeFilter
            minPrice={draft.minPrice}
            maxPrice={draft.maxPrice}
            onMinChange={(v: number) => setDraft((d) => ({ ...d, minPrice: v }))}
            onMaxChange={(v: number) => setDraft((d) => ({ ...d, maxPrice: v }))}
          />
        </div>

        {/* Footer */}
        <div className="h-20 px-7 border-t border-[#F0ECE4] bg-white flex items-center justify-between shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-3 rounded-full border border-[#E8E4DC] text-sm font-semibold text-[#14201C] hover:bg-[#FAF8F4]"
          >
            Hủy bỏ
          </button>
          <button
            type="button"
            onClick={handleApply}
            className="px-8 py-3 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-sm font-bold shadow-md transition-all"
          >
            Áp dụng bộ lọc
          </button>
        </div>
      </div>
    </div>
  );
}