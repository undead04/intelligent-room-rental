import Link from "next/link";
import FilterButton from "@/components/FilterButton";

interface SearchToolbarProps {
  query: string;
  placeholder: string;
  activeFilterCount: number;
  onQueryChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onOpenFilter: () => void;
}

export default function SearchToolbar({
  query,
  placeholder,
  activeFilterCount,
  onQueryChange,
  onSubmit,
  onOpenFilter,
}: SearchToolbarProps) {
  return (
    <div className="sticky top-[72px] z-30 bg-[#FAF8F4]/95 backdrop-blur-md py-3 flex items-center gap-3">
      <Link
        href="/"
        className="w-11 h-11 shrink-0 rounded-full bg-white border border-[#E8E4DC] hover:bg-[#E9F7F0] flex items-center justify-center text-gray-700 shadow-xs transition-colors"
      >
        <span className="material-symbols-outlined text-[20px]">arrow_back</span>
      </Link>

      <form
        onSubmit={onSubmit}
        className="flex-1 relative flex items-center gap-2 bg-white border border-[#E8E4DC] rounded-full pl-4 pr-1.5 sm:pl-5 py-1.5 sm:py-2 shadow-xs"
      >
        <span className="material-symbols-outlined text-[#0F5F4A] text-[20px]">search</span>
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={placeholder}
          aria-label="Từ khóa tìm kiếm"
          className="flex-1 min-w-0 bg-transparent text-sm font-semibold text-[#121E1A] placeholder:text-[#6F7974] outline-none"
        />
        <button
          type="submit"
          aria-label="Tìm"
          title="Tìm"
          className="shrink-0 px-3 sm:px-5 py-1.5 sm:py-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-xs sm:text-sm font-semibold transition-colors"
        >
          <span className="material-symbols-outlined text-[18px] sm:hidden">search</span>
        </button>
      </form>

      <FilterButton activeFilterCount={activeFilterCount} onClick={onOpenFilter} variant="toolbar" />
    </div>
  );
}