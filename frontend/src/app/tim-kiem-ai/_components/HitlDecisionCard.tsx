"use client";

import React, { useEffect, useState } from "react";
import type { HitlOption, HitlProposal } from "@/app/tim-kiem-ai/types";

interface HitlDecisionCardProps {
  proposal?: HitlProposal | null;
  followUpQuestions?: string[];
  selectedAction?: string;
  isLocked?: boolean;
  onSelect: (actionText: string) => void;
}

/**
 * Phân tích và sinh danh sách options chuẩn Claude UI từ followUpQuestions
 * trong trường hợp đối tượng HitlProposal bị thiếu hoặc chưa có đầy đủ metadata.
 */
function synthesizeOptionsFromQuestions(questions: string[]): HitlOption[] {
  return questions.map((q, idx) => {
    const isAgree = q.startsWith("👍") || q.includes("nới ngân sách") || q.includes("Nới ngân sách");
    const isLocation = q.startsWith("🧭") || q.includes("Mở rộng") || q.includes("bán kính");
    const isDorm = q.startsWith("🛌") || q.includes("ký túc xá") || q.includes("Sleepbox");
    const isAmenity = q.startsWith("🪄") || q.includes("tiện ích");
    const isKeep = q.startsWith("❌") || q.includes("Giữ nguyên");
    const isCustom = q.startsWith("✏️") || q.includes("Tùy chỉnh");

    if (isAgree) {
      return {
        id: `opt_agree_${idx}`,
        type: "budget",
        title: "Điều chỉnh ngân sách tìm kiếm",
        description: "Nới ngân sách theo mặt bằng giá thực tế để tiếp cận nhiều phòng chất lượng hơn",
        badge: "Đề xuất tối ưu",
        badge_color: "emerald",
        action_text: q,
        highlight: true,
      };
    }
    if (isLocation) {
      return {
        id: `opt_loc_${idx}`,
        type: "location",
        title: "Mở rộng phạm vi tìm kiếm",
        description: "Tìm kiếm ở các khu vực hoặc bán kính lân cận có mức giá mềm hơn",
        badge: "Giữ ngân sách",
        badge_color: "blue",
        action_text: q,
      };
    }
    if (isDorm) {
      return {
        id: `opt_dorm_${idx}`,
        type: "room_type",
        title: "Ký túc xá / Ở ghép (Sleepbox)",
        description: "Phương án khả thi cho ngân sách tiết kiệm dưới 2 triệu/tháng",
        badge: "Tiết kiệm chi phí",
        badge_color: "amber",
        action_text: q,
      };
    }
    if (isAmenity) {
      return {
        id: `opt_amenity_${idx}`,
        type: "amenity",
        title: "Lược bớt yêu cầu tiện ích",
        description: "Giảm bớt tiêu chí phòng để tìm được các mức giá cơ bản tốt hơn",
        badge: "Tối ưu bộ lọc",
        badge_color: "purple",
        action_text: q,
      };
    }
    if (isKeep) {
      return {
        id: `opt_keep_${idx}`,
        type: "keep",
        title: "Giữ nguyên tiêu chí của tôi",
        description: "Lưu lại tiêu chí và kết thúc đề xuất nới lỏng, chờ khi có phòng mới đăng tải",
        badge: "Kết thúc nới lỏng",
        badge_color: "slate",
        action_text: q,
      };
    }
    if (isCustom) {
      return {
        id: `opt_custom_${idx}`,
        type: "custom",
        title: "Tùy chỉnh tiêu chí khác",
        description: "Nhập trực tiếp khu vực mới, khoảng giá hoặc tiêu chí khác vào ô chat",
        badge: "Linh hoạt",
        badge_color: "orange",
        action_text: q,
      };
    }

    return {
      id: `opt_misc_${idx}`,
      type: "general",
      title: q,
      description: "Lựa chọn hành động tiếp theo",
      action_text: q,
    };
  });
}

