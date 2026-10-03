"use client";

import { useState } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";
import FilterModal from "@/components/FilterModal";
import ListingSection from "@/components/ListingSection";
import { Listing } from "@/components/ListingCard";

export default function HomePage() {
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [selectedCity, setSelectedCity] = useState("Hồ Chí Minh");
  const [searchQuery, setSearchQuery] = useState("");

  const houseListings: Listing[] = [
    {
      id: "house-1",
      title: "Nhà nguyên căn 3 tầng",
      location: "Tăng Nhơn Phú A, TP. Thủ Đức, TP.HCM",
      price: "12 triệu",
      tag: "⚡ Mới",
      source: "Chợ Tốt",
      image: "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=600&q=80",
      time: "1 giờ trước"
    },
    {
      id: "house-2",
      title: "Nhà riêng 2 phòng ngủ",
      location: "Vĩnh Lộc A, Bình Chánh, TP.HCM",
      price: "5 triệu",
      tag: "⚡ Mới",
      source: "Chợ Tốt",
      image: "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=600&q=80",
      time: "1 giờ trước"
    },
    {
      id: "house-3",
      title: "Biệt thự mini sân vườn",
      location: "Tân Thuận Đông, Quận 7, TP.HCM",
      price: "40 triệu",
      tag: "⚡ Mới",
      source: "Homigo Verified",
      image: "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?auto=format&fit=crop&w=600&q=80",
      time: "2 giờ trước"
    },
    {
      id: "house-4",
      title: "Nhà phố liền kề",
      location: "Tân Phong, Quận 7, TP.HCM",
      price: "25 triệu",
      tag: "⚡ Mới",
      source: "Chợ Tốt",
      image: "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=600&q=80",
      time: "3 giờ trước"
    }
  ];

  const studentRooms: Listing[] = [
    {
      id: "room-1",
      title: "Phòng trọ ban công full nội thất",
      location: "Dương Quảng Hàm, Gò Vấp, TP.HCM",
      price: "4.5 triệu",
      tag: "🔥 Hot",
      source: "Homigo Verified",
      image: "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?auto=format&fit=crop&w=600&q=80",
      time: "30 phút trước"
    },
    {
      id: "room-2",
      title: "Phòng Duplex gác lửng cao cấp",
      location: "Đặng Văn Bi, Thủ Đức, TP.HCM",
      price: "3.8 triệu",
      tag: "⚡ Mới",
      source: "Homigo Verified",
      image: "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=600&q=80",
      time: "45 phút trước"
    },
    {
      id: "room-3",
      title: "KTX cao cấp máy lạnh 24/7",
      location: "Điện Biên Phủ, Bình Thạnh, TP.HCM",
      price: "1.8 triệu",
      tag: "⭐ Giá tốt",
      source: "Chợ Tốt",
      image: "https://images.unsplash.com/photo-1555854877-bab0e564b8d5?auto=format&fit=crop&w=600&q=80",
      time: "2 giờ trước"
    },
    {
      id: "room-4",
      title: "Studio cửa sổ thoáng mát",
      location: "Nguyễn Gia Trí (D2), Bình Thạnh",
      price: "5.2 triệu",
      tag: "⚡ Mới",
      source: "Homigo Verified",
      image: "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=600&q=80",
      time: "4 giờ trước"
    }
  ];

  const universityZones = [
    { name: "ĐHQG TP.HCM (Khu Đô Thị)", count: "1.420 phòng", icon: "school" },
    { name: "ĐH Bách Khoa (Quận 10)", count: "890 phòng", icon: "engineering" },
    { name: "ĐH Kinh Tế UEH (Quận 3/Quận 10)", count: "760 phòng", icon: "payments" },
    { name: "ĐH Sư Phạm Kỹ Thuật (Thủ Đức)", count: "1.150 phòng", icon: "memory" },
    { name: "ĐH Tôn Đức Thắng (Quận 7)", count: "980 phòng", icon: "location_city" },
    { name: "ĐH Ngoại Thương CS2 (Bình Thạnh)", count: "670 phòng", icon: "business" },
  ];

  return (
    <SiteLayout className="bg-[#FAF8F4]" onOpenFilter={() => setIsFilterOpen(true)}>

      <main className="w-full flex-1">
        {/* HERO SEARCH AREA */}
        <section className="w-full bg-gradient-to-b from-[#EFFDF6] via-[#EFFDF6]/70 to-[#FAF8F4] pt-8 pb-6">
          <div className="max-w-4xl mx-auto px-4 flex flex-col items-center text-center">
            <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-3xl sm:text-4xl text-[#0F5F4A] tracking-tight mb-2">
              Tìm phòng trọ, căn hộ ưng ý cùng AI
            </h1>
            <p className="text-sm sm:text-base text-[#3F4944] mb-6">
              Hàng ngàn tin đăng được xác thực mỗi ngày từ các nguồn uy tín
            </p>

            {/* Pill Search Bar */}
            <div className="w-full relative flex items-center bg-white rounded-full h-14 border border-[#E8E4DC] shadow-[0_4px_20px_rgba(15,95,74,0.06)] px-5 gap-3 transition-shadow focus-within:shadow-[0_6px_24px_rgba(15,95,74,0.12)]">
              <span className="material-symbols-outlined text-[#6F7974] text-[22px] shrink-0">search</span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Bạn muốn tìm phòng ở đâu? (vd: gần ĐH Bách Khoa, dưới 4 triệu...)"
                className="w-full h-full bg-transparent text-sm text-[#121E1A] placeholder:text-[#6F7974] outline-none"
              />
              <button
                onClick={() => setIsFilterOpen(true)}
                className="relative flex items-center justify-center w-10 h-10 rounded-full bg-[#E9F7F0] hover:bg-[#E3F1EA] text-[#0F5F4A] transition-colors shrink-0"
                title="Mở bộ lọc nâng cao"
              >
                <span className="material-symbols-outlined text-[20px]">tune</span>
                <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#FF6B4A] text-white text-[10px] font-bold shadow-sm">
                  2
                </span>
              </button>
              <Link
                href={`/tim-kiem?q=${encodeURIComponent(searchQuery)}`}
                className="px-5 py-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white text-sm font-semibold transition-all shrink-0 hidden sm:inline-flex items-center gap-1.5"
              >
                <span>Tìm</span>
              </Link>
            </div>

            {/* City Chips */}
            <div className="flex items-center justify-center gap-3 mt-4 flex-wrap">
              {["Đà Nẵng", "Hồ Chí Minh", "Hà Nội", "Bình Dương"].map((city) => {
                const active = selectedCity === city;
                return (
                  <button
                    key={city}
                    onClick={() => setSelectedCity(city)}
                    className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-semibold transition-all shadow-xs ${
                      active
                        ? "border border-[#0F5F4A] bg-[#E6F4EE] text-[#0F5F4A]"
                        : "border border-[#E8E4DC] bg-white text-[#3F4944] hover:bg-[#E3F1EA]"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[16px]">
                      {city === "Đà Nẵng" ? "waves" : city === "Hồ Chí Minh" ? "domain" : "temple_buddhist"}
                    </span>
                    <span>{city}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <div className="max-w-[1500px] mx-auto px-4 lg:px-8 py-8">
          <ListingSection
            title="Phòng trọ & KTX sinh viên giá tốt"
            description="Các phòng trọ đầy đủ tiện nghi, giá rẻ cho sinh viên và người đi làm"
            listings={studentRooms}
          />
          <ListingSection
            title="Nhà nguyên căn cho thuê"
            description="Không gian riêng tư, thích hợp hộ gia đình và nhóm bạn"
            listings={houseListings}
          />

          {/* SECTION: KHU VỰC ĐẠI HỌC NỔI BẬT */}
          <section className="w-full mb-12">
            <h2 className="font-['Plus_Jakarta_Sans'] text-xl sm:text-2xl font-bold text-[#121E1A] mb-4">
              Khu vực quanh các trường Đại Học
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
              {universityZones.map((zone) => (
                <Link
                  key={zone.name}
                  href={`/tim-kiem?q=${encodeURIComponent(zone.name)}`}
                  className="flex items-center gap-3.5 p-4 rounded-2xl bg-white border border-[#E8E4DC] hover:border-[#0F5F4A] hover:bg-[#E6F4EE]/30 transition-all shadow-xs group"
                >
                  <div className="w-11 h-11 rounded-xl bg-[#E6F4EE] text-[#0F5F4A] flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                    <span className="material-symbols-outlined text-[22px]">{zone.icon}</span>
                  </div>
                  <div>
                    <h3 className="font-semibold text-sm text-[#121E1A] group-hover:text-[#0F5F4A] transition-colors">
                      {zone.name}
                    </h3>
                    <span className="text-xs text-gray-500">{zone.count}</span>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </main>

      <FilterModal isOpen={isFilterOpen} onClose={() => setIsFilterOpen(false)} />
    </SiteLayout>
  );
}
