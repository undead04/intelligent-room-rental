"use client";

import { useState } from "react";
import SiteLayout from "@/components/SiteLayout";
import AgentInsightPanel from "@/app/tim-kiem-ai/_components/AgentInsightPanel";
import AiChatPanel from "@/app/tim-kiem-ai/_components/AiChatPanel";
import AiWorkspaceHeader from "@/app/tim-kiem-ai/_components/AiWorkspaceHeader";
import RoomMapPanel from "@/app/tim-kiem-ai/_components/RoomMapPanel";
import RoomResultsPanel from "@/app/tim-kiem-ai/_components/RoomResultsPanel";
import {
  DEFAULT_FILTER_ID,
  DEFAULT_ROOM_ID,
  SAMPLE_ROOMS,
} from "@/app/tim-kiem-ai/_constants/aiWorkspace";
import { useAiChat } from "@/app/tim-kiem-ai/_hooks/useAiChat";

export default function AIChatWorkspacePage() {
  const [selectedRoomId, setSelectedRoomId] = useState<string>(DEFAULT_ROOM_ID);
  const [activeFilter, setActiveFilter] = useState<string>(DEFAULT_FILTER_ID);

  const { messages, inputValue, setInputValue, isTyping, sendMessage } = useAiChat();

  const rooms = SAMPLE_ROOMS;
  const selectedRoom = rooms.find((room) => room.id === selectedRoomId) || rooms[0];

  return (
    <SiteLayout className="bg-[#F8FAF8] text-[#121E1A] font-sans antialiased">
      {/* BREADCRUMB & CONTEXT HEADER */}
      <AiWorkspaceHeader />

      {/* MAIN WORKSPACE LAYOUT (Strict 3-Column / 4-Panel Layout matching Stitch Design) */}
      <main className="flex-1 px-4 lg:px-8 py-3 max-w-[1500px] w-full mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-auto lg:h-[720px]">
          {/* COLUMN 1: CHAT / NHẬP YÊU CẦU (Col span 4) */}
          <AiChatPanel
            messages={messages}
            isTyping={isTyping}
            inputValue={inputValue}
            onInputChange={setInputValue}
            onSubmit={sendMessage}
          />

          {/* COLUMN 2: KẾT QUẢ DANH SÁCH PHÒNG (Col span 4) */}
          <RoomResultsPanel
            rooms={rooms}
            selectedRoomId={selectedRoomId}
            activeFilter={activeFilter}
            onSelectRoom={setSelectedRoomId}
            onSelectFilter={setActiveFilter}
          />

          {/* COLUMN 3: BẢN ĐỒ VỊ TRÍ & PHÂN TÍCH AGENT (Col span 4) */}
          <section className="lg:col-span-4 flex flex-col gap-4 h-[750px] lg:h-full overflow-hidden">
            {/* TOP CARD: 3. Bản đồ vị trí (48% height) */}
            <RoomMapPanel
              rooms={rooms}
              selectedRoom={selectedRoom}
              onSelectRoom={setSelectedRoomId}
            />

            {/* BOTTOM CARD: 4. Phân tích & giải thích của Agent (52% height) */}
            <AgentInsightPanel room={selectedRoom} />
          </section>
        </div>
      </main>

    </SiteLayout>
  );
}