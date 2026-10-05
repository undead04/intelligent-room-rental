import Link from "next/link";

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
        className="flex-1 relative flex items-center bg-white border border-[#E8E4DC] rounded-full px-5 py-2.5 shadow-xs"
      >
        <span className="material-symbols-outlined text-[#0F5F4A] mr-3 text-[20px]">search</span>
        <input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 bg-transparent text-sm font-semibold text-[#121E1A] placeholder:text-[#6F7974] outline-none"
        />
      </form>

      <button
        onClick={onOpenFilter}
        className="relative w-11 h-11 shrink-0 rounded-full bg-white border border-[#0F5F4A] hover:bg-[#E9F7F0] text-[#0F5F4A] flex items-center justify-center shadow-xs transition-all"
        title="Mở bộ lọc"
      >
        <span className="material-symbols-outlined text-[20px]">tune</span>
        {activeFilterCount > 0 && (
          <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold flex items-center justify-center">
            {activeFilterCount}
          </span>
        )}
      </button>
    </div>
  );
}