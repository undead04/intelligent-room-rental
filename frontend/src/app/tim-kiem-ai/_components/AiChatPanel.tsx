import ChatMessageItem from "@/app/tim-kiem-ai/_components/ChatMessageItem";
import type { ChatMessage } from "@/app/tim-kiem-ai/types";

interface AiChatPanelProps {
  messages: ChatMessage[];
  isTyping: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}

export default function AiChatPanel({
  messages,
  isTyping,
  inputValue,
  onInputChange,
  onSubmit,
}: AiChatPanelProps) {
  return (
    <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[600px] lg:h-full overflow-hidden">
      {/* Section Header */}
      <div className="p-3.5 px-4 border-b border-[#E8E4DC] flex items-center justify-between bg-white">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>1. Chat / Nhập yêu cầu</span>
        </h2>
        <span className="text-[11px] font-semibold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full">
          AI Assistant
        </span>
      </div>

      {/* Chat Conversation Messages Container */}
      <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs leading-relaxed bg-[#FAFBF9]">
        {messages.map((message) => (
          <ChatMessageItem key={message.id} message={message} />
        ))}

        {isTyping && (
          <div className="flex items-center gap-2 text-xs text-gray-500 pl-10">
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce"></span>
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-100"></span>
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-200"></span>
            <span className="italic text-[11px]">AI đang phân tích yêu cầu mới...</span>
          </div>
        )}
      </div>

      {/* Chat Input Footer */}
      <form onSubmit={onSubmit} className="p-3 border-t border-[#E8E4DC] bg-white">
        <div className="relative flex items-center">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            placeholder="Nhập tin nhắn để điều chỉnh yêu cầu..."
            className="w-full pl-4 pr-12 py-2.5 bg-[#FAFBF9] border border-[#E8E4DC] rounded-full text-xs text-[#121E1A] focus:outline-none focus:ring-2 focus:ring-[#0F5F4A]/20 focus:border-[#0F5F4A] transition placeholder-[#6F7974]"
          />
          <button
            type="submit"
            className="absolute right-1.5 w-8 h-8 bg-[#0F5F4A] hover:bg-[#004635] text-white rounded-full flex items-center justify-center transition shadow-xs"
          >
            <span className="material-symbols-outlined text-[16px]">send</span>
          </button>
        </div>
      </form>
    </section>
  );
}