"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";
import { locationsApi, priceStatsApi } from "@/lib/api/client";
import type { CityDto, DistrictDto, PriceStatsDto } from "@shared/dto";
import { PriceStatsSkeleton } from "@/components/LoadingSkeleton";
import Breadcrumbs from "@/components/Breadcrumbs";
import { formatPrice } from "@/lib/utils/listing";

export default function PriceAnalyticsPage() {
  const [selectedCity, setSelectedCity] = useState("Hồ Chí Minh");
  const [selectedType, setSelectedType] = useState("Tất cả");
  const [cities, setCities] = useState<CityDto[]>([]);
  const [cityId, setCityId] = useState<number | undefined>();
  const [districtId, setDistrictId] = useState<number | undefined>();
  const [districts, setDistricts] = useState<DistrictDto[]>([]);
  const [stats, setStats] = useState<PriceStatsDto | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    locationsApi.cities().then((result) => {
      setCities(result);
      const city = result.find((item) => item.name.includes("Hồ Chí Minh")) || result[0];
      if (city) {
        setSelectedCity(city.name);
        setCityId(city.id);
      }
    }).catch(() => setApiError("Không thể tải danh sách thành phố."));
  }, []);

  useEffect(() => {
    if (cityId === undefined) return;
    setDistrictId(undefined);
    setDistricts([]);
    locationsApi.districts({ city_id: cityId })
      .then(setDistricts)
      .catch(() => setApiError("Không thể tải danh sách quận/huyện."));
  }, [cityId]);

  useEffect(() => {
    if (cityId === undefined) return;
    setIsLoading(true);
    priceStatsApi.get({ city_id: cityId, district_id: districtId })
      .then(setStats)
      .catch(() => {
        setApiError("Không thể tải thống kê giá từ máy chủ.");
        setStats(null);
      })
      .finally(() => setIsLoading(false));
  }, [cityId, districtId]);

  const districtData = (stats?.price_stats_by_area || []).map((item) => ({
    id: item.area_id,
    name: item.area,
    avgPrice: formatPrice(item.average_price_vnd),
    range: `${formatPrice(item.minimum_price_vnd)} - ${formatPrice(item.maximum_price_vnd)}`,
    trend: item.fluctuation_month === null ? "--" : `${item.fluctuation_month > 0 ? "+" : ""}${item.fluctuation_month}%`,
    status: (item.fluctuation_month || 0) >= 0 ? "up" : "down",
    total: item.total_listings,
  }));

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

        {/* 3 KPI Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
          {/* Card 1 */}
          <div className="bg-white rounded-2xl p-5 border border-[#E8E4DC] shadow-xs flex flex-col justify-between">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs uppercase font-bold text-gray-400 tracking-wider">Giá trung bình</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="font-['Plus_Jakarta_Sans'] text-3xl font-extrabold text-[#0F5F4A]">{formatPrice(stats?.price_stats_general.average_price_vnd, "...")}</span>
                  <span className="text-xs text-gray-500">/tháng</span>
                </div>
              </div>
              <div className="w-12 h-12 rounded-2xl bg-[#E6F4EE] flex items-center justify-center text-[#0F5F4A]">
                <span className="material-symbols-outlined text-[24px]">payments</span>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">
              <span className="inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
                <span className="material-symbols-outlined text-[14px]">trending_up</span>
                +2.4%
              </span>
              <span className="text-xs text-gray-500">so với tháng trước</span>
            </div>
          </div>

          {/* Card 2 */}
          <div className="bg-white rounded-2xl p-5 border border-[#E8E4DC] shadow-xs flex flex-col justify-between">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs uppercase font-bold text-gray-400 tracking-wider">Tổng tin phân tích</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="font-['Plus_Jakarta_Sans'] text-3xl font-extrabold text-[#121E1A]">{stats?.price_stats_general.total_listings ?? "..."}</span>
                  <span className="text-xs text-gray-500">căn</span>
                </div>
              </div>
              <div className="w-12 h-12 rounded-2xl bg-[#E6F4EE] flex items-center justify-center text-[#0F5F4A]">
                <span className="material-symbols-outlined text-[24px]">bar_chart</span>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100 text-xs text-[#0F5F4A] font-semibold">
              <span className="material-symbols-outlined text-[16px]">sync</span>
              <span>Cập nhật liên tục 24h qua</span>
            </div>
          </div>

          {/* Card 3 */}
          <div className="bg-white rounded-2xl p-5 border border-[#E8E4DC] shadow-xs flex flex-col justify-between">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs uppercase font-bold text-gray-400 tracking-wider">Khu vực sôi động nhất</span>
                <div className="flex items-baseline gap-1 mt-1">
                  <span className="font-['Plus_Jakarta_Sans'] text-2xl font-extrabold text-[#FF6B4A]">{stats?.price_stats_general.area_hotspot || "Đang cập nhật"}</span>
                  <span className="text-xs text-gray-500 font-semibold">(Gò Vấp)</span>
                </div>
              </div>
              <div className="w-12 h-12 rounded-2xl bg-[#FFF0ED] flex items-center justify-center text-[#FF6B4A]">
                <span className="material-symbols-outlined text-[24px]">local_fire_department</span>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">
              <span className="inline-flex items-center gap-0.5 px-2.5 py-0.5 rounded-full bg-[#FFF0ED] text-[#FF6B4A] text-xs font-bold">
                <span className="material-symbols-outlined text-[14px]">whatshot</span>
                Lượt tìm tăng 38%
              </span>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="bg-white rounded-2xl p-4 border border-[#E8E4DC] shadow-xs mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <select
                value={selectedCity}
                onChange={(e) => {
                  const city = cities.find((item) => item.name === e.target.value);
                  setSelectedCity(e.target.value);
                  setCityId(city?.id);
                }}
                className="custom-select px-4 py-2.5 pr-10 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs font-bold text-[#0F5F4A] outline-none"
              >
                {cities.length > 0
                  ? cities.map((city) => <option key={city.id}>{city.name}</option>)
                  : <option>Đang tải...</option>}
              </select>
              <span className="material-symbols-outlined pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[18px] text-[#0F5F4A]">
                expand_more
              </span>
            </div>

            <div className="relative">
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="custom-select px-4 py-2.5 pr-10 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs font-semibold text-gray-700 outline-none"
              >
                <option>Tất cả loại phòng</option>
                <option>Phòng trọ / KTX</option>
                <option>Căn hộ dịch vụ</option>
                <option>Chung cư mini</option>
                <option>Nhà nguyên căn</option>
              </select>
              <span className="material-symbols-outlined pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-[18px] text-[#0F5F4A]">
                expand_more
              </span>
            </div>
          </div>

          <div className="text-xs text-gray-500 font-medium">
            Thời gian: <strong>30 ngày gần nhất</strong>
          </div>
        </div>

        {/* District Price Comparison Table */}
        <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-xs overflow-hidden mb-10">
          <div className="p-5 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A]">
                Bảng giá thuê bình quân theo từng {districtId ? "Phường / Xã" : "Quận / Khu vực"}
              </h2>
              {districtId && (
                <button
                  type="button"
                  onClick={() => setDistrictId(undefined)}
                  className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-[#0F5F4A] hover:underline"
                >
                  <span className="material-symbols-outlined text-[14px]">arrow_back</span>
                  Quay lại danh sách quận
                </button>
              )}
            </div>
            <span className="text-xs text-gray-500">Đơn vị: VNĐ / tháng</span>
          </div>

          {isLoading ? (
            <PriceStatsSkeleton />
          ) : <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-[#FAF8F4] border-b border-[#E8E4DC] text-gray-600 font-bold uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 px-6">{districtId ? "Phường / Xã" : "Quận / Huyện"}</th>
                  <th className="py-3.5 px-6">Giá trung bình</th>
                  <th className="py-3.5 px-6">Khoảng giá phổ biến</th>
                  <th className="py-3.5 px-6">Biến động (Tháng)</th>
                  <th className="py-3.5 px-6">Số lượng phòng</th>
                  <th className="py-3.5 px-6 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {districtData.map((d) => (
                  <tr key={d.name} className="hover:bg-[#FAF8F4]/80 transition-colors">
                    <td className="py-4 px-6 font-bold text-sm text-[#121E1A]">{d.name}</td>
                    <td className="py-4 px-6 font-extrabold text-sm text-[#0F5F4A]">{d.avgPrice}</td>
                    <td className="py-4 px-6 text-gray-600">{d.range}</td>
                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center gap-1 font-bold ${
                          d.status === "up" ? "text-red-500" : "text-emerald-600"
                        }`}
                      >
                        {d.status === "up" ? "▲" : "▼"} {d.trend}
                      </span>
                    </td>
                    <td className="py-4 px-6 text-gray-600">{d.total} phòng</td>
                    <td className="py-4 px-6 text-right">
                      {districtId ? (
                        <Link
                          href={`/tim-kiem?district_id=${districtId}&ward_id=${d.id}`}
                          className="px-3.5 py-1.5 rounded-full bg-[#E6F4EE] hover:bg-[#0F5F4A] hover:text-white text-[#0F5F4A] font-semibold transition-all inline-block"
                        >
                          Tìm phòng
                        </Link>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setDistrictId(d.id)}
                          className="px-3.5 py-1.5 rounded-full bg-[#E6F4EE] hover:bg-[#0F5F4A] hover:text-white text-[#0F5F4A] font-semibold transition-all"
                        >
                          Xem phường
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>}
        </div>
      </main>

    </SiteLayout>
  );
}
