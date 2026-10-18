import QuickFilterPills from "@/app/tim-kiem-ai/_components/QuickFilterPills";
import RoomResultCard from "@/app/tim-kiem-ai/_components/RoomResultCard";
import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomResultsPanelProps {
  rooms: RoomItem[];
  selectedRoomId: string;
  activeFilter: string;
  onSelectRoom: (roomId: string) => void;
  onSelectFilter: (filterId: string) => void;
}

export default function RoomResultsPanel({
  rooms,
  selectedRoomId,
  activeFilter,
  onSelectRoom,
  onSelectFilter,
}: RoomResultsPanelProps) {
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
            {rooms.length > 0 ? `${rooms.length} phòng` : "Chờ yêu cầu"}
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

        {/* Filter Pills Row */}
        {rooms.length > 0 && (
          <QuickFilterPills activeFilter={activeFilter} onSelect={onSelectFilter} />
        )}
      </div>

      {/* Room Cards Scroll Area or Empty State */}
      {rooms.length > 0 ? (
        <div className="flex-1 p-3.5 overflow-y-auto space-y-3.5 bg-[#FAFBF9]">
          {rooms.map((room) => (
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