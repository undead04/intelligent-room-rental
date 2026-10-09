import KpiCard from "@/components/KpiCard";
import type { PriceStatsDto } from "@/types/dto";
import { formatPrice } from "@/lib/utils/listing";

interface PriceStatsOverviewProps {
  stats: PriceStatsDto | null;
}

export default function PriceStatsOverview({ stats }: PriceStatsOverviewProps) {
  const general = stats?.price_stats_general;
  const priceFluctuation = general?.price_fluctuation_month ?? null;
  const isPriceUp = (priceFluctuation ?? 0) >= 0;

  const postingGrowth = general?.hotspot_posting_growth_month ?? null;
  const isGrowthUp = (postingGrowth ?? 0) >= 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
      <KpiCard
        label="Giá trung bình"
        value={formatPrice(general?.average_price_vnd, "...")}
        unit="/tháng"
        icon="payments"
        footer={
          <>
            {priceFluctuation !== null ? (
              <span
                className={`inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  isPriceUp
                    ? "bg-[#E6F4EE] text-[#0F5F4A]"
                    : "bg-[#FEECEC] text-[#D32F2F]"
                }`}
              >
                <span className="material-symbols-outlined text-[14px]">
                  {isPriceUp ? "trending_up" : "trending_down"}
                </span>
                {priceFluctuation > 0 ? `+${priceFluctuation}%` : `${priceFluctuation}%`}
              </span>
            ) : (
              <span className="text-xs text-gray-400 font-medium">--</span>
            )}
            <span className="text-xs text-gray-500">so với tháng trước</span>
          </>
        }
      />

      <KpiCard
        label="Tổng tin phân tích"
        value={`${general?.total_listings ?? "..."}`}
        unit="căn"
        icon="bar_chart"
        tone="neutral"
        footer={
          <span className="flex items-center gap-2 text-xs text-[#0F5F4A] font-semibold">
            <span className="material-symbols-outlined text-[16px]">sync</span>
            <span>Cập nhật liên tục 24h qua</span>
          </span>
        }
      />

      <KpiCard
        label="Khu vực sôi động nhất"
        value={general?.area_hotspot || "Đang cập nhật"}
        unit=""
        icon="local_fire_department"
        tone="coral"
        compactValue
        footer={
          postingGrowth !== null ? (
            <span
              className={`inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full text-xs font-bold ${
                isGrowthUp ? "bg-[#FFF0ED] text-[#FF6B4A]" : "bg-gray-100 text-gray-600"
              }`}
            >
              <span className="material-symbols-outlined text-[14px]">whatshot</span>
              {postingGrowth > 0
                ? `Tin đăng tăng +${postingGrowth}%`
                : `Tin đăng giảm ${postingGrowth}%`}{" "}
              <span className="text-gray-400 font-normal">sv tháng trước</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full bg-[#FFF0ED] text-[#FF6B4A] text-xs font-bold">
              <span className="material-symbols-outlined text-[14px]">whatshot</span>
              Khu vực có nhiều tin nhất
            </span>
          )
        }
      />
    </div>
  );
}