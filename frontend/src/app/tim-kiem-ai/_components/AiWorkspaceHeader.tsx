"use client";

import Breadcrumbs from "@/components/Breadcrumbs";

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
          <Breadcrumbs
            items={[{ label: "Trang chủ", href: "/" }, { label: "Tìm kiếm với AI" }]}
          />
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