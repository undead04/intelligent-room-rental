"use client";

import { useState } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";
import PropertyGallery from "@/components/PropertyGallery";

export default function PropertyDetailPage() {
  const [selectedImgIdx, setSelectedImgIdx] = useState(0);
  const [showPhone, setShowPhone] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  const images = [
    "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=1200&q=80",
    "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&q=80",
  ];

  const amenities = [
    { icon: "ac_unit", label: "Máy lạnh Inveter", active: true },
    { icon: "stairs", label: "Gác lửng cao 1.8m", active: true },
    { icon: "lock", label: "Khóa vân tay 24/7", active: true },
    { icon: "local_laundry_service", label: "Máy giặt chung", active: true },
    { icon: "kitchen", label: "Kệ bếp & chậu rửa", active: true },
    { icon: "balcony", label: "Ban công thoáng mát", active: true },
    { icon: "wifi", label: "Wifi tốc độ cao", active: true },
    { icon: "two_wheeler", label: "Nhà để xe rộng rãi", active: true },
    { icon: "pets", label: "Cho phép nuôi pet nhỏ", active: true },
    { icon: "security", label: "Camera an ninh 24/7", active: true },
  ];

  return (
    <SiteLayout className="bg-[#FAF8F4]">

      {/* Breadcrumb */}
      <div className="w-full bg-white border-b border-[#E8E4DC]">
        <div className="max-w-[1500px] mx-auto px-4 lg:px-8 py-3">
          <nav className="flex items-center gap-1.5 text-xs text-gray-500 overflow-x-auto hide-scrollbar">
            <Link href="/" className="hover:text-[#0F5F4A]">Trang chủ</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <Link href="/tim-kiem" className="hover:text-[#0F5F4A]">Phòng trọ TP.HCM</Link>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="hover:text-[#0F5F4A]">Gò Vấp</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-[#121E1A] font-semibold truncate max-w-[280px]">
              DUPLEX MỚI DƯƠNG QUẢNG HÀM ĐI ĐÂU CŨNG TIỆN
            </span>
          </nav>
        </div>
      </div>

      {/* Sticky Sub-Nav */}
      <div className="sticky top-[72px] z-40 w-full bg-white/95 backdrop-blur-md shadow-xs border-b border-[#E8E4DC]">
        <div className="max-w-[1380px] mx-auto px-4 lg:px-8 h-16 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <img
              src={images[0]}
              alt="Thumbnail"
              className="w-11 h-11 rounded-xl object-cover shrink-0"
            />
            <div className="min-w-0">
              <h2 className="text-sm font-bold text-[#121E1A] truncate">
                DUPLEX MỚI DƯƠNG QUẢNG HÀM ĐI ĐÂU CŨNG TIỆN
              </h2>
              <div className="flex items-center gap-2 text-xs">
                <span className="font-['Plus_Jakarta_Sans'] font-extrabold text-[#FF6B4A]">
                  3,3 triệu/tháng
                </span>
                <span className="text-gray-400">• 20 m²</span>
              </div>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setIsSaved(!isSaved)}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-[#E9F7F0] hover:bg-[#E3F1EA] text-[#0F5F4A] transition-all text-xs font-semibold"
            >
              <span className="material-symbols-outlined text-[18px]">
                {isSaved ? "bookmark_added" : "bookmark"}
              </span>
              <span className="hidden sm:inline">{isSaved ? "Đã lưu" : "Lưu tin"}</span>
            </button>

            <button
              onClick={() => setShowPhone(!showPhone)}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white font-bold text-xs shadow-xs transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">call</span>
              <span>{showPhone ? "0784 498 868" : "Hiện số 078449***"}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <main className="max-w-[1380px] mx-auto px-4 lg:px-8 py-6 w-full flex-1">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <PropertyGallery images={images} selectedIndex={selectedImgIdx} onSelect={setSelectedImgIdx} />

            {/* Title & Price Header */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className="px-3 py-1 rounded-full bg-[#E6F4EE] text-[#0F5F4A] text-xs font-bold">
                  Homigo Verified
                </span>
                <span className="px-3 py-1 rounded-full bg-[#FAF8F4] border border-[#E8E4DC] text-xs text-gray-600">
                  Mã tin: HM-88294
                </span>
              </div>

              <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl text-[#121E1A] mb-3">
                DUPLEX MỚI DƯƠNG QUẢNG HÀM ĐI ĐÂU CŨNG TIỆN
              </h1>

              <p className="text-xs sm:text-sm text-gray-600 flex items-center gap-1.5 mb-4">
                <span className="material-symbols-outlined text-[#0F5F4A] text-[18px]">location_on</span>
                <span>Đường Dương Quảng Hàm, Phường 5, Quận Gò Vấp, TP. Hồ Chí Minh</span>
              </p>

              <div className="p-4 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC] flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-baseline gap-2">
                  <span className="font-['Plus_Jakarta_Sans'] font-black text-3xl text-[#FF6B4A]">
                    3,3 triệu
                  </span>
                  <span className="text-sm text-gray-500">/ tháng</span>
                  <span className="ml-2 px-2.5 py-0.5 rounded-full bg-[#E9F7F0] text-[#0F5F4A] text-xs font-semibold">
                    Cọc 1 tháng
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs font-semibold text-gray-700">
                  <span>📐 20 m²</span>
                  <span>👥 2-3 người</span>
                  <span>🏢 Tầng 3</span>
                </div>
              </div>
            </div>

            {/* Cost Breakdown */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A] mb-4">
                Chi phí sinh hoạt hàng tháng
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="p-3.5 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]">
                  <div className="text-xs text-gray-500 mb-1">⚡ Tiền điện</div>
                  <div className="font-bold text-sm text-[#121E1A]">3.800 đ/kWh</div>
                </div>
                <div className="p-3.5 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]">
                  <div className="text-xs text-gray-500 mb-1">💧 Tiền nước</div>
                  <div className="font-bold text-sm text-[#121E1A]">100.000 đ/người</div>
                </div>
                <div className="p-3.5 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]">
                  <div className="text-xs text-gray-500 mb-1">🌐 Wifi + Rác</div>
                  <div className="font-bold text-sm text-[#121E1A]">150.000 đ/phòng</div>
                </div>
                <div className="p-3.5 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]">
                  <div className="text-xs text-gray-500 mb-1">🛵 Giữ xe máy</div>
                  <div className="font-bold text-sm text-[#0F5F4A]">Miễn phí</div>
                </div>
              </div>
            </div>

            {/* Amenities Grid */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs">
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A] mb-4">
                Tiện ích & Trang thiết bị
              </h2>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {amenities.map((a) => (
                  <div
                    key={a.label}
                    className="flex items-center gap-2.5 p-3 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC]"
                  >
                    <span className="material-symbols-outlined text-[#0F5F4A] text-[20px]">
                      {a.icon}
                    </span>
                    <span className="text-xs font-semibold text-gray-800">{a.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Description */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-xs space-y-3">
              <h2 className="font-['Plus_Jakarta_Sans'] font-bold text-lg text-[#121E1A]">
                Mô tả chi tiết
              </h2>
              <div className="text-sm text-gray-700 space-y-2 leading-relaxed">
                <p>
                  CHO THUÊ PHÒNG DUPLEX BAN CÔNG MỚI 100% TẠI DƯƠNG QUẢNG HÀM, GÒ VẤP.
                </p>
                <p>
                  - Vị trí thuận lợi: Gần ĐH Văn Lang CS3 (5 phút), ĐH Công Nghiệp IUH (7 phút), gần Emart Phan Văn Trị và chợ An Nhơn.
                </p>
                <p>
                  - Phòng mới xây, có gác lửng cao đứng không đụng đầu, ban công cửa sổ thoáng mát, đầy đủ máy lạnh, kệ bếp nấu ăn, toilet riêng có máy nước nóng.
                </p>
                <p>
                  - Giờ giấc tự do 24/7 không chung chủ, khóa cổng vân tay thông minh, camera an ninh toàn tòa nhà.
                </p>
              </div>
            </div>
          </div>

          {/* Right Column (4 cols) - Sticky Landlord Card */}
          <div className="lg:col-span-4 sticky top-[150px] space-y-5">
            {/* Landlord Card */}
            <div className="bg-white rounded-2xl p-6 border border-[#E8E4DC] shadow-sm">
              <div className="flex items-center gap-3.5 pb-4 border-b border-gray-100">
                <div className="w-14 h-14 rounded-full overflow-hidden bg-gray-200 border-2 border-[#0F5F4A]">
                  <img
                    src="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&w=200&q=80"
                    alt="Chủ nhà avatar"
                    className="w-full h-full object-cover"
                  />
                </div>
                <div>
                  <h3 className="font-['Plus_Jakarta_Sans'] font-bold text-base text-[#121E1A]">
                    Chị Mai Anh
                  </h3>
                  <div className="flex items-center gap-1 text-xs text-[#0F5F4A] font-semibold mt-0.5">
                    <span className="material-symbols-outlined text-[16px]">verified</span>
                    <span>Chủ nhà xác thực Homigo</span>
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1">Phản hồi trong 5 phút</div>
                </div>
              </div>

              <div className="py-4 space-y-3">
                <button
                  onClick={() => setShowPhone(!showPhone)}
                  className="w-full py-3.5 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white font-bold text-sm flex items-center justify-center gap-2 shadow-sm transition-all"
                >
                  <span className="material-symbols-outlined text-[20px]">call</span>
                  <span>{showPhone ? "0784 498 868" : "Gọi điện: 0784 498 ***"}</span>
                </button>

                <button
                  className="w-full py-3.5 rounded-full bg-[#E6F4EE] hover:bg-[#D5EFE5] text-[#0F5F4A] font-bold text-sm flex items-center justify-center gap-2 transition-all"
                >
                  <span className="material-symbols-outlined text-[20px]">chat</span>
                  <span>Nhắn tin tư vấn phòng</span>
                </button>

                <button
                  className="w-full py-3 rounded-full border border-[#E8E4DC] hover:bg-[#FAF8F4] text-xs font-semibold text-gray-700 flex items-center justify-center gap-1.5 transition-all"
                >
                  <span className="material-symbols-outlined text-[16px]">calendar_today</span>
                  <span>Đặt lịch xem phòng trực tiếp</span>
                </button>
              </div>

              <div className="p-3 rounded-xl bg-[#FAF8F4] border border-[#E8E4DC] text-xs text-gray-600 space-y-1">
                <div className="font-semibold text-[#121E1A]">🛡️ Cam kết Homigo</div>
                <p>Tin đăng thật 100%, không thu phí trung gian của người thuê phòng.</p>
              </div>
            </div>
          </div>
        </div>
      </main>

    </SiteLayout>
  );
}
