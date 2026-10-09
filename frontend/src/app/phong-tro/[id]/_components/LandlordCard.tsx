import type { ListingDetailDto } from "@/types/dto";
import ImageWithFallback from "@/components/ImageWithFallback";

interface LandlordCardProps {
  listing: ListingDetailDto | null;
  defaultImage: string;
  showPhone: boolean;
  onTogglePhone: () => void;
}

interface StatItemProps {
  icon: string;
  value: number;
  label: string;
}

function StatItem({ icon, value, label }: StatItemProps) {
  return (
    <div className="flex items-center gap-2.5 rounded-xl bg-[#FAF8F4] px-3 py-2.5">
      <span className="material-symbols-outlined text-[20px] text-[#0F5F4A]">{icon}</span>
      <div className="min-w-0 leading-tight">
        <div className="font-['Plus_Jakarta_Sans'] text-base font-bold text-[#121E1A]">
          {value.toLocaleString("vi-VN")}
        </div>
        <div className="truncate text-[11px] text-gray-500">{label}</div>
      </div>
    </div>
  );
}

export default function LandlordCard({ listing, defaultImage, showPhone, onTogglePhone }: LandlordCardProps) {
  const poster = listing?.poster;
  const isCompany = poster?.is_company ?? false;
  const liveAds = poster?.live_ads ?? 0;
  const soldAds = poster?.sold_ads ?? 0;

  return (
    <aside className="self-start lg:sticky lg:top-24 lg:col-span-4 lg:h-fit">
      <div className="rounded-2xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3.5 border-b border-gray-100 pb-4">
          <div className="h-14 w-14 shrink-0 overflow-hidden rounded-full border-2 border-[#0F5F4A] bg-gray-200">
            <ImageWithFallback
              src={poster?.avatar_url || defaultImage}
              alt={poster?.name || "Chủ nhà"}
              fallbackSrc={defaultImage}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="min-w-0">
            <h3 className="truncate font-['Plus_Jakarta_Sans'] text-base font-bold text-[#121E1A]">
              {poster?.name || "Chủ nhà Homigo"}
            </h3>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  isCompany ? "bg-[#FFF3DC] text-[#8A5A00]" : "bg-gray-100 text-gray-600"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">
                  {isCompany ? "apartment" : "person"}
                </span>
                {isCompany ? "Doanh nghiệp" : "Cá nhân"}
              </span>
              <span className="inline-flex items-center gap-1 text-xs font-semibold text-[#0F5F4A]">
                <span className="material-symbols-outlined text-[16px]">verified</span>
                Xác thực Homigo
              </span>
            </div>
            <div className="mt-1 text-[11px] text-gray-500">Phản hồi trong 5 phút</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2.5 border-b border-gray-100 py-4">
          <StatItem icon="campaign" value={liveAds} label="Tin đang đăng" />
          <StatItem icon="task_alt" value={soldAds} label="Đã cho thuê" />
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