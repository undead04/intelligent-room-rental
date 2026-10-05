"use client";

import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";
import Breadcrumbs from "@/components/Breadcrumbs";
import PriceStatsOverview from "@/app/tra-cuu-gia-tro/_components/PriceStatsOverview";
import PriceStatsFilterBar from "@/app/tra-cuu-gia-tro/_components/PriceStatsFilterBar";
import PriceStatsTable from "@/app/tra-cuu-gia-tro/_components/PriceStatsTable";
import { usePriceStats } from "@/app/tra-cuu-gia-tro/_hooks/usePriceStats";

export default function PriceAnalyticsPage() {
  const {
    stats,
    rows,
    cities,
    cityId,
    selectCity,
    districtId,
    selectDistrict,
    apiError,
    isLoading,
  } = usePriceStats();

  return (
    <SiteLayout className="bg-[#FAF8F4]">

      <main className="max-w-[1500px] mx-auto px-4 lg:px-8 pt-6 pb-16 w-full flex-1">
        {apiError && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {apiError}
          </div>
        )}

        {/* Breadcrumb */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <Breadcrumbs
            items={[
              { label: "Trang chủ", href: "/" },
              { label: "Tra cứu giá trọ thị trường" },
            ]}
          />
          <Link
            href="/tim-kiem"
            className="inline-flex items-center gap-1.5 text-xs text-[#0F5F4A] font-semibold hover:underline"
          >
            <span className="material-symbols-outlined text-[16px]">arrow_back</span>
            <span>Xem phòng theo quận</span>
          </Link>
        </div>

        {/* Title Header */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 mb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4EE] mb-2 text-[#0F5F4A] text-[11px] uppercase tracking-wider font-bold">
              <span className="material-symbols-outlined text-[14px]">query_stats</span>
              <span>Báo cáo thời gian thực</span>
            </div>
            <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] tracking-tight">
              Thống kê & Biến động giá phòng trọ
            </h1>
            <p className="text-xs sm:text-sm text-gray-600 mt-1">
              Dữ liệu phân tích thực tế từ 10.000+ tin đăng và giao dịch đã xác thực trên hệ thống Homigo.
            </p>
          </div>

          <div className="flex items-center gap-3 px-4 py-2 rounded-2xl bg-white border border-[#E8E4DC] shadow-2xs">
            <span className="material-symbols-outlined text-[#0F5F4A] text-[22px]">verified_user</span>
            <div>
              <div className="text-xs font-bold text-[#121E1A]">Homigo Index Shield</div>
              <div className="text-[10px] text-gray-500">Độ tin cậy dữ liệu: 99.4%</div>
            </div>
          </div>
        </div>

        <PriceStatsOverview stats={stats} />

        <PriceStatsFilterBar cities={cities} cityId={cityId} onCityChange={selectCity} />

        <PriceStatsTable
          rows={rows}
          districtId={districtId}
          isLoading={isLoading}
          onSelectDistrict={selectDistrict}
          cityId={cityId}
        />
      </main>

    </SiteLayout>
  );
}