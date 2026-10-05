import type { ChatMessage } from "@/app/tim-kiem-ai/types";
import { USER_AVATAR } from "@/app/tim-kiem-ai/_constants/aiWorkspace";

interface ChatMessageItemProps {
  message: ChatMessage;
}

export default function ChatMessageItem({ message }: ChatMessageItemProps) {
  if (message.sender === "user") {
    return (
      <div className="flex items-start gap-2.5">
        <div className="w-8 h-8 rounded-full overflow-hidden border border-[#E8E4DC] shrink-0 shadow-2xs">
          <img
            src={message.avatar || USER_AVATAR}
            alt="User avatar"
            className="w-full h-full object-cover"
          />
        </div>
        <div className="bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#121E1A] p-3.5 rounded-2xl rounded-tl-xs max-w-[90%] shadow-2xs font-medium leading-normal">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-2.5">
      <div className="w-8 h-8 rounded-full bg-[#0F5F4A] shrink-0 flex items-center justify-center text-white shadow-2xs">
        <span className="material-symbols-outlined text-[17px]">auto_awesome</span>
      </div>
      <div className="bg-white border border-[#E8E4DC] rounded-2xl rounded-tl-xs p-4 shadow-sm flex-1 space-y-3">
        <p className="font-bold text-[#121E1A]">{message.text}</p>

        {/* Condition: Bắt buộc */}
        {message.mandatoryCriteria && (
          <div className="space-y-1.5">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#E6F4EE] text-[#0F5F4A] text-[10px] font-bold rounded-full border border-[#0F5F4A]/20">
              <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
              <span>Bắt buộc</span>
            </span>
            <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
              {message.mandatoryCriteria.map((criteria, index) => (
                <li key={index} className="flex items-center gap-2 text-[#0F5F4A]">
                  <span className="material-symbols-outlined text-[15px] font-bold">check_circle</span>
                  <span>{criteria}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Condition: Ưu tiên */}
        {message.priorityCriteria && (
          <div className="space-y-1.5 pt-1 border-t border-[#F1F5F9]">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#FFF5E6] text-[#D97706] text-[10px] font-bold rounded-full border border-[#FFE0B2]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B4A]"></span>
              <span>Ưu tiên</span>
            </span>
            <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
              {message.priorityCriteria.map((criteria, index) => (
                <li key={index} className="flex items-center gap-2 text-[#B45309]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B4A]"></span>
                  <span>{criteria}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Clarification prompt text */}
        {message.summaryCount && (
          <p className="text-[11px] text-[#6F7974] pt-1 leading-normal border-t border-[#F1F5F9]">
            Mình đã tìm thấy <span className="font-bold text-[#0F5F4A]">{message.summaryCount} phòng</span> phù hợp nhất cho bạn ở khu vực gần UIT.
          </p>
        )}
      </div>
    </div>
  );
}