interface HeroSearchProps {
  query: string;
  activeFilterCount: number;
  onQueryChange: (value: string) => void;
  onOpenFilter: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
}

export default function HeroSearch({
  query,
  activeFilterCount,
  onQueryChange,
  onOpenFilter,
  onSubmit,
}: HeroSearchProps) {
  return (
    <section className="w-full bg-gradient-to-b from-[#EFFDF6] via-[#EFFDF6]/70 to-[#FAF8F4] pt-6 pb-4">
      <div className="max-w-4xl mx-auto px-4 flex flex-col items-center text-center">
        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#0F5F4A] tracking-tight mb-2">
          Tìm phòng trọ, căn hộ ưng ý cùng AI
        </h1>
        <p className="text-sm sm:text-base text-[#3F4944] mb-6">
          Hàng ngàn tin đăng được xác thực mỗi ngày từ các nguồn uy tín
        </p>

        {/* Pill Search Bar */}
        <form onSubmit={onSubmit} className="w-full relative flex items-center bg-white rounded-full h-14 border border-[#E8E4DC] shadow-[0_4px_20px_rgba(15,95,74,0.06)] px-5 gap-3 transition-shadow focus-within:shadow-[0_6px_24px_rgba(15,95,74,0.12)]">
          <span className="material-symbols-outlined text-[#6F7974] text-[22px] shrink-0">search</span>
          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Bạn muốn tìm phòng ở đâu? (vd: gần ĐH Bách Khoa, dưới 4 triệu...)"
            className="w-full h-full bg-transparent text-sm text-[#121E1A] placeholder:text-[#6F7974] outline-none"
          />
          <button
            type="button"
            onClick={onOpenFilter}
            className="relative flex items-center cursor-pointer justify-center w-10 h-10 rounded-full bg-[#E9F7F0] hover:bg-[#E3F1EA] text-[#0F5F4A] transition-colors shrink-0 "
            title="Mở bộ lọc nâng cao"
          >
            <span className="material-symbols-outlined text-[20px]">tune</span>
            {activeFilterCount > 0 && (
              <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold shadow-sm">
                {activeFilterCount}
              </span>
            )}
          </button>
          <button type="submit" className="px-5 py-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-sm font-semibold transition-all shrink-0 hidden sm:inline-flex items-center gap-1.5">
            <span>Tìm</span>
          </button>
        </form>
      </div>
    </section>
  );
}