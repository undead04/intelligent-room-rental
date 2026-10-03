import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full bg-[#121E1A] text-white border-t border-gray-800 pt-12 pb-8 mt-auto">
      <div className="max-w-[1500px] mx-auto px-4 lg:px-8">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 mb-12">
          <div className="space-y-4 md:col-span-1">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-xl bg-[#0F5F4A] flex items-center justify-center text-white">
                <span className="material-symbols-outlined text-[20px]">apartment</span>
              </div>
              <span className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl text-white">
                Homigo<span className="text-[#FF6B4A]">.</span>
              </span>
            </div>
            <p className="text-gray-400 text-sm leading-relaxed">
              Nền tảng tìm kiếm phòng trọ, nhà thuê và căn hộ thông minh ứng dụng AI hàng đầu tại Việt Nam.
            </p>
          </div>

          <div>
            <h4 className="font-bold text-base mb-4 text-gray-200">Khám phá</h4>
            <ul className="space-y-2.5 text-sm text-gray-400">
              <li><Link href="/tim-kiem" className="hover:text-white transition-colors">Phòng trọ TP.HCM</Link></li>
              <li><Link href="/tim-kiem" className="hover:text-white transition-colors">Căn hộ dịch vụ</Link></li>
              <li><Link href="/tim-kiem" className="hover:text-white transition-colors">Nhà nguyên căn</Link></li>
              <li><Link href="/tim-kiem-ai" className="hover:text-white transition-colors">Tìm phòng bằng AI</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-base mb-4 text-gray-200">Công cụ & Tiện ích</h4>
            <ul className="space-y-2.5 text-sm text-gray-400">
              <li><Link href="/tra-cuu-gia-tro" className="hover:text-white transition-colors">Tra cứu giá trọ</Link></li>
              <li><Link href="/stitch-preview" className="hover:text-white transition-colors">Stitch Design Preview</Link></li>
              <li><Link href="#" className="hover:text-white transition-colors">Tính chi phí sinh hoạt</Link></li>
              <li><Link href="#" className="hover:text-white transition-colors">Mẫu hợp đồng thuê phòng</Link></li>
            </ul>
          </div>

          <div>
            <h4 className="font-bold text-base mb-4 text-gray-200">Liên hệ & Hỗ trợ</h4>
            <p className="text-sm text-gray-400 mb-2">Tổng đài hỗ trợ: <span className="text-[#8DD5BA] font-semibold">1900 6868</span></p>
            <p className="text-sm text-gray-400 mb-4">Email: <span className="text-gray-200">support@homigo.vn</span></p>
            <div className="flex gap-3">
              <span className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-gray-300 hover:bg-[#0F5F4A] hover:text-white cursor-pointer transition-colors text-sm">f</span>
              <span className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-gray-300 hover:bg-[#0F5F4A] hover:text-white cursor-pointer transition-colors text-sm">in</span>
              <span className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center text-gray-300 hover:bg-[#0F5F4A] hover:text-white cursor-pointer transition-colors text-sm">yt</span>
            </div>
          </div>
        </div>

        <div className="pt-8 border-t border-gray-800/80 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-gray-500">
          <p>© 2026 Homigo Rental Marketplace. Đồ án tốt nghiệp.</p>
          <div className="flex gap-6">
            <Link href="#" className="hover:underline">Điều khoản sử dụng</Link>
            <Link href="#" className="hover:underline">Chính sách bảo mật</Link>
            <Link href="/stitch-preview" className="hover:underline text-[#8DD5BA]">UI Stitch Assets</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
