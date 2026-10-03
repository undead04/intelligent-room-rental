interface AmenityChipsProps {
  options: string[];
  selected: string[];
  onToggle: (name: string) => void;
}

export default function AmenityChips({ options, selected, onToggle }: AmenityChipsProps) {
  return (
    <div className="space-y-2.5 pb-1">
      <label className="block uppercase text-[11px] font-bold text-[#6B7A74] tracking-wider">
        Tiện ích phổ biến
      </label>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              onClick={() => onToggle(option)}
              aria-pressed={active}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                active
                  ? "bg-[#E6F4EE] text-[#0F5F4A] border border-[#0F5F4A]"
                  : "bg-[#FAF8F4] text-[#14201C] border border-[#E8E4DC] hover:border-[#0F5F4A]"
              }`}
            >
              {active && <span className="material-symbols-outlined text-[14px]">check</span>}
              <span>{option}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
