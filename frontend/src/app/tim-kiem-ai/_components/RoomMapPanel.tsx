import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface RoomMapPanelProps {
  rooms: RoomItem[];
  selectedRoom: RoomItem;
  onSelectRoom: (roomId: string) => void;
}

export default function RoomMapPanel({
  rooms,
  selectedRoom,
  onSelectRoom,
}: RoomMapPanelProps) {
  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[48%] overflow-hidden">
      <div className="px-4 py-2.5 border-b border-[#E8E4DC] flex items-center justify-between bg-white">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>3. Bản đồ vị trí</span>
        </h2>
        <span className="text-[10px] bg-[#E6F4EE] text-[#0F5F4A] px-2.5 py-0.5 rounded-full font-bold">
          Bán kính 1.5 km
        </span>
      </div>

      {/* Stylized Interactive Map Area */}
      <div className="flex-1 relative bg-[#F1F5F9] overflow-hidden flex items-center justify-center">
        {/* Map Grid Background Pattern */}
        <div
          className="absolute inset-0 opacity-80"
          style={{
            backgroundImage: `
              radial-gradient(#CBD5E1 1.2px, transparent 1.2px),
              linear-gradient(to right, rgba(226,232,240,0.6) 1px, transparent 1px),
              linear-gradient(to bottom, rgba(226,232,240,0.6) 1px, transparent 1px)
            `,
            backgroundSize: "24px 24px, 48px 48px, 48px 48px",
          }}
        />

        {/* Map road network graphic elements */}
        <svg className="absolute inset-0 w-full h-full opacity-60 pointer-events-none" xmlns="http://www.w3.org/2000/svg">
          <line stroke="#cbd5e1" strokeLinecap="round" strokeWidth="4" x1="0" x2="100%" y1="40" y2="160" />
          <line stroke="#e2e8f0" strokeWidth="3" x1="20%" x2="60%" y1="0" y2="100%" />
          <line stroke="#fcd34d" strokeDasharray="4,4" strokeWidth="3" x1="0" x2="100%" y1="180" y2="70" />
          <line stroke="#a7f3d0" strokeWidth="2" x1="75%" x2="70%" y1="0" y2="100%" />
        </svg>

        {/* UIT Circle Radius (Translucent target ring in Homigo emerald) */}
        <div className="absolute w-44 h-44 rounded-full bg-[#0F5F4A]/10 border-2 border-[#0F5F4A]/30 flex items-center justify-center animate-pulse pointer-events-none"></div>

        {/* UIT Center Landmark Pin */}
        <div className="relative z-10 flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-[#0F5F4A] text-white flex items-center justify-center shadow-lg border-2 border-white">
            <span className="material-symbols-outlined text-[20px]">school</span>
          </div>
          <span className="mt-1 px-2.5 py-0.5 bg-[#004635] text-white text-[10px] font-black rounded-full shadow-xs tracking-wider">
            UIT
          </span>
        </div>

        {/* Pins for Rooms */}
        {rooms.map((room) => (
          <div
            key={room.id}
            onClick={() => onSelectRoom(room.id)}
            style={{ top: `${room.latPercent}%`, left: `${room.lngPercent}%` }}
            className={`absolute z-20 flex flex-col items-center cursor-pointer transition-transform ${
              selectedRoom.id === room.id ? "scale-125 z-30" : "hover:scale-110"
            }`}
            title={`${room.rankText}: ${room.price} - ${room.distance}`}
          >
            <div
              className={`px-2 py-0.5 rounded-full text-[10px] font-bold shadow-md border-2 border-white flex items-center gap-1 ${
                selectedRoom.id === room.id
                  ? "bg-[#FF6B4A] text-white ring-2 ring-[#FF6B4A]/50"
                  : "bg-[#0F5F4A] text-white"
              }`}
            >
              <span>#{room.rank}</span>
              <span>{room.priceNum}tr</span>
            </div>
            <div
              className={`w-2 h-2 rotate-45 -mt-1 ${
                selectedRoom.id === room.id ? "bg-[#FF6B4A]" : "bg-[#0F5F4A]"
              }`}
            ></div>
          </div>
        ))}

        {/* Distance pill at bottom of map */}
        <div className="absolute bottom-2.5 bg-white/95 backdrop-blur-xs border border-[#E8E4DC] text-[#121E1A] text-[10px] font-bold px-3 py-1 rounded-full shadow-sm flex items-center gap-1.5 z-20">
          <span className="text-[#0F5F4A]">📍</span>
          <span>Khoảng cách tới UIT: ~ {selectedRoom.distance}</span>
        </div>

        {/* Map UI Zoom controls on right */}
        <div className="absolute right-2.5 top-2.5 z-20 flex flex-col bg-white rounded-lg shadow-sm border border-[#E8E4DC] overflow-hidden text-xs">
          <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold border-b border-[#E8E4DC] transition">
            +
          </button>
          <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold transition">
            -
          </button>
        </div>

        {/* Location re-center target button */}
        <div className="absolute right-2.5 bottom-2.5 z-20 bg-white rounded-lg shadow-sm border border-[#E8E4DC]">
          <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#0F5F4A] transition" title="Định vị UIT">
            <span className="material-symbols-outlined text-[16px]">my_location</span>
          </button>
        </div>
      </div>
    </div>
  );
}