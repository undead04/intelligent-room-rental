"use client";

import Link from "next/link";

interface AiWorkspaceHeaderProps {
  onResetConversation?: () => void;
  hasActiveSession?: boolean;
}

export default function AiWorkspaceHeader({
  onResetConversation,
  hasActiveSession,
}: AiWorkspaceHeaderProps) {
  return (
    <div className="w-full max-w-[1600px] mx-auto px-4 lg:px-6 pt-2 pb-1 shrink-0">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#E8E4DC] pb-2">
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs text-[#6F7974] font-medium">
            <Link href="/" className="hover:text-[#0F5F4A] transition">Trang chủ</Link>
            <span>/</span>
            <span className="text-[#0F5F4A] font-semibold">Tìm với AI</span>
          </div>
          <span className="text-gray-300 hidden sm:inline">|</span>
          <h1 className="text-sm sm:text-base font-extrabold text-[#121E1A] tracking-tight flex items-center gap-1.5">
            <span className="w-6 h-6 rounded-lg bg-[#E6F4EE] text-[#0F5F4A] flex items-center justify-center">
              <span className="material-symbols-outlined text-[15px]">auto_awesome</span>
            </span>
            <span>Không Gian Tìm Phòng Trọ Thông Minh AI</span>
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {hasActiveSession && onResetConversation && (
            <button
              onClick={onResetConversation}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-white border border-[#E8E4DC] hover:border-[#0F5F4A] text-[#4A5550] hover:text-[#0F5F4A] text-[11px] font-semibold transition cursor-pointer shadow-2xs"
              title="Xoá lịch sử chat và bắt đầu phiên tìm kiếm mới"
            >
              <span className="material-symbols-outlined text-[14px]">refresh</span>
              <span>Hội thoại mới</span>
            </button>
          )}

          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#E6F4EE] border border-[#0F5F4A]/20 text-[#0F5F4A] text-[11px] font-bold shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A] animate-pulse"></span>
            <span>AI Agent đang kết nối</span>
          </span>
        </div>
      </div>
    </div>
  );
}