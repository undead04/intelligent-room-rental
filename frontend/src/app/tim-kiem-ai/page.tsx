"use client";

import SiteLayout from "@/components/SiteLayout";
import AgentInsightPanel from "@/app/tim-kiem-ai/_components/AgentInsightPanel";
import AiChatPanel from "@/app/tim-kiem-ai/_components/AiChatPanel";
import AiWorkspaceHeader from "@/app/tim-kiem-ai/_components/AiWorkspaceHeader";
import RoomMapPanel from "@/app/tim-kiem-ai/_components/RoomMapPanel";
import RoomResultsPanel from "@/app/tim-kiem-ai/_components/RoomResultsPanel";
import { useAiChat } from "@/app/tim-kiem-ai/_hooks/useAiChat";
import BackendConnectionError from "@/components/BackendConnectionError";

export default function AIChatWorkspacePage() {

  const {
    messages,
    inputValue,
    setInputValue,
    isTyping,
    sendMessage,
    rooms,
    insights,
    preferences,
    selectedRoomId,
    setSelectedRoomId,
    connectionError,
    resetConversation,
    hasActiveSession,
  } = useAiChat();

  const selectedRoom = rooms.find((room) => room.id === selectedRoomId) || rooms[0] || null;

  return (
    <SiteLayout
      hideFooter
      className="bg-[#F8FAF8] text-[#121E1A] font-sans antialiased h-screen flex flex-col overflow-hidden"
    >
      {/* BREADCRUMB & CONTEXT HEADER */}
      <AiWorkspaceHeader
        onResetConversation={resetConversation}
        hasActiveSession={hasActiveSession}
      />


      {/* MAIN WORKSPACE LAYOUT (Viewport Fit: No whole-page scroll on desktop) */}
      <main className="flex-1 min-h-0 px-3 sm:px-4 lg:px-6 pb-3 pt-1 max-w-[1600px] w-full mx-auto flex flex-col overflow-y-auto lg:overflow-hidden">
        {connectionError && (
          <BackendConnectionError
            message={connectionError}
            variant="banner"
            serviceName="AI Agent Microservice"
            port="8001"
            className="mb-2 shrink-0"
            onRetry={() => sendMessage(undefined, inputValue || "Tìm phòng gần UIT dưới 5 triệu có máy lạnh")}
          />
        )}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5 flex-1 min-h-0 h-auto lg:h-full">
          {/* COLUMN 1: CHAT / NHẬP YÊU CẦU (Col span 4) */}
          <AiChatPanel
            messages={messages}
            isTyping={isTyping}
            inputValue={inputValue}
            onInputChange={setInputValue}
            onSubmit={sendMessage}
            onSelectQuestion={(question) => {
              if (question.includes("Tùy chỉnh tiêu chí") || question.startsWith("✏️")) {
                setInputValue("Tôi muốn điều chỉnh: ");
                setTimeout(() => {
                  const inputEl = document.querySelector('input[type="text"]') as HTMLInputElement;
                  if (inputEl) {
                    inputEl.focus();
                    inputEl.setSelectionRange(inputEl.value.length, inputEl.value.length);
                  }
                }, 50);
              } else {
                sendMessage(undefined, question);
              }
            }}
          />

          {/* COLUMN 2: KẾT QUẢ DANH SÁCH PHÒNG (Col span 4) */}
          <RoomResultsPanel
            rooms={rooms}
            selectedRoomId={selectedRoomId}
            preferences={preferences}
            onSelectRoom={setSelectedRoomId}
          />

          {/* COLUMN 3: BẢN ĐỒ VỊ TRÍ & PHÂN TÍCH AGENT (Col span 4) */}
          <section className="lg:col-span-4 flex flex-col gap-3 h-[600px] lg:h-full min-h-0 overflow-hidden">
            {/* TOP CARD: 3. Bản đồ vị trí (42% height on desktop) */}
            <div className="h-[220px] lg:h-[42%] shrink-0">
              <RoomMapPanel
                rooms={rooms}
                selectedRoom={selectedRoom}
                locationText={preferences?.location_text}
                landmarkLat={preferences?.lat}
                landmarkLng={preferences?.lng}
                onSelectRoom={setSelectedRoomId}
              />
            </div>

            {/* BOTTOM CARD: 4. Phân tích & giải thích của Agent (fill remaining space) */}
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
              <AgentInsightPanel
                room={selectedRoom}
                insights={insights}
                rooms={rooms}
              />
            </div>
          </section>
        </div>
      </main>
    </SiteLayout>
  );
}