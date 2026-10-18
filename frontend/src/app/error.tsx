"use client";

import { useEffect } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log unexpected client/render errors for debugging
    console.error("Global application error caught:", error);
  }, [error]);

  const isNetworkError =
    error?.message?.toLowerCase().includes("fetch") ||
    error?.message?.toLowerCase().includes("network") ||
    error?.message?.toLowerCase().includes("connection") ||
    error?.message?.toLowerCase().includes("failed");

  return (
    <SiteLayout className="bg-[#FAF8F4] flex flex-col min-h-screen">
      <main className="flex-1 max-w-[1000px] w-full mx-auto px-4 py-16 sm:py-24 flex flex-col items-center justify-center text-center">
        {/* Error Icon */}
        <div className="w-20 h-20 rounded-3xl bg-[#FEF2F2] border border-[#FEE2E2] text-[#DC2626] flex items-center justify-center mb-6 shadow-md">
          <span className="material-symbols-outlined text-[44px]">
            {isNetworkError ? "cloud_off" : "warning"}
          </span>
        </div>

        {/* Title */}
        <h1 className="font-['Plus_Jakarta_Sans'] font-extrabold text-2xl sm:text-3xl text-[#121E1A] tracking-tight mb-2">
          {isNetworkError
            ? "Không thể kết nối đến hệ thống máy chủ"
            : "Đã xảy ra lỗi không mong muốn"}
        </h1>

        <p className="text-sm sm:text-base text-[#4A5550] max-w-lg mb-4 leading-relaxed">
          {isNetworkError
            ? "Ứng dụng không thể kết nối hoặc nhận phản hồi từ máy chủ Backend. Bạn vui lòng kiểm tra lại dịch vụ Backend hoặc thử lại sau."
            : "Hệ thống gặp sự cố khi xử lý tác vụ của bạn. Vui lòng bấm thử lại hoặc quay về trang chủ."}
        </p>

        {error?.message && (
          <div className="w-full max-w-lg p-3 rounded-xl bg-gray-100 border border-gray-200 text-left font-mono text-xs text-gray-700 mb-6 overflow-x-auto">
            <span className="font-bold text-red-600 block mb-1">Chi tiết lỗi:</span>
            {error.message}
          </div>
        )}

        {/* Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => reset()}
            className="inline-flex items-center gap-2 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white px-6 py-3 text-sm font-bold shadow-sm transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
            <span>Thử lại</span>
          </button>

          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full border border-[#0F5F4A] bg-white hover:bg-[#E6F4EE] text-[#0F5F4A] px-6 py-3 text-sm font-bold shadow-xs transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[18px]">home</span>
            <span>Về trang chủ</span>
          </Link>
        </div>
      </main>
    </SiteLayout>
  );
}
