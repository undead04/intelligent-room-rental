"use client";

import { useMemo } from "react";
import QuickFilterPills from "@/app/tim-kiem-ai/_components/QuickFilterPills";
import RoomResultCard from "@/app/tim-kiem-ai/_components/RoomResultCard";
import type { RoomItem, UserPreferenceState } from "@/app/tim-kiem-ai/types";

interface RoomResultsPanelProps {
  rooms: RoomItem[];
  selectedRoomId: string;
  activeFilter: string;
  preferences?: UserPreferenceState | null;
  onSelectRoom: (roomId: string) => void;
  onSelectFilter: (filterId: string) => void;
}

export default function RoomResultsPanel({
  rooms,
  selectedRoomId,
  activeFilter,
  preferences,
  onSelectRoom,
  onSelectFilter,
}: RoomResultsPanelProps) {
  // Extract active search tags from AI preferences
  const searchTags = useMemo(() => {
    if (!preferences) return [];
    const tags: string[] = [];
    if (preferences.location_text) {
      tags.push(`📍 ${preferences.location_text}`);
    }
    if (preferences.max_price) {
      const priceTr = (preferences.max_price / 1_000_000).toFixed(1).replace(".0", "");
      tags.push(`💰 ≤ ${priceTr}tr`);
    }
    if (preferences.amenities && preferences.amenities.length > 0) {
      preferences.amenities.forEach((a) => {
        const clean = a.trim().toLowerCase();
        if (/^(aircon|ac)$|máy lạnh|điều hòa/i.test(clean)) tags.push("❄️ Máy lạnh");
        else if (/^mezzanine$|gác/i.test(clean)) tags.push("🪜 Gác lửng");
        else if (/^private_wc$|wc riêng|vệ sinh riêng/i.test(clean)) tags.push("🚿 WC riêng");
        else if (/^free_hours$|giờ giấc tự do|tự do/i.test(clean)) tags.push("🛵 Giờ tự do");
        else if (/^pet_allowed$|thú cưng|nuôi pet/i.test(clean)) tags.push("🐾 Nuôi thú cưng");
        else if (/^balcony$|ban công/i.test(clean)) tags.push("🌿 Ban công");
        else if (/^kitchen$|bếp/i.test(clean)) tags.push("🍳 Kệ bếp");
        else if (/^fridge$|tủ lạnh/i.test(clean)) tags.push("🧊 Tủ lạnh");
        else if (/^washing_machine$|máy giặt/i.test(clean)) tags.push("🧺 Máy giặt");
        else if (/^parking$|chỗ để xe|giữ xe/i.test(clean)) tags.push("🛵 Chỗ để xe");
        else if (/^security$|an ninh/i.test(clean)) tags.push("🛡️ An ninh");
        else tags.push(`✨ ${a}`);
      });
    }
    if (preferences.special_requirements && preferences.special_requirements.length > 0) {
      preferences.special_requirements.forEach((r) => {
        if (/giờ/i.test(r)) tags.push("🛵 Giờ tự do");
        else if (/thú cưng/i.test(r)) tags.push("🐾 Nuôi thú cưng");
        else tags.push(`🏷️ ${r}`);
      });
    }
    return Array.from(new Set(tags));
  }, [preferences]);

  // Client-side filtering & sorting of rooms
  const processedRooms = useMemo(() => {
    if (!rooms || rooms.length === 0) return [];

    switch (activeFilter) {
      case "price_asc":
        return [...rooms].sort((a, b) => a.priceNum - b.priceNum);
      case "score_desc":
        return [...rooms].sort((a, b) => b.matchScore - a.matchScore);
      case "has_ac": {
        const filtered = rooms.filter(
          (r) =>
            r.tags.some((t) => /máy lạnh|điều hòa/i.test(t)) ||
            /máy lạnh|điều hòa/i.test(r.title)
        );
        return filtered.length > 0 ? filtered : rooms;
      }
      case "has_mezzanine": {
        const filtered = rooms.filter(
          (r) =>
            r.tags.some((t) => /gác/i.test(t)) ||
            /gác/i.test(r.title)
        );
        return filtered.length > 0 ? filtered : rooms;
      }
      case "default":
      default:
        return rooms;
    }
  }, [rooms, activeFilter]);

  const hasSpecificFilter = activeFilter !== "default";
  const filterMatched =
    activeFilter === "has_ac"
      ? rooms.some((r) => r.tags.some((t) => /máy lạnh|điều hòa/i.test(t)) || /máy lạnh|điều hòa/i.test(r.title))
      : activeFilter === "has_mezzanine"
      ? rooms.some((r) => r.tags.some((t) => /gác/i.test(t)) || /gác/i.test(r.title))
      : true;

  return (
    <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[520px] lg:h-full min-h-0 overflow-hidden">
      {/* Header & Quick Filters */}
      <div className="p-3 px-4 border-b border-[#E8E4DC] space-y-2 bg-white shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
            <span>2. Kết quả danh sách phòng</span>
          </h2>
          <span
            className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
              rooms.length > 0
                ? "text-[#0F5F4A] bg-[#E6F4EE]"
                : "text-[#6F7974] bg-[#F1F5F9]"
            }`}
          >
            {rooms.length > 0 ? `${processedRooms.length} phòng` : "Chờ yêu cầu"}
          </span>
        </div>
        <p className="text-[11px] text-[#6F7974] font-medium">
          {rooms.length > 0 ? (
            <>
              Tìm được <span className="text-[#121E1A] font-bold">{rooms.length} phòng</span> phù hợp với yêu cầu của bạn.
            </>
          ) : (
            "Kết quả đề xuất sẽ hiển thị sau khi AI Agent phân tích tiêu chí của bạn."
          )}
        </p>

        {/* Filter Pills & Active Search Criteria Row */}
        {rooms.length > 0 && (
          <QuickFilterPills
            activeFilter={activeFilter}
            onSelect={onSelectFilter}
            searchTags={searchTags}
          />
        )}
      </div>

      {/* Filter notice if none matched specific filter */}
      {!filterMatched && (
        <div className="mx-3 mt-2 px-3 py-1.5 bg-[#FFFBEB] border border-[#FDE68A] text-[#92400E] text-[11px] rounded-lg flex items-center justify-between">
          <span>Không có phòng nào gắn nhãn này trong top 5. Đang hiển thị danh sách gốc.</span>
          <button
            onClick={() => onSelectFilter("default")}
            className="text-[10px] underline font-bold ml-2 cursor-pointer"
          >
            Về mặc định
          </button>
        </div>
      )}

      {/* Room Cards Scroll Area or Empty State */}
      {rooms.length > 0 ? (
        <div className="flex-1 p-3.5 overflow-y-auto space-y-3.5 bg-[#FAFBF9]">
          {processedRooms.map((room) => (
            <RoomResultCard
              key={room.id}
              room={room}
              isSelected={selectedRoomId === room.id}
              onSelect={onSelectRoom}
            />
          ))}
        </div>
      ) : (
        <div className="flex-1 p-5 overflow-y-auto bg-[#FAFBF9] flex flex-col items-center justify-center text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#E6F4EE] border border-[#0F5F4A]/20 flex items-center justify-center text-[#0F5F4A] mb-3 shadow-xs">
            <span className="material-symbols-outlined text-[28px]">search_spark</span>
          </div>
          <h3 className="text-xs font-bold text-[#121E1A] mb-1">
            Chưa có danh sách phòng
          </h3>
          <p className="text-[11px] text-[#6F7974] max-w-[280px] leading-relaxed mb-4">
            Hãy nhập yêu cầu của bạn ở khung chat bên trái (hoặc bấm vào các gợi ý) để AI phân tích và đề xuất danh sách phòng trọ tốt nhất.
          </p>
          <div className="w-full max-w-[290px] p-3 rounded-xl bg-white border border-[#E8E4DC] text-left text-[11px] space-y-1.5 shadow-2xs">
            <div className="font-semibold text-[#0F5F4A] flex items-center gap-1 text-[11px]">
              <span className="material-symbols-outlined text-[15px]">tips_and_updates</span>
              <span>Mẹo tìm phòng thông minh:</span>
            </div>
            <p className="text-[#4A5550] text-[10px] leading-relaxed">
              Bạn có thể nói tự nhiên: <em>&quot;Tìm phòng gần UIT dưới 5 triệu có máy lạnh, gác lửng, giờ giấc tự do&quot;</em>.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}