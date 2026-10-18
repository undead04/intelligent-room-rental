import SearchBar from "@/components/SearchBar";

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
    <section className="w-full bg-gradient-to-b from-[#EFFDF6] via-[#EFFDF6]/70 to-[#FAF8F4] pt-5 pb-3">
      <div className="max-w-4xl mx-auto px-4 flex flex-col items-center text-center">
        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#0F5F4A] tracking-tight mb-1.5">
          Tìm phòng trọ, căn hộ ưng ý cùng AI
        </h1>
        <p className="text-sm sm:text-base text-[#3F4944] mb-4">
          Hàng ngàn tin đăng được xác thực mỗi ngày từ các nguồn uy tín
        </p>

        <SearchBar
          query={query}
          placeholder="Bạn muốn tìm phòng ở đâu? (vd: gần ĐH Bách Khoa, dưới 4 triệu...)"
          activeFilterCount={activeFilterCount}
          onQueryChange={onQueryChange}
          onSubmit={onSubmit}
          onOpenFilter={onOpenFilter}
          size="hero"
        />
      </div>
    </section>
  );
}