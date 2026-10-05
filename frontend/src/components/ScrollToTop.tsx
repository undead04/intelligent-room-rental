"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

export default function ScrollToTop() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isRestoringHistory = useRef(false);

  useEffect(() => {
    const handlePopState = () => {
      isRestoringHistory.current = true;
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    // Nút back/forward: giữ vị trí cuộn mà Next.js đã khôi phục
    if (isRestoringHistory.current) {
      isRestoringHistory.current = false;
      return;
    }

    // Có anchor trong URL: để trình duyệt cuộn tới anchor
    if (window.location.hash) return;

    window.scrollTo(0, 0);
  }, [pathname, searchParams]);

  return null;
}
