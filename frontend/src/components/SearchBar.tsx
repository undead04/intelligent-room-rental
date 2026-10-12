import FilterButton from "@/components/FilterButton";

interface SearchBarProps {
  query: string;
  placeholder: string;
  activeFilterCount: number;
  onQueryChange: (value: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
  onOpenFilter: () => void;
  size?: "hero" | "compact";
}

const SIZE_STYLES = {
  hero: {
    form: "w-full relative flex items-center gap-3 h-14 px-5 bg-white rounded-full border border-[#E8E4DC] shadow-[0_4px_20px_rgba(15,95,74,0.06)] transition-shadow focus-within:shadow-[0_6px_24px_rgba(15,95,74,0.12)]",
    icon: "text-[22px] text-[#6F7974]",
    input: "w-full min-w-0 text-sm font-normal text-[#121E1A]",
    submit: "hidden sm:inline-flex items-center px-5 py-2 text-sm font-semibold",
    filterVariant: "hero" as const,
  },
  compact: {
    form: "flex-1 min-w-0 relative flex items-center gap-2 pl-4 pr-1.5 sm:pl-5 py-1.5 sm:py-2 bg-white rounded-full border border-[#E8E4DC] shadow-xs",
    icon: "text-[20px] text-[#0F5F4A]",
    input: "flex-1 min-w-0 text-sm font-semibold text-[#121E1A]",
    submit: "shrink-0 px-3 sm:px-5 py-1.5 sm:py-2 text-xs sm:text-sm font-semibold",
    filterVariant: "toolbar" as const,
  },
};

const SUBMIT_STYLE = "rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white transition-colors";
const INPUT_STYLE = "bg-transparent placeholder:text-[#6F7974] outline-none";

export default function SearchBar({
  query,
  placeholder,
  activeFilterCount,
  onQueryChange,
  onSubmit,
  onOpenFilter,
  size = "hero",
}: SearchBarProps) {
  const styles = SIZE_STYLES[size];

  return (
    <form onSubmit={onSubmit} className={styles.form}>
      <span className={`material-symbols-outlined shrink-0 ${styles.icon}`}>search</span>
      <input
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder={placeholder}
        aria-label="Từ khóa tìm kiếm"
        className={`${styles.input} ${INPUT_STYLE}`}
      />
      <FilterButton
        activeFilterCount={activeFilterCount}
        onClick={onOpenFilter}
        variant={styles.filterVariant}
      />
      <button type="submit" aria-label="Tìm" title="Tìm" className={`${styles.submit} ${SUBMIT_STYLE}`}>
        <span className="material-symbols-outlined text-[18px] sm:hidden">search</span>
        <span className="hidden sm:inline">Tìm</span>
      </button>
    </form>
  );
}