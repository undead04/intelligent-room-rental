import type { RoomItem } from "@/app/tim-kiem-ai/types";

interface AgentInsightPanelProps {
  room: RoomItem;
}

export default function AgentInsightPanel({ room }: AgentInsightPanelProps) {
  return (
    <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col flex-1 overflow-hidden">
      <div className="px-4 py-2.5 border-b border-[#E8E4DC] flex items-center justify-between bg-white">
        <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
          <span>4. Phân tích & giải thích của Agent</span>
        </h2>
        <span className="text-[10px] text-[#0F5F4A] bg-[#E6F4EE] font-bold px-2 py-0.5 rounded-full">
          AI Logic
        </span>
      </div>

      <div className="flex-1 p-3.5 overflow-y-auto space-y-3 text-xs bg-[#FAFBF9]">
        {/* Insight Box 1: Why #1 ranked top */}
        <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-2">
          <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold">
            <span className="text-[#FF6B4A]">💡</span>
            <span>Vì sao phòng #{room.rank} ({room.title}) được đề xuất?</span>
          </div>
          <ul className="text-[11px] text-[#3F4944] space-y-1.5 pl-1 leading-relaxed">
            <li className="flex items-start gap-1.5">
              <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
              <span>
                <strong className="text-[#121E1A]">Gần UIT nhất:</strong> {room.distance}, lộ trình an toàn ít tắc xe.
              </span>
            </li>
            <li className="flex items-start gap-1.5">
              <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
              <span>
                <strong className="text-[#121E1A]">Đầy đủ điều kiện bắt buộc:</strong> Giá {room.price} (đạt ≤ 5tr), có sẵn máy lạnh Inverter & gác đúc cao.
              </span>
            </li>
            <li className="flex items-start gap-1.5">
              <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
              <span>
                <strong className="text-[#121E1A]">Phòng mới & nội thất hiện đại:</strong> Tòa nhà hoàn công mới, được cộng thêm 15 điểm ưu tiên.
              </span>
            </li>
            <li className="flex items-start gap-1.5">
              <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
              <span>
                <strong className="text-[#121E1A]">Chi phí phụ thấp minh bạch:</strong> Đồng hồ điện nước riêng, phí dịch vụ chỉ 80k/tháng.
              </span>
            </li>
          </ul>
        </div>

        {/* Insight Box 2: Quick comparison with #2 */}
        <div className="bg-white rounded-xl p-3 border border-[#E8E4DC] shadow-2xs space-y-1.5">
          <div className="flex items-center gap-1.5 text-[#0F5F4A] font-bold">
            <span className="text-[#0F5F4A]">🧭</span>
            <span>So sánh nhanh với phòng #2</span>
          </div>
          <p className="text-[11px] text-[#3F4944] font-medium leading-relaxed">
            Phòng #2 có giá 4.8tr và gần hơn (800m), tuy nhiên phòng #1 vẫn được ưu tiên xếp đầu bảng vì:
          </p>
          <ul className="text-[11px] text-[#3F4944] space-y-1 pl-4 list-disc leading-relaxed">
            <li>Tiết kiệm hơn <strong className="text-[#121E1A]">300.000đ/tháng</strong> (tổng 3.6 triệu/năm).</li>
            <li>Phòng mới bàn giao, gác cao đứng thẳng không bị chạm đầu.</li>
            <li>Diện tích sử dụng rộng rãi hơn (<strong className="text-[#121E1A]">25m² vs 20m²</strong>).</li>
          </ul>
        </div>
      </div>
    </div>
  );
}