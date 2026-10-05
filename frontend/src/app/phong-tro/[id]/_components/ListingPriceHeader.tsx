import { FALLBACK_LISTING_CODE } from "../_constants/fallbackListing";

interface ListingPriceHeaderProps {
  title: string;
  location: string;
  price: string;
  isSaved: boolean;
  onToggleSave: () => void;
}

export default function ListingPriceHeader({
  title,
  location,
  price,
  isSaved,
  onToggleSave,
}: ListingPriceHeaderProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="px-3 py-1 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
          Homigo Verified
        </span>
        <span className="px-3 py-1 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs text-gray-600">
          Mã tin: {FALLBACK_LISTING_CODE}
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

      <div className="p-4 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-baseline gap-2">
          <span className="font-['Plus_Jakarta_Sans'] font-black text-3xl text-[#FF6B4A]">
            {price}
          </span>
        </div>
      </div>
    </div>
  );
}