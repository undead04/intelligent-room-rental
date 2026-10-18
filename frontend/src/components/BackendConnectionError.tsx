"use client";

interface BackendConnectionErrorProps {
  message?: string | null;
  onRetry?: () => void;
  variant?: "full" | "banner";
  serviceName?: string;
  port?: number | string;
  className?: string;
}

export default function BackendConnectionError({
  message,
  onRetry,
  variant = "full",
  serviceName = "Backend Server (FastAPI)",
  port = "8000",
  className = "",
}: BackendConnectionErrorProps) {
  const isNetworkOrDown =
    !message ||
    message.includes("fetch") ||
    message.includes("connect") ||
    message.includes("500") ||
    message.includes("Failed to fetch") ||
    message.includes("kết nối");

  const displayMessage =
    message || "Không thể kết nối đến máy chủ dữ liệu. Vui lòng thử lại sau.";

  if (variant === "banner") {
    return (
      <div
        className={`w-full rounded-2xl border border-amber-300 bg-amber-50/90 p-4 text-[#854D0E] shadow-xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${className}`}
      >
        <div className="flex items-start gap-2.5">
          <span className="material-symbols-outlined text-amber-600 text-[22px] shrink-0 mt-0.5">
            cloud_off
          </span>
          <div>
            <div className="text-xs font-bold text-[#78350F]">
              Mất kết nối {serviceName} (Port {port})
            </div>
            <div className="text-[11px] text-[#92400E] mt-0.5 leading-relaxed">
              {displayMessage}
            </div>
          </div>
        </div>

        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold transition shadow-2xs cursor-pointer"
          >
            <span className="material-symbols-outlined text-[15px]">refresh</span>
            <span>Thử lại</span>
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={`w-full rounded-3xl border border-[#F3E8E2] bg-white p-6 sm:p-8 text-center shadow-xs flex flex-col items-center justify-center my-6 ${className}`}
    >
      {/* Icon */}
      <div className="w-16 h-16 rounded-3xl bg-[#FEF2F2] border border-[#FEE2E2] text-[#DC2626] flex items-center justify-center mb-4 shadow-sm">
        <span className="material-symbols-outlined text-[32px]">
          {isNetworkOrDown ? "cloud_off" : "error_outline"}
        </span>
      </div>

      {/* Heading */}
      <h3 className="font-['Plus_Jakarta_Sans'] font-extrabold text-base sm:text-lg text-[#121E1A] mb-1.5">
        Không thể kết nối đến {serviceName}
      </h3>

      <p className="text-xs sm:text-sm text-[#4A5550] max-w-md mx-auto mb-4 leading-relaxed">
        {displayMessage}
      </p>

      {/* Developer note (helpful for local dev and grading) */}
      <div className="w-full max-w-md bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl p-3 text-left mb-6 text-[11px] text-[#4A5550] space-y-1">
        <div className="flex items-center gap-1.5 font-bold text-[#0F5F4A]">
          <span className="material-symbols-outlined text-[15px]">terminal</span>
          <span>Kiểm tra dịch vụ máy chủ:</span>
        </div>
        <p className="text-[#6F7974] leading-relaxed">
          Đảm bảo Backend API đang chạy tại <code className="bg-[#E6F4EE] text-[#0F5F4A] px-1.5 py-0.5 rounded font-mono font-bold">http://localhost:{port}</code>.
        </p>
        <p className="font-mono text-[10px] bg-gray-100 text-gray-800 p-1.5 rounded border border-gray-200 overflow-x-auto">
          cd backend &amp;&amp; uvicorn main:app --port {port} --reload
        </p>
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap items-center justify-center gap-2.5">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#0F5F4A] hover:bg-[#004635] text-white px-5 py-2.5 text-xs font-bold transition shadow-xs cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">refresh</span>
            <span>Thử lại kết nối</span>
          </button>
        )}
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-1.5 rounded-full border border-[#DCECE4] bg-white hover:bg-[#F1FBF6] text-[#0F5F4A] px-5 py-2.5 text-xs font-bold transition shadow-2xs cursor-pointer"
        >
          <span className="material-symbols-outlined text-[16px]">sync</span>
          <span>Tải lại trang</span>
        </button>
      </div>
    </div>
  );
}
