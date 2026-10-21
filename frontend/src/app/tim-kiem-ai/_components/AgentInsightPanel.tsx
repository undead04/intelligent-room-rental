"use client";

import Link from "next/link";
import { useMemo } from "react";
import type { DecisionInsight, RoomItem } from "@/app/tim-kiem-ai/types";

interface AgentInsightPanelProps {
  room?: RoomItem | null;
  insights?: DecisionInsight | null;
  rooms?: RoomItem[];
}

const FACTOR_LABELS: Record<string, { label: string; icon: string }> = {
  price: { label: "Độ hợp lý giá (ML)", icon: "payments" },
  location: { label: "Vị trí & Khoảng cách", icon: "near_me" },
  safety: { label: "An ninh khu vực", icon: "shield" },
  amenity: { label: "Tiện nghi yêu cầu", icon: "home_iot_device" },
  semantic: { label: "Độ khớp nhu cầu", icon: "psychology" },
};

const FACTOR_ORDER = ["price", "location", "safety", "amenity", "semantic"];

export default function AgentInsightPanel({
  room,
  insights,
  rooms = [],
}: AgentInsightPanelProps) {
  const explainBreakdown = useMemo(() => {
    if (!room?.explain_match) return null;
    const rawFactors = Array.isArray(room.explain_match.top_factors)
      ? (room.explain_match.top_factors as Record<string, unknown>[])
      : [];
    const weakFactors: string[] = Array.isArray(room.explain_match.weak_factors)
      ? (room.explain_match.weak_factors as string[])
      : [];

    const factors = rawFactors.map((f: Record<string, unknown>) => {
      const key = String(f.name || "");
      const meta = FACTOR_LABELS[key] || { label: key, icon: "analytics" };
      const fitPct = Math.round(Number(f.fit || 0) * 100);
      const weightPct = Math.round(Number(f.weight || 0) * 100);
      return {
        key,
        label: meta.label,
        icon: meta.icon,
        fitPct,
        weightPct,
        contribution: Number(f.contribution || 0),
      };
    });

    // Cố định thứ tự các tiêu chí theo chuẩn hệ thống để vị trí không bị xáo trộn khi chuyển phòng
    factors.sort((a, b) => {
      const idxA = FACTOR_ORDER.indexOf(a.key);
      const idxB = FACTOR_ORDER.indexOf(b.key);
      return (idxA !== -1 ? idxA : 99) - (idxB !== -1 ? idxB : 99);
    });

    return {
      factors,
      weakLabels: weakFactors.map((w) => FACTOR_LABELS[w]?.label || w),
    };
  }, [room]);

  // Compute comparison: compare selected room with the other 4 rooms
  const comparisonWithOtherRooms = useMemo(() => {
    if (!room || rooms.length <= 1) return null;

    const otherRooms = rooms.filter((r) => r.id !== room.id);
    const count = otherRooms.length;

    // 1. Price comparison
    const avgOtherPrice =
      otherRooms.reduce((acc, r) => acc + r.priceNum, 0) / count;
    const diffPrice = room.priceNum - avgOtherPrice;
    const cheaperThanCount = otherRooms.filter((r) => room.priceNum < r.priceNum).length;
    const moreExpensiveCount = otherRooms.filter((r) => room.priceNum > r.priceNum).length;

    // 2. Score comparison
    const higherScoreCount = otherRooms.filter((r) => room.matchScore > r.matchScore).length;

    // 3. Amenities comparison
    const uniqueTags = room.tags.filter(
      (tag) => !otherRooms.some((o) => o.tags.includes(tag))
    );
    const missingTags = Array.from(
      new Set(otherRooms.flatMap((o) => o.tags))
    ).filter((tag) => !room.tags.includes(tag));

    // 4. Advantages (+) vs the other 4 rooms
    const advantages: string[] = [];
    if (cheaperThanCount === count) {
      advantages.push(
        `Giá thuê rẻ nhất nhóm: Rẻ hơn cả ${count} phòng còn lại, tiết kiệm ~${(Math.abs(diffPrice) / 1_000_000).toFixed(2).replace(/\.?0+$/, "")} triệu/tháng so với mức trung bình.`
      );
    } else if (cheaperThanCount > 0) {
      advantages.push(
        `Giá thuê cạnh tranh (${room.price}): Rẻ hơn ${cheaperThanCount}/${count} phòng còn lại trong danh sách đề xuất.`
      );
    }

    if (higherScoreCount === count) {
      advantages.push(
        `Điểm Rerank cao nhất (${(room.matchScore * 100).toFixed(1)}%): Dẫn đầu toàn bộ danh sách đề xuất về độ tương thích đa tiêu chí.`
      );
    } else if (higherScoreCount >= Math.floor(count / 2)) {
      advantages.push(
        `Điểm phù hợp tốt (${(room.matchScore * 100).toFixed(1)}%): Xếp trên ${higherScoreCount}/${count} phòng khác trong cùng đợt tìm kiếm.`
      );
    }

    if (explainBreakdown && explainBreakdown.factors.length > 0) {
      const bestFactor = [...explainBreakdown.factors].sort(
        (a, b) => b.fitPct - a.fitPct
      )[0];
      if (bestFactor && bestFactor.fitPct >= 60) {
        advantages.push(
          `Điểm mạnh nhất theo thuật toán: ${bestFactor.label} đạt ${bestFactor.fitPct}% (trọng số ${bestFactor.weightPct}%).`
        );
      }
    }

    if (uniqueTags.length > 0) {
      advantages.push(
        `Đặc điểm nổi bật riêng: Có ${uniqueTags.join(", ")} mà các phòng còn lại chưa ghi nhận.`
      );
    } else if (room.tags.length > 0) {
      advantages.push(`Đặc điểm & tiện ích: ${room.tags.join(", ")}.`);
    }

    advantages.push(`Địa chỉ cụ thể: ${room.address} (Khoảng cách: ${room.distance}).`);

    // 5. Disadvantages / Considerations (-) vs the other 4 rooms
    const considerations: string[] = [];
    if (moreExpensiveCount === count) {
      considerations.push(
        `Mức giá cao nhất nhóm: Cao hơn cả ${count} phòng còn lại (~${(diffPrice / 1_000_000).toFixed(2).replace(/\.?0+$/, "")} triệu/tháng so với trung bình).`
      );
    } else if (diffPrice > 200_000) {
      considerations.push(
        `Chi phí thuê: Cao hơn mức trung bình của các phòng còn lại khoảng ${(diffPrice / 1_000_000).toFixed(2).replace(/\.?0+$/, "")} triệu/tháng.`
      );
    }

    if (room.rank > 1 && rooms[0]) {
      considerations.push(
        `So với Phòng Top #1 (${rooms[0].price}): Điểm tổng thể thấp hơn (${(room.matchScore * 100).toFixed(1)}% so với ${(rooms[0].matchScore * 100).toFixed(1)}%).`
      );
    }

    if (explainBreakdown && explainBreakdown.weakLabels.length > 0) {
      considerations.push(
        `Tiêu chí điểm chưa cao (<40%): ${explainBreakdown.weakLabels.join(", ")} — cần kiểm tra kỹ khi đi xem thực tế.`
      );
    }

    if (missingTags.length > 0) {
      considerations.push(
        `So sánh tiện ích/nhãn: Một số phòng khác trong top có thêm ${missingTags.slice(0, 2).join(", ")}.`
      );
    }

    return {
      otherCount: count,
      advantages,
      considerations,
    };
  }, [room, rooms, explainBreakdown]);

  // Dynamic verification checklist tailored to this specific room's features
  const dynamicChecklist = useMemo(() => {
    if (!room) return [];
    const items: string[] = [];

    if (insights?.verification_checklist && insights.verification_checklist.length > 0 && (room.rank === 1 || room.id === insights.selected_top_1_id)) {
      items.push(...insights.verification_checklist);
    }

    if (room.priceNum > 0 && room.priceNum <= 3_500_000) {
      items.push(
        "Xác nhận đơn giá điện nước: Hỏi rõ giá điện (giá nhà nước hay 3.5k–4k/kWh), giá nước và phí dịch vụ/rác/wifi để tính tổng chi phí thực tế hàng tháng."
      );
    }

    const hasAc =
      room.tags.some((t) => /máy lạnh|điều hòa/i.test(t)) ||
      /máy lạnh|điều hòa/i.test(room.title);
    if (hasAc) {
      items.push(
        "Kiểm tra máy lạnh: Bật thử máy lạnh khi xem phòng để kiểm tra độ lạnh sâu, độ ồn và đời máy (có Inverter tiết kiệm điện không)."
      );
    }

    const hasMezzanine =
      room.tags.some((t) => /gác/i.test(t)) || /gác/i.test(room.title);
    if (hasMezzanine) {
      items.push(
        "Kiểm tra gác lửng: Kiểm tra chiều cao trần trên gác, độ chắc chắn của lan can/cầu thang và độ thoáng khí."
      );
    }

    items.push(
      `Kiểm tra đường đi từ ${room.address}: Quan sát hẻm vào có đèn chiếu sáng ban đêm, có bị ngập nước khi mưa lớn và giờ giấc đóng mở cổng.`
    );

    items.push(
      "Tiền cọc & hợp đồng: Xác nhận số tháng đặt cọc, thời hạn hợp đồng tối thiểu và điều khoản hoàn cọc rõ ràng bằng văn bản."
    );

    return items;
  }, [room]);

  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col flex-1 min-h-0 overflow-hidden">
      <div className="px-4 py-2 border-b border-[#E8E4DC] flex items-center justify-between bg-white shrink-0">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>4. Phân tích & So sánh của Agent</span>
        </h2>
        {rooms.length > 0 && (
          <span className="text-[10px] text-[#0F5F4A] bg-[#E6F4EE] font-bold px-2 py-0.5 rounded-full">
            Đối sánh {rooms.length} phòng
          </span>
        )}
      </div>

      {!room ? (
        <div className="flex-1 p-5 overflow-y-auto bg-[#FAFBF9] flex flex-col items-center justify-center text-center">
          <div className="w-12 h-12 rounded-2xl bg-[#E6F4EE] border border-[#0F5F4A]/20 flex items-center justify-center text-[#0F5F4A] mb-3 shadow-xs">
            <span className="material-symbols-outlined text-[24px]">psychology</span>
          </div>
          <h3 className="text-xs font-bold text-[#121E1A] mb-1">
            Chưa chọn phòng trọ
          </h3>
          <p className="text-[11px] text-[#6F7974] max-w-[270px] leading-relaxed mb-4">
            Bấm vào bất kỳ phòng nào trong danh sách hoặc trên bản đồ để xem chi tiết điểm Rerank, địa chỉ và so sánh ưu/nhược điểm.
          </p>
        </div>
      ) : (
        <div className="flex-1 p-3.5 overflow-y-auto space-y-3 text-xs bg-[#FAFBF9]">
          {/* AI Agent Decision Support (Dynamic MCDM) */}
          {insights && (room.rank === 1 || room.id === insights.selected_top_1_id) && (
            <div className="bg-gradient-to-r from-[#E6F4EE]/90 via-[#F0FDF8] to-white rounded-xl p-3.5 border border-[#0F5F4A]/25 shadow-2xs space-y-2">
              <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold text-[12px]">
                <span className="material-symbols-outlined text-[16px]">psychology</span>
                <span>Lý do lựa chọn Top 1 (Dynamic MCDM):</span>
              </div>
              <p className="text-[11px] text-[#121E1A] leading-relaxed">
                {insights.top_1_reason}
              </p>
              {insights.key_factors && insights.key_factors.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
                  <span className="text-[10px] text-[#6F7974] font-medium">Tiêu chí then chốt:</span>
                  {insights.key_factors.map((kf, idx) => (
                    <span key={idx} className="px-2 py-0.5 rounded-md bg-white border border-[#0F5F4A]/20 text-[#0F5F4A] text-[10px] font-bold shadow-2xs">
                      {kf}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Detailed Room Header Card */}
          <div className="bg-white rounded-xl p-3.5 border border-[#E8E4DC] shadow-2xs space-y-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-1.5 text-[#0F5F4A] font-bold min-w-0">
                <span className="text-[#FF6B4A] shrink-0 mt-0.5">
                  {room.rank === 1 ? "👑" : room.rank === 2 ? "🥈" : room.rank === 3 ? "🥉" : "📌"}
                </span>
                <span className="leading-snug text-[#121E1A] font-bold text-[12.5px]">
                  Phòng #{room.rank}: {room.title}
                </span>
              </div>
              <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-[#E6F4EE] text-[#0F5F4A] border border-[#0F5F4A]/20 shrink-0 whitespace-nowrap">
                Độ hợp: {(room.matchScore * 100).toFixed(1)}% ({room.matchScore})
              </span>
            </div>

            {/* Full Street Address */}
            <div className="flex items-start gap-1.5 text-[11px] text-[#334155] bg-[#F8FAFC] px-2.5 py-1.5 rounded-lg border border-[#E2E8F0]">
              <span className="material-symbols-outlined text-[15px] text-[#0F5F4A] shrink-0 mt-0.5">
                location_on
              </span>
              <div>
                <span className="font-semibold text-[#0F172A]">Địa chỉ: </span>
                <span>{room.address}</span>
              </div>
            </div>

            {/* Price, Distance, Tags & Link */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5 text-[11px] text-[#3F4944]">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>
                  <strong>Giá thuê:</strong>{" "}
                  <span className="text-[#0F5F4A] font-extrabold text-[12px]">{room.price}</span>
                </span>
                <span>•</span>
                <span>
                  <strong>Vị trí / Khoảng cách:</strong>{" "}
                  <span className="font-semibold text-[#0F172A]">
                    {/^\d/.test(room.distance) ? `~ ${room.distance}` : room.distance}
                  </span>
                </span>
              </div>

              <Link
                href={`/phong-tro/${encodeURIComponent(room.id)}`}
                className="inline-flex items-center gap-1 text-[10.5px] font-bold text-[#0F5F4A] hover:text-[#004635] underline"
              >
                <span>Xem chi tiết phòng</span>
                <span className="material-symbols-outlined text-[13px]">open_in_new</span>
              </Link>
            </div>

            {/* Tags */}
            {room.tags && room.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {room.tags.map((tag, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-0.5 rounded-md bg-[#E6F4EE]/70 text-[#0F5F4A] text-[10px] font-semibold border border-[#0F5F4A]/15"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Rerank Explain Match Breakdown Bars */}
            {explainBreakdown && explainBreakdown.factors.length > 0 && (
              <div className="pt-2 border-t border-[#F1F5F9] space-y-1.5">
                <div className="flex items-center justify-between text-[10.5px] font-bold text-[#334155]">
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px] text-[#0F5F4A]">
                      equalizer
                    </span>
                    <span>Chi tiết điểm chấm Rerank đa tiêu chí:</span>
                  </span>
                  <span className="text-[9.5px] font-normal text-[#64748B]">
                    Độ khớp từng tiêu chí (Trọng số)
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                  {explainBreakdown.factors.map((f) => (
                    <div
                      key={f.key}
                      className="bg-[#FAFBF9] border border-[#E8E4DC] rounded-lg px-2.5 py-1.5 space-y-1"
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-semibold text-[#1E293B] truncate">{f.label}</span>
                        <span className="font-bold text-[#0F5F4A] shrink-0">
                          {f.fitPct}%{" "}
                          <span className="text-[9px] font-normal text-[#64748B]">
                            (w={f.weightPct}%)
                          </span>
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-[#E2E8F0] rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            f.fitPct >= 70
                              ? "bg-[#0F5F4A]"
                              : f.fitPct >= 45
                              ? "bg-[#F59E0B]"
                              : "bg-[#EF4444]"
                          }`}
                          style={{ width: `${Math.max(6, Math.min(100, f.fitPct))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Comparison with the other 4 rooms */}
          {comparisonWithOtherRooms && (
            <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold text-[12px]">
                  <span className="material-symbols-outlined text-[16px] text-[#0F5F4A]">
                    compare_arrows
                  </span>
                  <span>So sánh với {comparisonWithOtherRooms.otherCount} phòng còn lại:</span>
                </div>
                <span className="text-[9px] bg-[#FAFBF9] border border-[#E8E4DC] px-2 py-0.5 rounded-md text-[#6F7974] font-medium">
                  Phòng #{room.rank} vs {comparisonWithOtherRooms.otherCount} phòng khác
                </span>
              </div>

              {/* Advantages (+) vs other 4 rooms */}
              <div className="bg-[#E6F4EE]/60 border border-[#0F5F4A]/15 rounded-lg p-2.5 space-y-1.5">
                <div className="text-[11px] font-bold text-[#0F5F4A] flex items-center gap-1">
                  <span className="text-[13px]">▲</span>
                  <span>Ưu điểm nổi bật của phòng này:</span>
                </div>
                <ul className="text-[11px] text-[#121E1A] space-y-1 pl-3.5 list-disc leading-relaxed">
                  {comparisonWithOtherRooms.advantages.map((adv, idx) => (
                    <li key={idx}>{adv}</li>
                  ))}
                </ul>
              </div>

              {/* Considerations / Disadvantages (-) vs other 4 rooms */}
              {comparisonWithOtherRooms.considerations.length > 0 && (
                <div className="bg-[#FEF3C7]/45 border border-[#FDE68A] rounded-lg p-2.5 space-y-1.5">
                  <div className="text-[11px] font-bold text-[#92400E] flex items-center gap-1">
                    <span className="text-[13px]">▼</span>
                    <span>Điểm hạn chế / Cần cân nhắc:</span>
                  </div>
                  <ul className="text-[11px] text-[#78350F] space-y-1 pl-3.5 list-disc leading-relaxed">
                    {comparisonWithOtherRooms.considerations.map((con, idx) => (
                      <li key={idx}>{con}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Backend AI Computed Trade-offs */}
              {insights?.trade_offs && insights.trade_offs.length > 0 && (room.rank === 1 || room.id === insights.selected_top_1_id) && (
                <div className="space-y-1.5 pt-1 border-t border-[#F1F5F9]">
                  <div className="text-[11px] font-bold text-[#0F5F4A] flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">balance</span>
                    <span>Phân tích đánh đổi (Trade-off Matrix từ AI):</span>
                  </div>
                  {insights.trade_offs.map((to, idx) => (
                    <div key={idx} className="bg-[#FAFBF9] rounded-lg p-2.5 border border-[#E8E4DC] text-[10.5px] space-y-1">
                      <div className="font-bold text-[#1E293B]">So với {to.compared_with}:</div>
                      <div className="text-[#15803D] flex items-start gap-1">
                        <span className="font-bold shrink-0">▲</span>
                        <span>{to.advantage}</span>
                      </div>
                      <div className="text-[#B45309] flex items-start gap-1">
                        <span className="font-bold shrink-0">▼</span>
                        <span>{to.disadvantage}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Dynamic Verification Checklist */}
          {dynamicChecklist.length > 0 && (
            <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-1.5">
              <div className="flex items-center gap-1.5 text-[#D97706] font-bold">
                <span className="material-symbols-outlined text-[15px]">verified_user</span>
                <span>Checklist lưu ý thực tế khi xem phòng này</span>
              </div>
              <ul className="text-[11px] text-[#3F4944] space-y-1 pl-1 leading-relaxed">
                {dynamicChecklist.map((item, idx) => (
                  <li key={idx} className="flex items-start gap-1.5">
                    <span className="material-symbols-outlined text-[13px] text-[#D97706] mt-0.5 shrink-0">
                      check_circle
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}