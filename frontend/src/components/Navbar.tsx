"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Navbar() {
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const navItems = [
    { label: "Trang chủ", href: "/", icon: "home" },
    { label: "Tìm kiếm", href: "/tim-kiem", icon: "search" },
    { label: "Tìm với AI", href: "/tim-kiem-ai", icon: "auto_awesome" },
    { label: "Giá trọ", href: "/tra-cuu-gia-tro", icon: "bar_chart" },
  ];

  return (
    <header className="sticky top-0 z-50 w-full bg-white/95 backdrop-blur-md border-b border-[#E8E4DC] shadow-[0_1px_8px_rgba(0,0,0,0.03)]">
      <div className="h-[72px] max-w-[1500px] mx-auto px-4 lg:px-8 flex items-center justify-between gap-4">
        {/* Logo */}
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 group">
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-xl bg-[#0F5F4A] flex items-center justify-center text-white shadow-sm transition-transform group-hover:scale-105">
                <span className="material-symbols-outlined text-[24px]">apartment</span>
              </div>
              <div className="flex flex-col">
                <span className="font-['Plus_Jakarta_Sans'] font-extrabold text-[22px] tracking-tight text-[#0F5F4A] leading-none">
                  Homigo<span className="text-[#FF6B4A]">.</span>
                </span>
                <span className="text-[10px] text-gray-500 font-medium tracking-wider uppercase">Marketplace</span>
              </div>
            </div>
          </Link>
        </div>

        {/* Center Nav for Desktop */}
        <nav className="hidden lg:flex items-center gap-1.5 p-1.5 bg-[#EEF4F1] rounded-full border border-[#D8E4DF] shadow-inner">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href + "/"));

            return (
              <Link
                key={item.label}
                href={item.href}
                className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full transition-all text-xs sm:text-sm font-semibold ${
                  isActive
                    ? "bg-[#0F5F4A] text-white shadow-[0_2px_8px_rgba(15,95,74,0.3)] font-bold scale-[1.02]"
                    : "text-[#4A5550] hover:text-[#0F5F4A] hover:bg-white hover:shadow-xs active:scale-95"
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[18px] transition-colors ${
                    isActive ? "text-[#A9F1D5]" : "text-[#6F7974] group-hover:text-[#0F5F4A]"
                  }`}
                >
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Right Actions */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Link
            href="/tim-kiem"
            className="relative flex items-center justify-center w-10 h-10 rounded-full border border-[#E8E4DC] bg-white text-[#3F4944] hover:text-[#0F5F4A] hover:border-[#0F5F4A] hover:bg-[#E6F4EE]/40 transition-all shadow-sm cursor-pointer"
            title="Khám phá phòng trọ"
          >
            <span className="material-symbols-outlined text-[20px]">search</span>
          </Link>

          <div className="hidden sm:flex items-center gap-2.5 pl-1.5 pr-3 py-1.5 rounded-full border border-[#E8E4DC] bg-white hover:bg-[#EEF4F1] hover:border-[#0F5F4A]/40 transition-all cursor-pointer shadow-sm">
            <div className="w-8 h-8 rounded-full overflow-hidden bg-[#E6F4EE] border border-[#0F5F4A]/20 flex items-center justify-center text-[#0F5F4A]">
              <span className="material-symbols-outlined text-[20px]">account_circle</span>
            </div>
            <span className="text-xs font-semibold text-[#121E1A]">Tài khoản</span>
          </div>

          {/* Mobile Menu Hamburger Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="flex lg:hidden items-center justify-center w-10 h-10 rounded-full border border-[#E8E4DC] bg-white text-[#3F4944] hover:text-[#0F5F4A] hover:bg-[#E6F4EE]/40 transition-all shadow-sm cursor-pointer"
            aria-label="Mở menu điều hướng"
          >
            <span className="material-symbols-outlined text-[22px]">
              {mobileMenuOpen ? "close" : "menu"}
            </span>
          </button>
        </div>
      </div>

      {/* Mobile Menu Dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden border-t border-[#E8E4DC] bg-white px-4 py-3 shadow-lg animate-in slide-in-from-top-2 duration-200">
          <div className="flex flex-col gap-1">
            {navItems.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href + "/"));

              return (
                <Link
                  key={item.label}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all ${
                    isActive
                      ? "bg-[#E6F4EE] text-[#0F5F4A] font-bold"
                      : "text-[#4A5550] hover:bg-[#FAF8F4] hover:text-[#0F5F4A]"
                  }`}
                >
                  <span className="material-symbols-outlined text-[20px] text-[#0F5F4A]">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </header>
  );
}
