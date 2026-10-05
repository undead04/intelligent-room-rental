const HIGHLIGHTS: { icon: string; title: string; description: string }[] = [
  {
    icon: "verified",
    title: "100% tin thật",
    description: "Tin đăng được kiểm duyệt và cập nhật thường xuyên.",
  },
  {
    icon: "search",
    title: "Tìm kiếm thông minh",
    description: "Bộ lọc rõ ràng, tìm nhanh đúng nhu cầu.",
  },
  {
    icon: "shield",
    title: "An toàn & minh bạch",
    description: "Thông tin giá và vị trí được trình bày rõ ràng.",
  },
  {
    icon: "support_agent",
    title: "Đồng hành tận tâm",
    description: "Luôn sẵn sàng hỗ trợ bạn trong quá trình tìm nhà.",
  },
];

export default function WhyChooseHomigo() {
  return (
    <section className="w-full mb-12">
      <div className="text-center mb-5">
        <h2 className="font-['Plus_Jakarta_Sans'] text-xl sm:text-2xl font-bold text-[#121E1A]">
          Tại sao người dùng tin chọn Homigo?
        </h2>
        <p className="text-xs sm:text-sm text-[#6F7974] mt-1">Tìm nhà dễ dàng, an tâm ở lâu dài.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {HIGHLIGHTS.map((highlight) => (
          <div key={highlight.title} className="rounded-2xl border border-[#E0EEE7] bg-white p-4 shadow-xs">
            <span className="material-symbols-outlined text-[24px] text-[#0F5F4A]">{highlight.icon}</span>
            <h3 className="mt-3 text-sm font-bold text-[#121E1A]">{highlight.title}</h3>
            <p className="mt-1 text-xs leading-5 text-[#6F7974]">{highlight.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}