"use client";

import { useEffect, useRef } from "react";
import ChatMessageItem from "@/app/tim-kiem-ai/_components/ChatMessageItem";
import type { ChatMessage } from "@/app/tim-kiem-ai/types";

interface AiChatPanelProps {
  messages: ChatMessage[];
  isTyping: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (event: React.FormEvent) => void;
  onSelectQuestion?: (question: string) => void;
}

const MAX_TEXTAREA_HEIGHT = 132;

export default function AiChatPanel({
  messages,
  isTyping,
  inputValue,
  onInputChange,
  onSubmit,
  onSelectQuestion,
}: AiChatPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // Tự động co giãn chiều cao textarea theo nội dung nhập và reset khi xóa rỗng
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const nextHeight = Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT);
    el.style.height = `${nextHeight}px`;
    el.style.overflowY = el.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden";
  }, [inputValue]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!isTyping && inputValue.trim()) {
        formRef.current?.requestSubmit();
      }
    }
  };

  return (
    <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[520px] lg:h-full min-h-0 overflow-hidden">
      {/* Section Header */}
      <div className="p-3 px-4 border-b border-[#E8E4DC] flex items-center justify-between bg-white shrink-0">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>1. Chat / Nhập yêu cầu</span>
        </h2>
        <span className="text-[11px] font-semibold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full">
          AI Assistant
        </span>
      </div>

      {/* Chat Conversation Messages Container */}
      <div className="flex-1 min-h-0 p-3.5 sm:p-4 overflow-y-auto space-y-4 text-[13px] leading-relaxed bg-[#FAFBF9]">
        {messages.map((message, idx) => {
          const isLatest =
            idx === messages.length - 1 ||
            (idx === messages.length - 2 && messages[messages.length - 1]?.isStreaming);

          return (
            <ChatMessageItem
              key={message.id}
              message={message}
              isLatest={Boolean(isLatest)}
              isTyping={isTyping}
              onSelectQuestion={onSelectQuestion}
            />
          );
        })}

        {isTyping && !messages.some((m) => m.isStreaming) && (
          <div className="flex items-center gap-2 text-xs text-gray-500 pl-10">
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce"></span>
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-100"></span>
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-200"></span>
            <span className="italic text-[11px]">AI đang phân tích yêu cầu mới...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Chat Input Footer */}
      <form
        ref={formRef}
        onSubmit={onSubmit}
        className="p-2.5 sm:p-3 border-t border-[#E8E4DC] bg-white shrink-0"
      >
        <div className="flex items-end gap-2 bg-[#FAFBF9] border border-[#E8E4DC] rounded-2xl pl-3.5 pr-2 py-2 focus-within:ring-2 focus-within:ring-[#0F5F4A]/20 focus-within:border-[#0F5F4A] transition">
          <textarea
            ref={textareaRef}
            rows={1}
            data-ai-chat-input="true"
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Nhập yêu cầu (vd: 'gần UIT dưới 4tr có máy lạnh')..."
            className="w-full resize-none bg-transparent py-1 text-[13px] leading-[1.5] text-[#121E1A] focus:outline-none placeholder-[#6F7974] max-h-[132px] break-words"
          />
          <button
            type="submit"
            disabled={isTyping || !inputValue.trim()}
            className="shrink-0 w-8 h-8 bg-[#0F5F4A] hover:bg-[#0B4A39] disabled:opacity-40 text-white rounded-xl flex items-center justify-center transition shadow-xs cursor-pointer"
            aria-label="Gửi yêu cầu"
          >
            <span className="material-symbols-outlined text-[17px]">send</span>
          </button>
        </div>
        <p className="mt-1 px-1 text-[10px] text-[#6F7974] flex items-center justify-between">
          <span>Enter để gửi · Shift + Enter để xuống dòng</span>
        </p>
      </form>
    </section>
  );
}