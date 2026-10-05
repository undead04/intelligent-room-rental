import KpiCard from "@/components/KpiCard";
import type { PriceStatsDto } from "@shared/dto";
import { formatPrice } from "@/lib/utils/listing";

interface PriceStatsOverviewProps {
  stats: PriceStatsDto | null;
}

export default function PriceStatsOverview({ stats }: PriceStatsOverviewProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
      <KpiCard
        label="Giá trung bình"
        value={formatPrice(stats?.price_stats_general.average_price_vnd, "...")}
        unit="/tháng"
        icon="payments"
        footer={
          <>
            <span className="inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
              <span className="material-symbols-outlined text-[14px]">trending_up</span>
              +2.4%
            </span>
            <span className="text-xs text-gray-500">so với tháng trước</span>
          </>
        }
      />

      <KpiCard
        label="Tổng tin phân tích"
        value={`${stats?.price_stats_general.total_listings ?? "..."}`}
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
        value={stats?.price_stats_general.area_hotspot || "Đang cập nhật"}
        unit="(Gò Vấp)"
        icon="local_fire_department"
        tone="coral"
        compactValue
        footer={
          <span className="inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full bg-[#FFF0ED] text-[#FF6B4A] text-xs font-bold">
            <span className="material-symbols-outlined text-[14px]">whatshot</span>
            Lượt tìm tăng 38%
          </span>
        }
      />
    </div>
  );
}