interface ListingPriceHeaderProps {
  title: string;
  location: string;
  price: string;
  area?: string;
  isSaved: boolean;
  onToggleSave: () => void;
}

export default function ListingPriceHeader({
  title,
  location,
  price,
  area,
  isSaved,
  onToggleSave,
}: ListingPriceHeaderProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="px-3 py-1 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
          Homigo Verified
        </span>
        <button
          onClick={onToggleSave}
          className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-[#DCECE4] bg-[#F5FBF7] px-3 py-1.5 text-xs font-semibold text-[#0F5F4A]"
        >
          <span className="material-symbols-outlined text-[16px]">{isSaved ? "bookmark_added" : "bookmark"}</span>
          {isSaved ? "Đã lưu" : "Lưu tin"}
        </button>
      </div>

      <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl text-[#121E1A] mb-3">
        {title}
      </h1>

      <p className="text-xs sm:text-sm text-gray-600 flex items-center gap-1.5 mb-4">
        <span className="material-symbols-outlined text-[#0F5F4A] text-[18px]">location_on</span>
        <span>{location}</span>
      </p>

      <div className="p-5 rounded-2xl bg-[#FAF8F4] border border-[#E8E4DC] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-6 sm:gap-8 flex-wrap">
          <div>
            <span className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1">
              Giá thuê
            </span>
            <div className="flex items-baseline gap-1">
              <span className="font-['Plus_Jakarta_Sans'] font-black text-2xl sm:text-3xl text-[#FF6B4A]">
                {price}
              </span>
            </div>
          </div>

          {area && (
            <>
              <div className="hidden sm:block w-px h-10 bg-[#E0DCD3]" />
              <div>
                <span className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                  Diện tích
                </span>
                <div className="flex items-baseline gap-1">
                  <span className="font-['Plus_Jakarta_Sans'] font-black text-2xl sm:text-3xl text-[#121E1A]">
                    {area}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white border border-[#E8E4DC] text-xs font-semibold text-gray-700 shadow-2xs">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span>Đang cho thuê</span>
        </div>
      </div>
    </div>
  );
}