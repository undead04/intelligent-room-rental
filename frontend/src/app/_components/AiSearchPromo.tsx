import Link from "next/link";

export default function AiSearchPromo() {
  return (
    <section className="w-full mb-12 rounded-2xl border border-[#DCECE4] bg-[#F1FBF6] p-5 sm:p-7">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-11 h-11 rounded-full bg-[#0F5F4A] text-white flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-[22px]">auto_awesome</span>
          </div>
          <div>
            <h2 className="font-['Plus_Jakarta_Sans'] font-extrabold text-lg text-[#121E1A]">
              Tìm kiếm thông minh với AI
            </h2>
            <p className="text-xs sm:text-sm text-[#4A5550] mt-1">
              Mô tả nhu cầu, Homigo sẽ giúp bạn tìm căn phòng phù hợp nhất.
            </p>
          </div>
        </div>
        <Link
          href="/tim-kiem-ai"
          className="inline-flex items-center gap-1.5 rounded-full bg-[#FF6B4A] px-5 py-2.5 text-xs font-bold text-white hover:bg-[#e85b3d] transition-colors"
        >
          Thử ngay
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>
      </div>
    </section>
  );
}