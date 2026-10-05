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
    <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[650px] lg:h-full overflow-hidden">
      {/* Header & Quick Filters */}
      <div className="p-3.5 px-4 border-b border-[#E8E4DC] space-y-2.5 bg-white">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
            <span>2. Kết quả danh sách phòng</span>
          </h2>
          <span className="text-[11px] font-bold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full">
            {rooms.length} phòng
          </span>
        </div>
        <p className="text-[11px] text-[#6F7974] font-medium">
          Tìm được <span className="text-[#121E1A] font-bold">{rooms.length} phòng</span> phù hợp với yêu cầu của bạn.
        </p>

        {/* Filter Pills Row */}
        <QuickFilterPills activeFilter={activeFilter} onSelect={onSelectFilter} />
      </div>

      {/* Room Cards Scroll Area */}
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
    </section>
  );
}