import Link from "next/link";
import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomResultCardProps {
  room: RoomItem;
  isSelected: boolean;
  onSelect: (roomId: string) => void;
}

export default function RoomResultCard({ room, isSelected, onSelect }: RoomResultCardProps) {
  const areaTag = room.tags.find((tag) => /^\d+(\.\d+)?\s*(m²|m2)$/i.test(tag) || tag.includes("m²") || tag.includes("m2"));
  const displayTags = areaTag ? room.tags.filter((t) => t !== areaTag) : room.tags;

  return (
    <article
      onClick={() => onSelect(room.id)}
      className={`p-3 rounded-2xl border transition bg-white group cursor-pointer ${isSelected
        ? "border-2 border-[#0F5F4A] shadow-md ring-2 ring-[#0F5F4A]/10"
        : room.rank === 1
          ? "border-2 border-[#0F5F4A]/30 hover:border-[#0F5F4A] hover:shadow-md"
          : "border border-[#E8E4DC] hover:border-[#0F5F4A]/60 hover:shadow-md"
        }`}
    >
      <div className="flex gap-3">
        {/* Thumbnail + Photo counter */}
        <div className="relative w-24 h-24 sm:w-[100px] sm:h-[104px] rounded-xl overflow-hidden shrink-0 bg-[#F5F2EB] border border-[#E8E4DC]/60">
          <img
            src={room.image}
            alt={room.title}
            className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
          />
          <span className="absolute bottom-1.5 left-1.5 bg-[#121E1A]/75 backdrop-blur-xs text-white text-[10px] font-semibold px-1.5 py-0.5 rounded-md flex items-center gap-1">
            <span className="material-symbols-outlined text-[11px]">photo_camera</span>
            <span>{room.photoCount}</span>
          </span>
        </div>

        {/* Information Details */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-1.5 mb-1.5">
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wide uppercase whitespace-nowrap ${
                  room.rank === 1
                    ? "bg-[#0F5F4A] text-white"
                    : "bg-[#E6F4EE] text-[#0F5F4A] border border-[#0F5F4A]/20"
                }`}
              >
                {room.rankText}
              </span>
              <span className="text-[10.5px] font-bold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full border border-[#0F5F4A]/20 flex items-center gap-1 whitespace-nowrap shrink-0">
                <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
                <span>Match {Math.round(room.matchScore <= 1 ? room.matchScore * 100 : room.matchScore)}%</span>
              </span>
            </div>

            <h3
              className="font-bold text-[13px] text-[#121E1A] line-clamp-2 leading-snug group-hover:text-[#0F5F4A] transition-colors"
              title={room.title}
            >
              {room.title}
            </h3>

            <div className="flex items-baseline gap-1.5 mt-1 min-w-0">
              <span className="text-[15px] font-extrabold text-[#D95330] shrink-0">
                {room.price.replace(/\s*\/\s*(tháng|thang|month)\s*$/i, "")}
                <span className="text-[11px] font-medium text-[#6F7974]">/tháng</span>
              </span>
              {areaTag && (
                <>
                  <span className="text-[#D8E4DF]">·</span>
                  <span className="text-xs font-semibold text-[#4A5550] shrink-0">
                    {areaTag}
                  </span>
                </>
              )}
            </div>

            <p className="text-[11px] text-[#4A5550] truncate mt-1 flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px] text-[#0F5F4A] shrink-0">location_on</span>
              <span className="truncate">{room.address}</span>
            </p>

            <div className="text-[11px] font-semibold text-[#0F5F4A] mt-0.5 flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px] shrink-0">near_me</span>
              <span className="truncate">{room.distance}</span>
            </div>
          </div>

          {/* Tags */}
          {displayTags.length > 0 && (
            <div className="flex items-center gap-1.5 mt-1.5 text-[10.5px] text-[#4A5550] font-medium flex-wrap">
              {displayTags.slice(0, 4).map((tag) => (
                <span key={tag} className="px-2 py-0.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-md">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center justify-end gap-2 mt-2.5 pt-2 border-t border-[#F5F2EB]">
        <Link
          href={`/phong-tro/${room.id}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(event) => event.stopPropagation()}
          className="px-3.5 py-1.5 text-[11.5px] font-bold text-white bg-[#0F5F4A] hover:bg-[#0B4A39] rounded-full transition shadow-2xs inline-flex items-center gap-1"
        >
          <span>Xem chi tiết</span>
          <span className="material-symbols-outlined text-[13px]">open_in_new</span>
        </Link>
      </div>
    </article>
  );
}