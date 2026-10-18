"use client";

interface QuickFilterPillsProps {
  activeFilter: string;
  onSelect: (filterId: string) => void;
  searchTags?: string[];
}

const FILTER_OPTIONS = [
  { id: "default", label: "Xếp hạng AI", icon: "sort" },
  { id: "price_asc", label: "Giá thấp nhất", icon: "arrow_downward" },
  { id: "score_desc", label: "Phù hợp nhất", icon: "stars" },
  { id: "has_ac", label: "Có máy lạnh", icon: "ac_unit" },
  { id: "has_mezzanine", label: "Có gác", icon: "stairs" },
];

export default function QuickFilterPills({
  activeFilter,
  onSelect,
  searchTags = [],
}: QuickFilterPillsProps) {
  return (
    <div className="space-y-1.5 pt-0.5">
      {/* Active AI Search Criteria Tags */}
      {searchTags.length > 0 && (
        <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar text-[10px]">
          <span className="text-[#6F7974] font-semibold shrink-0 flex items-center gap-0.5">
            <span className="material-symbols-outlined text-[13px] text-[#0F5F4A]">tune</span>
            <span>Tiêu chí:</span>
          </span>
          {searchTags.map((tag, idx) => (
            <span
              key={idx}
              className="bg-[#FAFBF9] border border-[#E8E4DC] text-[#0F5F4A] px-2 py-0.5 rounded-md font-medium whitespace-nowrap shadow-2xs"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Interactive Filter/Sort Pills */}
      <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-0.5 text-[11px]">
        {FILTER_OPTIONS.map((filter) => {
          const isActive = activeFilter === filter.id;

          return (
            <button
              key={filter.id}
              onClick={() => onSelect(isActive && filter.id !== "default" ? "default" : filter.id)}
              className={`px-2.5 py-1 rounded-full border whitespace-nowrap transition-all flex items-center gap-1 cursor-pointer ${
                isActive
                  ? "bg-[#0F5F4A] text-white border-[#0F5F4A] font-bold shadow-xs"
                  : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0] font-medium"
              }`}
            >
              <span className="material-symbols-outlined text-[13px]">{filter.icon}</span>
              <span>{filter.label}</span>
              {isActive && filter.id !== "default" && (
                <span className="material-symbols-outlined text-[13px] opacity-80">check</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}