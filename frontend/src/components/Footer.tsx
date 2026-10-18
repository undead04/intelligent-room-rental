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
            <div className="mt-5 flex items-center gap-2.5">
              <a
                href="https://facebook.com"
                target="_blank"
                rel="noreferrer"
                aria-label="Homigo trên Facebook"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#35534A] bg-[#18362D] text-[#C9D9D2] transition-colors hover:border-[#8DD5BA] hover:bg-[#0F5F4A] hover:text-white"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
                </svg>
              </a>
              <a
                href="https://linkedin.com"
                target="_blank"
                rel="noreferrer"
                aria-label="Homigo trên LinkedIn"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#35534A] bg-[#18362D] text-[#C9D9D2] transition-colors hover:border-[#8DD5BA] hover:bg-[#0F5F4A] hover:text-white"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
                </svg>
              </a>
              <a
                href="https://youtube.com"
                target="_blank"
                rel="noreferrer"
                aria-label="Homigo trên YouTube"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#35534A] bg-[#18362D] text-[#C9D9D2] transition-colors hover:border-[#8DD5BA] hover:bg-[#0F5F4A] hover:text-white"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                  <path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z" />
                </svg>
              </a>
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
            <Link href="/tim-kiem-ai" className="text-[#8DD5BA] hover:text-white">Trợ lý AI</Link>
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
