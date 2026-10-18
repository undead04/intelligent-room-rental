import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";

export default function NotFound() {
  return (
    <SiteLayout className="bg-[#FAF8F4] flex flex-col min-h-screen">
      <main className="flex-1 max-w-[800px] w-full mx-auto px-4 py-20 sm:py-28 flex flex-col items-center justify-center text-center">
        {/* Subtle pill tag */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#0F5F4A] text-xs font-semibold mb-6">
          <span className="w-2 h-2 rounded-full bg-[#0F5F4A]"></span>
          <span>Mã lỗi 404</span>
        </div>

        {/* Clean Typographic 404 */}
        <div className="text-7xl sm:text-9xl font-black font-['Plus_Jakarta_Sans'] text-[#0F5F4A] tracking-tight leading-none mb-4 select-none">
          404
        </div>

        {/* Main Heading */}
        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] tracking-tight mb-3">
          Không tìm thấy trang bạn yêu cầu
        </h1>

        {/* Subtitle */}
        <p className="text-sm sm:text-base text-[#6F7974] max-w-md mx-auto mb-8 leading-relaxed">
          Đường dẫn có thể bị sai, tin đăng phòng đã hết hạn hoặc trang đã được chuyển sang địa chỉ mới.
        </p>

        {/* Primary Action Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-3 mb-10">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white px-6 py-3 text-sm font-bold shadow-xs transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">home</span>
            <span>Về trang chủ</span>
          </Link>
          <Link
            href="/tim-kiem"
            className="inline-flex items-center gap-2 rounded-full border border-[#DCECE4] bg-white hover:bg-[#F1FBF6] text-[#0F5F4A] px-6 py-3 text-sm font-bold shadow-2xs transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">search</span>
            <span>Tìm phòng trọ</span>
          </Link>
          <Link
            href="/tim-kiem-ai"
            className="inline-flex items-center gap-2 rounded-full bg-[#FF6B4A] hover:bg-[#e85b3d] text-white px-6 py-3 text-sm font-bold shadow-xs transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
            <span>Hỏi AI tìm phòng</span>
          </Link>
        </div>

        {/* Subtle quick links */}
        <div className="pt-6 border-t border-[#E8E4DC] w-full max-w-md">
          <p className="text-xs text-[#8A9590] mb-3">
            Hoặc bạn có thể truy cập nhanh các mục sau:
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
            <Link
              href="/"
              className="px-3 py-1 rounded-full bg-white border border-[#E8E4DC] text-[#3F4944] hover:text-[#0F5F4A] hover:border-[#0F5F4A] transition-colors"
            >
              Phòng mới nhất
            </Link>
            <Link
              href="/tim-kiem"
              className="px-3 py-1 rounded-full bg-white border border-[#E8E4DC] text-[#3F4944] hover:text-[#0F5F4A] hover:border-[#0F5F4A] transition-colors"
            >
              Phòng theo quận
            </Link>
            <Link
              href="/tra-cuu-gia-tro"
              className="px-3 py-1 rounded-full bg-white border border-[#E8E4DC] text-[#3F4944] hover:text-[#0F5F4A] hover:border-[#0F5F4A] transition-colors"
            >
              Báo cáo giá thị trường
            </Link>
          </div>
        </div>
      </main>
    </SiteLayout>
  );
}
