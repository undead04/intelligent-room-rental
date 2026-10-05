import Link from "next/link";
import PriceStatsSkeleton from "@/components/skeleton/PriceStatsSkeleton";
import type { PriceStatRow } from "@/lib/utils/priceStats";

interface PriceStatsTableProps {
  rows: PriceStatRow[];
  cityId: number | undefined;
  districtId: number | undefined;
  isLoading: boolean;
  onSelectDistrict: (districtId: number | undefined) => void;
}

export default function PriceStatsTable({
  rows,
  districtId,
  isLoading,
  onSelectDistrict,
  cityId,
}: PriceStatsTableProps) {
  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-xs overflow-hidden mb-10">
      <div className="p-5 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A]">
            Bảng giá thuê bình quân theo từng {districtId ? "Phường / Xã" : "Quận / Khu vực"}
          </h2>
          {districtId && (
            <button
              type="button"
              onClick={() => onSelectDistrict(undefined)}
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
      ) : (
      <div className="overflow-x-auto">
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
            {rows.map((row) => (
              <tr key={row.name} className="hover:bg-[#FAF8F4]/80 transition-colors">
                <td className="py-4 px-6 font-bold text-sm text-[#121E1A]">{row.name}</td>
                <td className="py-4 px-6 font-extrabold text-sm text-[#0F5F4A]">{row.avgPrice}</td>
                <td className="py-4 px-6 text-gray-600">{row.range}</td>
                <td className="py-4 px-6">
                  <span
                    className={`inline-flex items-center gap-1 font-bold ${
                      row.status === "up" ? "text-red-500" : "text-emerald-600"
                    }`}
                  >
                    {row.status === "up" ? "▲" : "▼"} {row.trend}
                  </span>
                </td>
                <td className="py-4 px-6 text-gray-600">{row.total} phòng</td>
                <td className="py-4 px-6 text-right">
                  {districtId ? (
                    <Link
                      href={`/tim-kiem?city_id=${cityId}&district_id=${districtId}&ward_id=${row.id}`}
                      className="px-3.5 py-1.5 rounded-full bg-[#E6F4EE] hover:bg-[#0F5F4A] hover:text-white text-[#0F5F4A] font-semibold transition-all inline-block"
                    >
                      Tìm phòng
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={() => onSelectDistrict(row.id)}
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
      </div>
      )}
    </div>
  );
}