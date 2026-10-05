interface FilterButtonProps {
  activeFilterCount: number;
  onClick: () => void;
  variant: "hero" | "toolbar";
}

const VARIANT_STYLES = {
  hero: {
    title: "Mở bộ lọc nâng cao",
    button: "w-10 h-10 bg-[#E9F7F0] hover:bg-[#E3F1EA] transition-colors",
    badge: "h-4 w-4 shadow-sm",
  },
  toolbar: {
    title: "Mở bộ lọc",
    button: "w-11 h-11 bg-white border border-[#0F5F4A] hover:bg-[#E9F7F0] shadow-xs transition-all",
    badge: "w-5 h-5",
  },
} as const;

export default function FilterButton({ activeFilterCount, onClick, variant }: FilterButtonProps) {
  const styles = VARIANT_STYLES[variant];

  return (
    <button
      type="button"
      onClick={onClick}
      title={styles.title}
      className={`relative flex items-center cursor-pointer justify-center rounded-full text-[#0F5F4A] shrink-0 ${styles.button}`}
    >
      <span className="material-symbols-outlined text-[20px]">tune</span>
      {activeFilterCount > 0 && (
        <span
          className={`absolute -top-1 -right-1 flex items-center justify-center rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold ${styles.badge}`}
        >
          {activeFilterCount}
        </span>
      )}
    </button>
  );
}