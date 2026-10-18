import type { DecisionInsight, RoomItem } from "@/app/tim-kiem-ai/types";

interface AgentInsightPanelProps {
  room?: RoomItem | null;
  insights?: DecisionInsight | null;
}

export default function AgentInsightPanel({ room, insights }: AgentInsightPanelProps) {
  const hasDynamicFactors = insights?.key_factors && insights.key_factors.length > 0;
  const hasTradeOffs = insights?.trade_offs && insights.trade_offs.length > 0;
  const hasChecklist = insights?.verification_checklist && insights.verification_checklist.length > 0;

  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col flex-1 min-h-0 overflow-hidden">
      <div className="px-4 py-2 border-b border-[#E8E4DC] flex items-center justify-between bg-white shrink-0">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>4. Phân tích & giải thích của Agent</span>
        </h2>
        <span className="text-[10px] text-[#0F5F4A] bg-[#E6F4EE] font-bold px-2 py-0.5 rounded-full">
          MCDM AI Logic
        </span>
      </div>

      {!room ? (
        <div className="flex-1 p-5 overflow-y-auto bg-[#FAFBF9] flex flex-col items-center justify-center text-center">
          <div className="w-12 h-12 rounded-2xl bg-[#E6F4EE] border border-[#0F5F4A]/20 flex items-center justify-center text-[#0F5F4A] mb-3 shadow-xs">
            <span className="material-symbols-outlined text-[24px]">psychology</span>
          </div>
          <h3 className="text-xs font-bold text-[#121E1A] mb-1">
            Chưa chọn phòng trọ
          </h3>
          <p className="text-[11px] text-[#6F7974] max-w-[270px] leading-relaxed mb-4">
            Khi AI gợi ý kết quả, chọn một phòng bất kỳ để xem phân tích chi tiết của hệ thống MCDM:
          </p>
          <div className="w-full max-w-[290px] space-y-2 text-left">
            <div className="bg-white p-2.5 rounded-xl border border-[#E8E4DC] flex items-start gap-2 shadow-2xs">
              <span className="text-[14px]">💡</span>
              <div className="text-[10px]">
                <strong className="text-[#0F5F4A]">Lý do đề xuất:</strong> Tiêu chí khớp nhu cầu và điểm tương thích.
              </div>
            </div>
            <div className="bg-white p-2.5 rounded-xl border border-[#E8E4DC] flex items-start gap-2 shadow-2xs">
              <span className="text-[14px]">🧭</span>
              <div className="text-[10px]">
                <strong className="text-[#0F5F4A]">Phân tích đánh đổi:</strong> So sánh ưu và nhược điểm so với các phòng khác.
              </div>
            </div>
            <div className="bg-white p-2.5 rounded-xl border border-[#E8E4DC] flex items-start gap-2 shadow-2xs">
              <span className="text-[14px]">📋</span>
              <div className="text-[10px]">
                <strong className="text-[#D97706]">Checklist kiểm tra:</strong> Những điểm cần hỏi và kiểm tra thực tế khi xem phòng.
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 p-3.5 overflow-y-auto space-y-3 text-xs bg-[#FAFBF9]">
        {/* Insight Box 1: Why this room is recommended */}
        <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-2">
          <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold">
            <span className="text-[#FF6B4A]">💡</span>
            <span>Vì sao phòng #{room.rank} ({room.title}) được đề xuất?</span>
          </div>

          {room.rank === 1 && insights?.top_1_reason ? (
            <p className="text-[11px] text-[#121E1A] font-medium leading-relaxed bg-[#E6F4EE]/60 p-2 rounded-lg border border-[#0F5F4A]/10">
              {insights.top_1_reason}
            </p>
          ) : null}

          <ul className="text-[11px] text-[#3F4944] space-y-1.5 pl-1 leading-relaxed">
            {hasDynamicFactors ? (
              insights.key_factors.map((factor, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">
                    check_circle
                  </span>
                  <span>{factor}</span>
                </li>
              ))
            ) : (
              <>
                <li className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">
                    check_circle
                  </span>
                  <span>
                    <strong className="text-[#121E1A]">Vị trí thuận tiện:</strong> {room.distance}, thuận lợi di chuyển.
                  </span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">
                    check_circle
                  </span>
                  <span>
                    <strong className="text-[#121E1A]">Mức giá tối ưu:</strong> {room.price}, độ tương thích ngân sách cao.
                  </span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">
                    check_circle
                  </span>
                  <span>
                    <strong className="text-[#121E1A]">Đầy đủ tiện nghi:</strong> {room.tags.join(" • ") || "Đạt chuẩn an cư sinh viên"}.
                  </span>
                </li>
              </>
            )}
          </ul>
        </div>

        {/* Insight Box 2: Quick comparison / Trade-off analysis */}
        <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-1.5">
          <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold">
            <span className="text-[#0F5F4A]">🧭</span>
            <span>Phân tích đối sánh đánh đổi (Trade-off)</span>
          </div>

          {hasTradeOffs ? (
            <div className="space-y-2 pt-1">
              {insights.trade_offs.map((to, idx) => (
                <div key={idx} className="text-[11px] space-y-1 border-b border-gray-100 pb-2 last:border-b-0 last:pb-0">
                  <div className="font-semibold text-[#121E1A]">So sánh với {to.compared_with}:</div>
                  <div className="flex items-start gap-1 text-[#0F5F4A]">
                    <span className="font-bold text-[12px]">▲</span>
                    <span><strong>Ưu điểm:</strong> {to.advantage}</span>
                  </div>
                  <div className="flex items-start gap-1 text-[#D97706]">
                    <span className="font-bold text-[12px]">▼</span>
                    <span><strong>Cân nhắc:</strong> {to.disadvantage}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <>
              <p className="text-[11px] text-[#3F4944] font-medium leading-relaxed">
                So với các lựa chọn khác trong cùng tầm giá:
              </p>
              <ul className="text-[11px] text-[#3F4944] space-y-1 pl-4 list-disc leading-relaxed">
                <li>Ưu tiên tối đa khả năng tiếp cận và tiết kiệm chi phí đi lại.</li>
                <li>Không gian phòng thoáng mát, trang thiết bị cơ bản đã được lắp sẵn.</li>
                <li>Hợp đồng minh bạch, xác thực thông tin chính chủ.</li>
              </ul>
            </>
          )}
        </div>

        {/* Insight Box 3: Verification Checklist */}
        {hasChecklist && (
          <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-1.5">
            <div className="flex items-center gap-1.5 text-[#D97706] font-bold">
              <span>📋</span>
              <span>Checklist lưu ý khi đi xem phòng</span>
            </div>
            <ul className="text-[11px] text-[#3F4944] space-y-1 pl-1 leading-relaxed">
              {insights.verification_checklist.map((item, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[13px] text-[#D97706] mt-0.5 shrink-0">
                    info
                  </span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      )}
    </div>
  );
}