function getBadgeStyle(color?: string) {
  switch (color) {
    case "emerald":
      return "bg-emerald-50 text-emerald-800 border-emerald-200";
    case "blue":
      return "bg-sky-50 text-sky-800 border-sky-200";
    case "amber":
      return "bg-amber-50 text-amber-800 border-amber-200";
    case "purple":
      return "bg-purple-50 text-purple-800 border-purple-200";
    case "orange":
      return "bg-orange-50 text-orange-800 border-orange-200";
    case "slate":
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

function getIconForType(type?: string) {
  switch (type) {
    case "budget":
      return { icon: "payments", bg: "bg-emerald-50 text-[#0F5F4A] border-emerald-200" };
    case "location":
      return { icon: "explore", bg: "bg-sky-50 text-sky-700 border-sky-200" };
    case "room_type":
      return { icon: "bed", bg: "bg-amber-50 text-amber-700 border-amber-200" };
    case "amenity":
      return { icon: "tune", bg: "bg-purple-50 text-purple-700 border-purple-200" };
    case "keep":
      return { icon: "bookmark_border", bg: "bg-slate-100 text-slate-600 border-slate-200" };
    case "custom":
      return { icon: "edit_note", bg: "bg-orange-50 text-orange-700 border-orange-200" };
    default:
      return { icon: "touch_app", bg: "bg-slate-50 text-slate-600 border-slate-200" };
  }
}

export function HitlDecisionCard({
  proposal,
  followUpQuestions = [],
  selectedAction,
  isLocked = false,
  onSelect,
}: HitlDecisionCardProps) {
  const [chosenAction, setChosenAction] = useState<string | null>(selectedAction || null);

  const options: HitlOption[] =
    proposal?.options && proposal.options.length > 0
      ? proposal.options
      : synthesizeOptionsFromQuestions(followUpQuestions);

  const hasChosen = Boolean(chosenAction || selectedAction);
  const isResolved = Boolean(hasChosen || isLocked);
  const [isExpanded, setIsExpanded] = useState<boolean>(!hasChosen);

  useEffect(() => {
    if (selectedAction) {
      setChosenAction(selectedAction);
      setIsExpanded(false);
    }
  }, [selectedAction]);

  if (!options || options.length === 0) return null;

  const isMarketGap = proposal?.is_market_gap;
  const marketMessage = proposal?.message;

  const handleSelect = (actionText: string) => {
    if (isResolved) return;
    setChosenAction(actionText);
    setIsExpanded(false);
    onSelect(actionText);
  };

  const selectedOption = options.find(
    (opt) =>
      opt.action_text === chosenAction ||
      opt.title === chosenAction ||
      (chosenAction && (chosenAction.includes(opt.title) || opt.action_text.includes(chosenAction)))
  );

  // Trạng thái thu gọn (Collapsed View) sau khi đã chọn
  if (hasChosen && !isExpanded) {
    const displayTitle = selectedOption?.title || chosenAction || "Đã xác nhận phương án";

    return (
      <div className="my-2.5 overflow-hidden rounded-xl border border-emerald-200/90 bg-gradient-to-r from-emerald-50/70 via-[#F7FCF9] to-white p-2.5 sm:px-3.5 shadow-2xs transition-all duration-200">
        <div className="flex items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white shadow-2xs">
              <span className="material-symbols-outlined text-[15px]">check</span>
            </span>
            <div className="flex items-center gap-2 min-w-0 flex-wrap">
              <span className="text-[11px] font-semibold text-slate-500 shrink-0">
                Lựa chọn của bạn:
              </span>
              <span className="text-[12px] font-bold text-emerald-950 truncate max-w-[240px] sm:max-w-none">
                {displayTitle}
              </span>
              {selectedOption?.badge && (
                <span className="inline-block rounded-md border border-emerald-300 bg-emerald-100/90 px-1.5 py-0.5 text-[9.5px] font-bold text-emerald-800 shrink-0">
                  {selectedOption.badge}
                </span>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 transition-all shadow-2xs shrink-0 cursor-pointer"
            title="Mở rộng để xem lại chi tiết các đề xuất"
          >
            <span>Chi tiết</span>
            <span className="material-symbols-outlined text-[15px] text-slate-500">expand_more</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`my-3 overflow-hidden rounded-2xl border transition-all ${
        isResolved
          ? "border-slate-200/60 bg-[#FAFAFA] opacity-95"
          : "border-slate-200/90 bg-gradient-to-b from-white via-[#FCFDFC] to-[#F8FAFA] shadow-xs"
      }`}
    >
      {/* Header bar phong cách Claude Confirmation Card */}
      <div className="flex flex-col gap-1.5 border-b border-slate-100 bg-[#FBFDFB] px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-md ${
                isResolved
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-[#0F5F4A]/10 text-[#0F5F4A]"
              }`}
            >
              <span className="material-symbols-outlined text-[15px]">
                {isResolved ? "check_circle" : "tune"}
              </span>
            </span>
            <span className="text-[12px] font-bold text-slate-900 tracking-tight">
              {proposal?.title || "Homigo AI · Cần xác nhận phương án"}
            </span>
          </div>

          {/* Badge trạng thái và nút thu gọn */}
          {hasChosen ? (
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/80 bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold tracking-wider text-emerald-800">
                <span className="material-symbols-outlined text-[12px] text-emerald-600">check</span>
                <span>Đã xác nhận</span>
              </span>
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-semibold text-slate-600 hover:bg-slate-50 transition-all cursor-pointer shadow-2xs"
                title="Thu gọn thẻ đề xuất"
              >
                <span>Thu gọn</span>
                <span className="material-symbols-outlined text-[14px]">expand_less</span>
              </button>
            </div>
          ) : isResolved ? (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
              <span>Đã đóng</span>
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/80 bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-800">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span>Human-in-the-loop</span>
            </span>
          )}
        </div>

        <p className="text-[11px] text-slate-500 leading-normal">
          {isResolved
            ? "Bạn đã phản hồi phương án này. Lựa chọn đã được ghi nhận và đóng lại."
            : "Không có phòng đáp ứng 100% tiêu chí ban đầu. Vui lòng chọn một phương án dưới đây để Homigo tìm kiếm lại cho bạn."}
        </p>
      </div>

      {/* Market Insight Callout: Hiển thị khi ngân sách người dùng chênh lệch lớn so với giá sàn thực tế */}
      {(isMarketGap || marketMessage) && (
        <div className="m-3 rounded-xl border border-amber-200/90 bg-gradient-to-r from-amber-50/90 to-orange-50/60 p-3 text-amber-950 shadow-2xs">
          <div className="flex items-start gap-2.5">
            <span className="material-symbols-outlined shrink-0 text-[18px] text-amber-600 pt-0.5">
              trending_up
            </span>
            <div className="space-y-1.5 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11.5px] font-bold text-amber-900">
                  Thực tế thị trường {proposal?.area_name ? `tại ${proposal.area_name}` : ""}
                </span>
                {proposal?.market_min_price_str && (
                  <span className="rounded bg-amber-100/90 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 border border-amber-200">
                    Giá sàn: ~{proposal.market_min_price_str}
                  </span>
                )}
                {proposal?.user_budget_str && (
                  <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-700 border border-rose-200">
                    Bạn nhập: {proposal.user_budget_str}
                  </span>
                )}
              </div>
              <p className="text-[11px] leading-relaxed text-amber-900/90">
                {marketMessage ||
                  `Mức ngân sách bạn tìm kiếm hiện thấp hơn giá sàn ghi nhận tại khu vực này. Homigo đề xuất điều chỉnh ngân sách sát thực tế hoặc chuyển sang mô hình phòng phù hợp hơn.`}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Grid danh sách Options chuẩn Claude Confirmation Cards */}
      <div className="p-3 pt-1 space-y-2">
        {options.map((opt) => {
          const { icon, bg } = getIconForType(opt.type);
          const badgeClass = getBadgeStyle(opt.badge_color);

          const isSelected = chosenAction === opt.action_text;
          const isOther = Boolean(chosenAction && !isSelected);

          return (
            <button
              key={opt.id}
              type="button"
              disabled={isResolved}
              onClick={() => handleSelect(opt.action_text)}
              className={`group w-full text-left rounded-xl border p-3 transition-all duration-200 flex items-start gap-3 relative ${
                isSelected
                  ? "border-emerald-500 bg-emerald-50/70 shadow-xs ring-2 ring-emerald-500/20 cursor-default"
                  : isOther || isLocked
                  ? "border-slate-100 bg-slate-50/50 opacity-45 cursor-not-allowed pointer-events-none"
                  : opt.highlight
                  ? "border-[#0F5F4A]/40 bg-gradient-to-r from-[#F0FDF8] via-white to-white hover:border-[#0F5F4A] hover:shadow-sm cursor-pointer"
                  : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/70 hover:shadow-2xs cursor-pointer"
              }`}
            >
              {/* Cột trái: Icon chủ đề */}
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-transform duration-200 ${
                  isSelected ? "scale-105 border-emerald-300 bg-emerald-100 text-emerald-800" : bg
                }`}
              >
                <span className="material-symbols-outlined text-[17px]">
                  {isSelected ? "check" : icon}
                </span>
              </div>

              {/* Cột giữa: Tiêu đề + Badge + Mô tả */}
              <div className="flex-1 min-w-0 pr-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`text-[12px] font-bold transition-colors ${
                      isSelected
                        ? "text-emerald-900"
                        : isOther
                        ? "text-slate-500"
                        : "text-slate-800 group-hover:text-[#0F5F4A]"
                    }`}
                  >
                    {opt.title}
                  </span>
                  {opt.badge && (
                    <span
                      className={`inline-block rounded-md border px-1.5 py-0.5 text-[9.5px] font-semibold tracking-tight ${
                        isSelected
                          ? "bg-emerald-100 text-emerald-900 border-emerald-300"
                          : badgeClass
                      }`}
                    >
                      {opt.badge}
                    </span>
                  )}
                </div>

                <p
                  className={`mt-0.5 text-[11px] leading-snug ${
                    isSelected ? "text-emerald-800 font-medium" : "text-slate-500"
                  }`}
                >
                  {opt.description}
                </p>
              </div>

              {/* Cột phải: Nút action indicator */}
              <div className="flex shrink-0 items-center self-center pl-1">
                {isSelected ? (
                  <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 text-white px-2.5 py-1 text-[11px] font-bold shadow-xs">
                    <span className="material-symbols-outlined text-[13px]">check</span>
                    <span>Đã chọn</span>
                  </span>
                ) : isResolved ? (
                  <span className="text-[10px] text-slate-400 font-medium italic">
                    Đã đóng
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-0.5 rounded-lg border border-transparent px-2 py-1 text-[11px] font-semibold text-[#0F5F4A] group-hover:border-[#0F5F4A]/20 group-hover:bg-[#0F5F4A]/5 transition-all">
                    <span>Chọn</span>
                    <span className="material-symbols-outlined text-[14px] transition-transform duration-200 group-hover:translate-x-0.5">
                      arrow_forward
                    </span>
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
