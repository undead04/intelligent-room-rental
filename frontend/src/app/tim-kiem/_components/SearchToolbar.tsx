import Link from "next/link";
import SearchBar from "@/components/SearchBar";

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

      <SearchBar
        query={query}
        placeholder={placeholder}
        activeFilterCount={activeFilterCount}
        onQueryChange={onQueryChange}
        onSubmit={onSubmit}
        onOpenFilter={onOpenFilter}
        size="compact"
      />
    </div>
  );
}