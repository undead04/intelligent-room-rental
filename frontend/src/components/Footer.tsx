import Link from "next/link";

const exploreLinks = [
  ["Phòng trọ TP.HCM", "/tim-kiem"],
  ["Căn hộ dịch vụ", "/tim-kiem"],
  ["Nhà nguyên căn", "/tim-kiem"],
  ["Tìm phòng bằng AI", "/tim-kiem-ai"],
];

const toolLinks = [
  ["Tra cứu giá trọ", "/tra-cuu-gia-tro"],
  ["Tính chi phí sinh hoạt", "#"],
  ["Mẫu hợp đồng thuê phòng", "#"],
];

export default function Footer() {
  return (
    <footer className="mt-auto w-full border-t border-[#DCECE4] bg-[#10251F] text-white">
      <div className="mx-auto max-w-[1500px] px-4 pb-7 pt-10 lg:px-8">
        <div className="grid gap-9 md:grid-cols-[1.5fr_1fr_1fr_1.2fr]">
          <div>
            <Link href="/" className="inline-flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0F5F4A] shadow-[0_8px_20px_rgba(0,0,0,0.18)]">
                <span className="material-symbols-outlined text-[22px]">apartment</span>
              </span>
              <span className="font-['Plus_Jakarta_Sans'] text-2xl font-extrabold tracking-tight">
                Homigo<span className="text-[#FF6B4A]">.</span>
              </span>
            </Link>
            <p className="mt-4 max-w-xs text-sm leading-6 text-[#B3C4BD]">
              Nền tảng tìm kiếm phòng trọ, nhà thuê và căn hộ thông minh giúp bạn tìm đúng nơi để gọi là nhà.
            </p>
            <div className="mt-5 flex items-center gap-2">
              {["facebook", "linkedin", "play_arrow"].map((icon) => (
                <button
                  key={icon}
                  type="button"
                  aria-label={`Homigo trên ${icon}`}
                  className="flex h-9 w-9 items-center justify-center rounded-full border border-[#35534A] bg-[#18362D] text-[#C9D9D2] transition-colors hover:border-[#8DD5BA] hover:bg-[#0F5F4A] hover:text-white"
                >
                  <span className="material-symbols-outlined text-[17px]">{icon}</span>
                </button>
              ))}
            </div>
          </div>

          <FooterColumn title="Khám phá" links={exploreLinks} />
          <FooterColumn title="Công cụ & tiện ích" links={toolLinks} />

          <div>
            <h3 className="text-sm font-bold text-white">Liên hệ & hỗ trợ</h3>
            <div className="mt-4 space-y-3 text-sm text-[#B3C4BD]">
              <p className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px] text-[#8DD5BA]">call</span>
                <span>1900 6868</span>
              </p>
              <p className="flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px] text-[#8DD5BA]">mail</span>
                <span>support@homigo.vn</span>
              </p>
              <p className="flex items-start gap-2">
                <span className="material-symbols-outlined text-[18px] text-[#8DD5BA]">location_on</span>
                <span>TP. Hồ Chí Minh, Việt Nam</span>
              </p>
            </div>
          </div>
        </div>

        <div className="mt-9 flex flex-col items-center justify-between gap-3 border-t border-[#29453C] pt-5 text-xs text-[#829991] sm:flex-row">
          <p>© 2026 Homigo Rental Marketplace.</p>
          <div className="flex flex-wrap justify-center gap-x-5 gap-y-2">
            <Link href="#" className="hover:text-white">Điều khoản sử dụng</Link>
            <Link href="#" className="hover:text-white">Chính sách bảo mật</Link>
            <Link href="/stitch-preview" className="text-[#8DD5BA] hover:text-white">UI Stitch Assets</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }: { title: string; links: string[][] }) {
  return (
    <div>
      <h3 className="text-sm font-bold text-white">{title}</h3>
      <ul className="mt-4 space-y-3 text-sm text-[#B3C4BD]">
        {links.map(([label, href]) => (
          <li key={label}>
            <Link href={href} className="transition-colors hover:text-[#8DD5BA]">{label}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
