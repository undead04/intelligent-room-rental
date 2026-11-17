"use client";

import { useEffect, useMemo, useRef } from "react";
import RoomResultCard from "@/app/tim-kiem-ai/_components/RoomResultCard";
import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomResultsPanelProps {
  rooms: RoomItem[];
  selectedRoomId: string;
  onSelectRoom: (roomId: string) => void;
  currentPage?: number;
  totalPages?: number;
  totalRooms?: number;
  isPaging?: boolean;
  onPageChange?: (page: number) => void;
}

function getCompactPageRange(current: number, total: number): Array<number | "..."> {
  if (total <= 5) {
    return Array.from({ length: total }, (_, idx) => idx + 1);
  }
  const pages = new Set<number>([1, total, current]);
  if (current - 1 >= 1) pages.add(current - 1);
  if (current + 1 <= total) pages.add(current + 1);

  const sorted = Array.from(pages).sort((a, b) => a - b);
  const result: Array<number | "..."> = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) {
      result.push("...");
    }
    result.push(sorted[i]);
  }
  return result;
}

export default function RoomResultsPanel({
  rooms,
  selectedRoomId,
  onSelectRoom,
  currentPage = 1,
  totalPages = 1,
  totalRooms,
  isPaging = false,
  onPageChange,
}: RoomResultsPanelProps) {
  const listContainerRef = useRef<HTMLDivElement | null>(null);

  // Client-side filtering & sorting of rooms
  const processedRooms = useMemo(() => {
    if (!rooms || rooms.length === 0) return [];

    return rooms;
  }, [rooms]);

  const effectiveTotalRooms = totalRooms && totalRooms > 0 ? totalRooms : processedRooms.length;
  const effectiveTotalPages = totalPages && totalPages > 0 ? totalPages : processedRooms.length > 0 ? 1 : 0;
  const pageItems = useMemo(
    () => (effectiveTotalPages > 1 ? getCompactPageRange(currentPage, effectiveTotalPages) : []),
    [currentPage, effectiveTotalPages]
  );

  useEffect(() => {
    if (listContainerRef.current) {
      listContainerRef.current.scrollTop = 0;
    }
  }, [currentPage, rooms]);

  return (
    <section className="lg:col-span-4 bg-white rounded-2xl border border-[#D8E4DF] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[520px] lg:h-full min-h-0 overflow-hidden">
      {/* Header đồng nhất 44px */}
      <div className="h-11 px-4 border-b border-[#E8E4DC] flex items-center justify-between gap-2 bg-white shrink-0">
        <h2 className="text-[13.5px] font-bold text-[#0F5F4A] flex items-center gap-2 whitespace-nowrap">
          <span className="w-2 h-2 rounded-full bg-[#0F5F4A] shrink-0"></span>
          <span>2. Kết quả phòng</span>
        </h2>
        <span
          className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full whitespace-nowrap shrink-0 ${
            rooms.length > 0
              ? "text-[#0F5F4A] bg-[#E6F4EE] border border-[#0F5F4A]/15"
              : "text-[#6F7974] bg-[#F5F2EB] border border-[#E8E4DC]"
          }`}
        >
          {rooms.length > 0 ? `${effectiveTotalRooms} phòng phù hợp` : "Chờ yêu cầu"}
        </span>
      </div>

      {/* Sub-bar trạng thái hiển thị khi có kết quả */}
      {rooms.length > 0 && (
        <div className="px-4 py-1.5 bg-[#FAF8F4] border-b border-[#E8E4DC] flex items-center justify-between gap-2 text-[11px] text-[#4A5550] shrink-0">
          <span>
            Top <strong className="text-[#121E1A]">{processedRooms.length}</strong> /{" "}
            <strong className="text-[#121E1A]">{effectiveTotalRooms}</strong> phòng
          </span>
          {effectiveTotalPages > 1 && (
            <span className="text-[#0F5F4A] font-semibold">
              Trang {currentPage}/{effectiveTotalPages}
            </span>
          )}
        </div>
      )}

      {/* Room Cards Scroll Area or Empty State */}
      {rooms.length > 0 ? (
        <div
          ref={listContainerRef}
          className={`flex-1 p-3.5 overflow-y-auto space-y-3 bg-[#FAF8F4]/55 transition-opacity ${
            isPaging ? "opacity-60 pointer-events-none" : "opacity-100"
          }`}
        >
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
        <div className="flex-1 p-6 overflow-y-auto bg-[#FAF8F4]/55 flex flex-col items-center justify-center text-center">
          <div className="w-14 h-14 rounded-2xl bg-[#E6F4EE] border border-[#0F5F4A]/20 flex items-center justify-center text-[#0F5F4A] mb-3.5 shadow-2xs">
            <span className="material-symbols-outlined text-[28px]">manage_search</span>
          </div>
          <h3 className="text-sm font-bold text-[#121E1A] mb-1.5">
            Chưa có danh sách phòng
          </h3>
          <p className="text-xs text-[#4A5550] max-w-[300px] leading-relaxed mb-4">
            Nhập yêu cầu của bạn ở khung chat bên trái hoặc chọn nhanh một gợi ý để AI phân tích và xếp hạng các phòng trọ phù hợp nhất.
          </p>
          <div className="w-full max-w-[310px] p-3.5 rounded-xl bg-white border border-[#D8E4DF] text-left space-y-1.5 shadow-2xs">
            <div className="font-semibold text-[#0F5F4A] flex items-center gap-1.5 text-xs">
              <span className="material-symbols-outlined text-[16px]">tips_and_updates</span>
              <span>Mẹo tìm phòng hiệu quả</span>
            </div>
            <p className="text-[#4A5550] text-[11.5px] leading-relaxed">
              Mô tả tự nhiên theo nhu cầu: <em>&quot;Tìm phòng gần UIT dưới 4 triệu có máy lạnh, gác lửng, giờ tự do&quot;</em>. AI sẽ lọc Top 5 phòng tối ưu cho mỗi trang.
            </p>
          </div>
        </div>
      )}

      {/* Compact Pagination Footer */}
      {rooms.length > 0 && effectiveTotalPages > 1 && onPageChange && (
        <div className="px-3.5 py-2 border-t border-[#E8E4DC] bg-white shrink-0 flex items-center justify-between gap-2">
          <span className="text-[11px] text-[#6F7974] font-medium whitespace-nowrap">
            Trang <strong className="text-[#121E1A]">{currentPage}</strong>/{effectiveTotalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => onPageChange(currentPage - 1)}
              disabled={isPaging || currentPage <= 1}
              aria-label="Trang trước"
              className="h-7 w-7 rounded-lg border border-[#E8E4DC] bg-white text-[#121E1A] flex items-center justify-center text-xs font-semibold transition hover:border-[#0F5F4A] hover:text-[#0F5F4A] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ‹
            </button>
            {pageItems.map((item, idx) =>
              item === "..." ? (
                <span key={`ellipsis-${idx}`} className="px-1 text-[11px] text-[#6F7974] select-none">
                  ...
                </span>
              ) : (
                <button
                  key={item}
                  type="button"
                  onClick={() => onPageChange(item)}
                  disabled={isPaging}
                  className={`h-7 min-w-[28px] px-2 rounded-lg text-[11px] font-bold transition ${
                    item === currentPage
                      ? "bg-[#0F5F4A] text-white shadow-xs"
                      : "border border-[#E8E4DC] bg-white text-[#4A5550] hover:border-[#0F5F4A] hover:text-[#0F5F4A]"
                  } disabled:opacity-60`}
                >
                  {item}
                </button>
              )
            )}
            <button
              type="button"
              onClick={() => onPageChange(currentPage + 1)}
              disabled={isPaging || currentPage >= effectiveTotalPages}
              aria-label="Trang sau"
              className="h-7 w-7 rounded-lg border border-[#E8E4DC] bg-white text-[#121E1A] flex items-center justify-center text-xs font-semibold transition hover:border-[#0F5F4A] hover:text-[#0F5F4A] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ›
            </button>
          </div>
        </div>
      )}
    </section>
  );
}