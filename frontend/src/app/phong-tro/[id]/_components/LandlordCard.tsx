import type { ListingDetailDto } from "@shared/dto";

interface LandlordCardProps {
  listing: ListingDetailDto | null;
  defaultImage: string;
  showPhone: boolean;
  onTogglePhone: () => void;
}

export default function LandlordCard({ listing, defaultImage, showPhone, onTogglePhone }: LandlordCardProps) {
  return (
    <aside className="self-start lg:sticky lg:top-24 lg:col-span-4 lg:h-fit">
      <div className="rounded-2xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3.5 border-b border-gray-100 pb-4">
          <div className="h-14 w-14 shrink-0 overflow-hidden rounded-full border-2 border-[#0F5F4A] bg-gray-200">
            <img
              src={listing?.poster?.avatar_url || defaultImage}
              alt={listing?.poster?.name || "Chủ nhà"}
              onError={(event) => {
                event.currentTarget.onerror = null;
                event.currentTarget.src = defaultImage;
              }}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="min-w-0">
            <h3 className="truncate font-['Plus_Jakarta_Sans'] text-base font-bold text-[#121E1A]">
              {listing?.poster?.name || "Chủ nhà Homigo"}
            </h3>
            <div className="mt-0.5 flex items-center gap-1 text-xs font-semibold text-[#0F5F4A]">
              <span className="material-symbols-outlined text-[16px]">verified</span>
              <span>Chủ nhà xác thực Homigo</span>
            </div>
            <div className="mt-1 text-[11px] text-gray-500">Phản hồi trong 5 phút</div>
          </div>
        </div>

        <div className="space-y-3 py-4">
          <button
            onClick={onTogglePhone}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-[#0F5F4A] py-3.5 text-sm font-bold text-white shadow-sm transition-all hover:bg-[#004635]"
          >
            <span className="material-symbols-outlined text-[20px]">call</span>
            <span>{showPhone ? "0784 498 868" : "Gọi điện: 0784 498 ***"}</span>
          </button>
          {listing?.url && (
            <a
              href={listing.url}
              target="_blank"
              rel="noreferrer"
              className="flex w-full items-center justify-center gap-2 rounded-full bg-[#E6F4EE] py-3.5 text-sm font-bold text-[#0F5F4A] transition-all hover:bg-[#D5EFE5]"
            >
              <span className="material-symbols-outlined text-[20px]">open_in_new</span>
              <span>Xem tin gốc trên Chợ Tốt</span>
            </a>
          )}
        </div>

        <div className="space-y-1 rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] p-3 text-xs text-gray-600">
          <div className="font-semibold text-[#121E1A]">🛡️ Cam kết Homigo</div>
          <p>Tin đăng thật 100%, không thu phí trung gian của người thuê phòng.</p>
        </div>
      </div>
    </aside>
  );
}
