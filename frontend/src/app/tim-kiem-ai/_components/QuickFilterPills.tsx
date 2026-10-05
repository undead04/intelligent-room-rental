interface QuickFilterPillsProps {
  activeFilter: string;
  onSelect: (filterId: string) => void;
}

const QUICK_FILTERS: { id: string; label: string; withArrow: boolean; isStrong: boolean }[] = [
  { id: "price", label: "Giá", withArrow: true, isStrong: true },
  { id: "distance", label: "Khoảng cách", withArrow: true, isStrong: false },
  { id: "ac", label: "Máy lạnh", withArrow: false, isStrong: false },
  { id: "mezzanine", label: "Gác", withArrow: false, isStrong: false },
];

export default function QuickFilterPills({ activeFilter, onSelect }: QuickFilterPillsProps) {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-1 text-[11px]">
      {QUICK_FILTERS.map((filter) => {
        const isActive = activeFilter === filter.id;

        return (
          <button
            key={filter.id}
            onClick={() => onSelect(filter.id)}
            className={`px-3 py-1 rounded-full border whitespace-nowrap transition-all ${
              filter.withArrow ? "flex items-center gap-1 " : ""
            }${filter.isStrong ? "font-semibold" : "font-medium"} ${
              isActive
                ? "bg-[#E6F4EE] text-[#0F5F4A] border-[#0F5F4A]/20"
                : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0]"
            }`}
          >
            <span>{filter.label}</span>
            {filter.withArrow && (
              <span className="material-symbols-outlined text-[14px]">arrow_drop_down</span>
            )}
          </button>
        );
      })}
    </div>
  );
}