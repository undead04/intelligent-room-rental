import type { AmenityDisplay } from "@/lib/utils/amenities";

interface AmenitiesGridProps {
  amenities: AmenityDisplay[];
}

export default function AmenitiesGrid({ amenities }: AmenitiesGridProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
      <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A] mb-4">
        Tiện ích & Trang thiết bị
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {amenities.map((amenity) => (
          <div
            key={amenity.label}
            className="flex items-center gap-2.5 p-3 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]"
          >
            <span className="material-symbols-outlined text-[#0F5F4A] text-[20px]">
              {amenity.icon}
            </span>
            <span className="text-xs font-semibold text-gray-800">{amenity.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}