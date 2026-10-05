import Link from "next/link";
import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomResultCardProps {
  room: RoomItem;
  isSelected: boolean;
  onSelect: (roomId: string) => void;
}

export default function RoomResultCard({ room, isSelected, onSelect }: RoomResultCardProps) {
  return (
    <article
      onClick={() => onSelect(room.id)}
      className={`p-3 rounded-2xl border transition bg-white group cursor-pointer ${
        isSelected
          ? "border-2 border-[#0F5F4A] shadow-md ring-2 ring-[#0F5F4A]/10"
          : room.rank === 1
          ? "border-2 border-[#0F5F4A]/30 hover:border-[#0F5F4A] hover:shadow-md"
          : "border border-[#E8E4DC] hover:border-[#0F5F4A]/60 hover:shadow-md"
      }`}
    >
      <div className="flex gap-3">
        {/* Thumbnail + Photo counter */}
        <div className="relative w-28 h-28 rounded-xl overflow-hidden shrink-0 bg-slate-100">
          <img
            src={room.image}
            alt={room.title}
            className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
          />
          <span className="absolute bottom-1.5 left-1.5 bg-black/60 backdrop-blur-xs text-white text-[9px] font-bold px-1.5 py-0.5 rounded flex items-center gap-1">
            📷 {room.photoCount}
          </span>
        </div>

        {/* Information Details */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between gap-1 mb-1">
              <span
                className={`text-[9px] font-extrabold px-2 py-0.5 rounded-full tracking-wide uppercase ${
                  room.rank === 1
                    ? "bg-[#0F5F4A] text-white"
                    : "bg-[#0F5F4A]/80 text-white"
                }`}
              >
                {room.rankText}
              </span>
              <span className="text-[10px] font-bold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full border border-[#0F5F4A]/20 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
                <span>Match {room.matchScore}%</span>
              </span>
            </div>

            <h3
              className="font-bold text-xs text-[#121E1A] truncate leading-snug group-hover:text-[#0F5F4A] transition-colors"
              title={room.title}
            >
              {room.title}
            </h3>

            <div className="text-sm font-extrabold text-[#FF6B4A] mt-0.5">
              {room.price}
              <span className="text-[10px] font-normal text-[#6F7974]">/tháng</span>
            </div>

            <p className="text-[10px] text-[#6F7974] truncate mt-0.5 flex items-center gap-1">
              <span className="material-symbols-outlined text-[13px] text-[#0F5F4A]">location_on</span>
              <span>{room.address}</span>
            </p>

            <div className="text-[10px] font-semibold text-[#0F5F4A] mt-0.5 flex items-center gap-1">
              <span>📍 {room.distance}</span>
            </div>
          </div>

          {/* Tags */}
          <div className="flex items-center gap-1.5 mt-1 text-[9px] text-[#3F4944] font-medium flex-wrap">
            {room.tags.map((tag) => (
              <span key={tag} className="px-1.5 py-0.5 bg-[#FAFBF9] border border-[#E8E4DC] rounded">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t border-[#F1F5F9]">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onSelect(room.id);
          }}
          className="px-3 py-1.5 text-[11px] font-bold text-[#0F5F4A] hover:bg-[#E6F4EE] border border-[#0F5F4A]/30 rounded-full transition"
        >
          So sánh
        </button>
        <Link
          href={`/phong-tro/${room.id}`}
          onClick={(event) => event.stopPropagation()}
          className="px-4 py-1.5 text-[11px] font-bold text-white bg-[#0F5F4A] hover:bg-[#004635] rounded-full transition shadow-xs"
        >
          Xem chi tiết
        </Link>
      </div>
    </article>
  );
}