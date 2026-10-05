import Link from "next/link";

export default function AiWorkspaceHeader() {
  return (
    <div className="w-full max-w-[1500px] mx-auto px-4 lg:px-8 pt-4 pb-1">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#E8E4DC] pb-3">
        <div>
          <div className="flex items-center gap-2 text-xs text-[#6F7974] mb-1 font-medium">
            <Link href="/" className="hover:text-[#0F5F4A] transition">Trang chủ</Link>
            <span>/</span>
            <span className="text-[#0F5F4A] font-semibold">Tìm với AI</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-extrabold text-[#121E1A] tracking-tight flex items-center gap-2">
            <span className="w-7 h-7 rounded-xl bg-[#E6F4EE] text-[#0F5F4A] flex items-center justify-center text-sm">
              <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
            </span>
            <span>Không Gian Tìm Phòng Trọ Thông Minh</span>
          </h1>
          <p className="text-xs sm:text-sm text-[#3F4944] mt-0.5">
            Trợ lý trí tuệ nhân tạo Homigo phân tích tiêu chí cá nhân hóa và xếp hạng phòng tối ưu nhất theo thời gian thực.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#E6F4EE] border border-[#0F5F4A]/20 text-[#0F5F4A] text-xs font-bold shadow-2xs">
            <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-pulse"></span>
            <span>AI Agent đang hoạt động</span>
          </span>
        </div>
      </div>
    </div>
  );
}