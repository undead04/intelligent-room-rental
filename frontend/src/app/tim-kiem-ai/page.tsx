"use client";

import { useState } from "react";
import Link from "next/link";
import SiteLayout from "@/components/SiteLayout";

interface RoomItem {
  id: string;
  rank: number;
  rankText: string;
  matchScore: number;
  title: string;
  price: string;
  priceNum: number;
  address: string;
  distance: string;
  photoCount: number;
  image: string;
  tags: string[];
  latPercent: number; // for map pin positioning
  lngPercent: number;
}

interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  avatar?: string;
  mandatoryCriteria?: string[];
  priorityCriteria?: string[];
  summaryCount?: number;
}

export default function AIChatWorkspacePage() {
  const [selectedRoomId, setSelectedRoomId] = useState<string>("room-1");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [inputVal, setInputVal] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "msg-1",
      sender: "user",
      text: "Tìm phòng dưới 5 triệu, gần UIT, có máy lạnh, có gác, ưu tiên phòng mới.",
      avatar: "/stitch/1_avatar_user_317ba717e1464aafbe096f8b685c3790.png",
    },
    {
      id: "msg-2",
      sender: "ai",
      text: "Mình hiểu nhu cầu của bạn:",
      mandatoryCriteria: ["Giá ≤ 5 triệu", "Gần UIT", "Có máy lạnh"],
      priorityCriteria: ["Phòng mới", "Có gác"],
      summaryCount: 18,
    },
  ]);

  const rooms: RoomItem[] = [
    {
      id: "room-1",
      rank: 1,
      rankText: "Top 1",
      matchScore: 94,
      title: "Phòng trọ mới, có gác, máy lạnh",
      price: "4.500.000đ",
      priceNum: 4.5,
      address: "Đường Lê Văn Việt, P. Hiệp Phú, TP. Thủ Đức",
      distance: "1.2 km (~ 4 phút)",
      photoCount: 12,
      image: "https://images.unsplash.com/photo-1522771739844-6a9f6d5f14af?auto=format&fit=crop&w=600&q=80",
      tags: ["❄️ Máy lạnh", "🪜 Có gác", "🚿 WC riêng"],
      latPercent: 22,
      lngPercent: 24,
    },
    {
      id: "room-2",
      rank: 2,
      rankText: "Top 2",
      matchScore: 91,
      title: "Phòng có gác, máy lạnh, gần UIT",
      price: "4.800.000đ",
      priceNum: 4.8,
      address: "Đường Kha Vạn Cân, P. Linh Tây, TP. Thủ Đức",
      distance: "800 m (~ 3 phút)",
      photoCount: 10,
      image: "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=600&q=80",
      tags: ["❄️ Máy lạnh", "🪜 Có gác", "🛵 Giữ xe máy"],
      latPercent: 72,
      lngPercent: 18,
    },
    {
      id: "room-3",
      rank: 3,
      rankText: "Top 3",
      matchScore: 88,
      title: "Phòng mới, gác cao, có máy lạnh",
      price: "4.700.000đ",
      priceNum: 4.7,
      address: "Đường 22/12, P. Linh Trung, TP. Thủ Đức",
      distance: "1.1 km (~ 4 phút)",
      photoCount: 9,
      image: "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=600&q=80",
      tags: ["❄️ Máy lạnh", "🪜 Có gác", "🚿 WC riêng"],
      latPercent: 28,
      lngPercent: 76,
    },
  ];

  const selectedRoom = rooms.find((r) => r.id === selectedRoomId) || rooms[0];

  const handleSendMessage = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputVal.trim()) return;

    const userText = inputVal;
    setInputVal("");

    const newMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: "user",
      text: userText,
      avatar: "/stitch/1_avatar_user_317ba717e1464aafbe096f8b685c3790.png",
    };

    setMessages((prev) => [...prev, newMsg]);
    setIsTyping(true);

    setTimeout(() => {
      const aiMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: "ai",
        text: "Đã cập nhật tiêu chí mới của bạn:",
        mandatoryCriteria: ["Giá ≤ 5 triệu", "Gần UIT", "Có máy lạnh", "Giờ tự do 24/7"],
        priorityCriteria: ["Phòng mới", "Có gác", "An ninh tốt"],
        summaryCount: 14,
      };
      setMessages((prev) => [...prev, aiMsg]);
      setIsTyping(false);
    }, 900);
  };

  return (
    <SiteLayout className="bg-[#F8FAF8] text-[#121E1A] font-sans antialiased">
      {/* BREADCRUMB & CONTEXT HEADER */}
      <div className="w-full max-w-[1500px] mx-auto px-4 lg:px-8 pt-4 pb-1">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#E8E4DC] pb-3">
          <div>
            <div className="flex items-center gap-2 text-xs text-[#6F7974] mb-1 font-medium">
              <Link href="/" className="hover:text-[#0F5F4A] transition">Trang chủ</Link>
              <span>/</span>
              <span className="text-[#0F5F4A] font-semibold">Tìm với AI</span>
            </div>
            <h1 className="text-xl sm:text-2xl font-extrabold text-[#121E1A] tracking-tight flex items-center gap-2">
              <span className="w-7 h-7 rounded-xl bg-[#E6F4EE] text-[#0F5F4A] flex items-center justify-center text-sm">
                <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
              </span>
              <span>Không Gian Tìm Phòng Trọ Thông Minh</span>
            </h1>
            <p className="text-xs sm:text-sm text-[#3F4944] mt-0.5">
              Trợ lý trí tuệ nhân tạo Homigo phân tích tiêu chí cá nhân hóa và xếp hạng phòng tối ưu nhất theo thời gian thực.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#E6F4EE] border border-[#0F5F4A]/20 text-[#0F5F4A] text-xs font-bold shadow-2xs">
              <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-pulse"></span>
              <span>AI Agent đang hoạt động</span>
            </span>
          </div>
        </div>
      </div>

      {/* MAIN WORKSPACE LAYOUT (Strict 3-Column / 4-Panel Layout matching Stitch Design) */}
      <main className="flex-1 px-4 lg:px-8 py-3 max-w-[1500px] w-full mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 h-auto lg:h-[720px]">
          {/* ========================================== */}
          {/* COLUMN 1: CHAT / NHẬP YÊU CẦU (Col span 4) */}
          {/* ========================================== */}
          <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[600px] lg:h-full overflow-hidden">
            {/* Section Header */}
            <div className="p-3.5 px-4 border-b border-[#E8E4DC] flex items-center justify-between bg-white">
              <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
                <span>1. Chat / Nhập yêu cầu</span>
              </h2>
              <span className="text-[11px] font-semibold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full">
                AI Assistant
              </span>
            </div>

            {/* Chat Conversation Messages Container */}
            <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs leading-relaxed bg-[#FAFBF9]">
              {messages.map((m) => {
                if (m.sender === "user") {
                  return (
                    <div key={m.id} className="flex items-start gap-2.5">
                      <div className="w-8 h-8 rounded-full overflow-hidden border border-[#E8E4DC] shrink-0 shadow-2xs">
                        <img
                          src={m.avatar || "/stitch/1_avatar_user_317ba717e1464aafbe096f8b685c3790.png"}
                          alt="User avatar"
                          className="w-full h-full object-cover"
                        />
                      </div>
                      <div className="bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#121E1A] p-3.5 rounded-2xl rounded-tl-xs max-w-[90%] shadow-2xs font-medium leading-normal">
                        {m.text}
                      </div>
                    </div>
                  );
                }

                return (
                  <div key={m.id} className="flex items-start gap-2.5">
                    <div className="w-8 h-8 rounded-full bg-[#0F5F4A] shrink-0 flex items-center justify-center text-white shadow-2xs">
                      <span className="material-symbols-outlined text-[17px]">auto_awesome</span>
                    </div>
                    <div className="bg-white border border-[#E8E4DC] rounded-2xl rounded-tl-xs p-4 shadow-sm flex-1 space-y-3">
                      <p className="font-bold text-[#121E1A]">{m.text}</p>

                      {/* Condition: Bắt buộc */}
                      {m.mandatoryCriteria && (
                        <div className="space-y-1.5">
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#E6F4EE] text-[#0F5F4A] text-[10px] font-bold rounded-full border border-[#0F5F4A]/20">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
                            <span>Bắt buộc</span>
                          </span>
                          <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
                            {m.mandatoryCriteria.map((crit, idx) => (
                              <li key={idx} className="flex items-center gap-2 text-[#0F5F4A]">
                                <span className="material-symbols-outlined text-[15px] font-bold">check_circle</span>
                                <span>{crit}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Condition: Ưu tiên */}
                      {m.priorityCriteria && (
                        <div className="space-y-1.5 pt-1 border-t border-[#F1F5F9]">
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#FFF5E6] text-[#D97706] text-[10px] font-bold rounded-full border border-[#FFE0B2]">
                            <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B4A]"></span>
                            <span>Ưu tiên</span>
                          </span>
                          <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
                            {m.priorityCriteria.map((crit, idx) => (
                              <li key={idx} className="flex items-center gap-2 text-[#B45309]">
                                <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B4A]"></span>
                                <span>{crit}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Clarification prompt text */}
                      {m.summaryCount && (
                        <p className="text-[11px] text-[#6F7974] pt-1 leading-normal border-t border-[#F1F5F9]">
                          Mình đã tìm thấy <span className="font-bold text-[#0F5F4A]">{m.summaryCount} phòng</span> phù hợp nhất cho bạn ở khu vực gần UIT.
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}

              {isTyping && (
                <div className="flex items-center gap-2 text-xs text-gray-500 pl-10">
                  <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce"></span>
                  <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-100"></span>
                  <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-bounce delay-200"></span>
                  <span className="italic text-[11px]">AI đang phân tích yêu cầu mới...</span>
                </div>
              )}
            </div>

            {/* Chat Input Footer */}
            <form onSubmit={handleSendMessage} className="p-3 border-t border-[#E8E4DC] bg-white">
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={inputVal}
                  onChange={(e) => setInputVal(e.target.value)}
                  placeholder="Nhập tin nhắn để điều chỉnh yêu cầu..."
                  className="w-full pl-4 pr-12 py-2.5 bg-[#FAFBF9] border border-[#E8E4DC] rounded-full text-xs text-[#121E1A] focus:outline-none focus:ring-2 focus:ring-[#0F5F4A]/20 focus:border-[#0F5F4A] transition placeholder-[#6F7974]"
                />
                <button
                  type="submit"
                  className="absolute right-1.5 w-8 h-8 bg-[#0F5F4A] hover:bg-[#004635] text-white rounded-full flex items-center justify-center transition shadow-xs"
                >
                  <span className="material-symbols-outlined text-[16px]">send</span>
                </button>
              </div>
            </form>
          </section>

          {/* ============================================== */}
          {/* COLUMN 2: KẾT QUẢ DANH SÁCH PHÒNG (Col span 4) */}
          {/* ============================================== */}
          <section className="lg:col-span-4 bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[650px] lg:h-full overflow-hidden">
            {/* Header & Quick Filters */}
            <div className="p-3.5 px-4 border-b border-[#E8E4DC] space-y-2.5 bg-white">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
                  <span>2. Kết quả danh sách phòng</span>
                </h2>
                <span className="text-[11px] font-bold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full">
                  18 phòng
                </span>
              </div>
              <p className="text-[11px] text-[#6F7974] font-medium">
                Tìm được <span className="text-[#121E1A] font-bold">18 phòng</span> phù hợp với yêu cầu của bạn.
              </p>

              {/* Filter Pills Row */}
              <div className="flex items-center gap-1.5 overflow-x-auto hide-scrollbar pb-1 text-[11px]">
                <button
                  onClick={() => setActiveFilter("price")}
                  className={`flex items-center gap-1 px-3 py-1 font-semibold rounded-full border whitespace-nowrap transition-all ${
                    activeFilter === "price"
                      ? "bg-[#E6F4EE] text-[#0F5F4A] border-[#0F5F4A]/20"
                      : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0]"
                  }`}
                >
                  <span>Giá</span>
                  <span className="material-symbols-outlined text-[14px]">arrow_drop_down</span>
                </button>
                <button
                  onClick={() => setActiveFilter("distance")}
                  className={`flex items-center gap-1 px-3 py-1 font-medium rounded-full border whitespace-nowrap transition-all ${
                    activeFilter === "distance"
                      ? "bg-[#E6F4EE] text-[#0F5F4A] border-[#0F5F4A]/20"
                      : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0]"
                  }`}
                >
                  <span>Khoảng cách</span>
                  <span className="material-symbols-outlined text-[14px]">arrow_drop_down</span>
                </button>
                <button
                  onClick={() => setActiveFilter("ac")}
                  className={`px-3 py-1 font-medium rounded-full border whitespace-nowrap transition-all ${
                    activeFilter === "ac"
                      ? "bg-[#E6F4EE] text-[#0F5F4A] border-[#0F5F4A]/20"
                      : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0]"
                  }`}
                >
                  Máy lạnh
                </button>
                <button
                  onClick={() => setActiveFilter("mezzanine")}
                  className={`px-3 py-1 font-medium rounded-full border whitespace-nowrap transition-all ${
                    activeFilter === "mezzanine"
                      ? "bg-[#E6F4EE] text-[#0F5F4A] border-[#0F5F4A]/20"
                      : "bg-white text-[#3F4944] border-[#E8E4DC] hover:bg-[#E9F7F0]"
                  }`}
                >
                  Gác
                </button>
              </div>
            </div>

            {/* Room Cards Scroll Area */}
            <div className="flex-1 p-3.5 overflow-y-auto space-y-3.5 bg-[#FAFBF9]">
              {rooms.map((room) => {
                const isSelected = selectedRoomId === room.id;
                return (
                  <article
                    key={room.id}
                    onClick={() => setSelectedRoomId(room.id)}
                    className={`p-3 rounded-2xl border transition bg-white group cursor-pointer ${
                      isSelected
                        ? "border-2 border-[#0F5F4A] shadow-md ring-2 ring-[#0F5F4A]/10"
                        : room.rank === 1
                        ? "border-2 border-[#0F5F4A]/30 hover:border-[#0F5F4A] hover:shadow-md"
                        : "border border-[#E8E4DC] hover:border-[#0F5F4A]/60 hover:shadow-md"
                    }`}
                  >
                    <div className="flex gap-3">
                      {/* Thumbnail + Photo counter */}
                      <div className="relative w-28 h-28 rounded-xl overflow-hidden shrink-0 bg-slate-100">
                        <img
                          src={room.image}
                          alt={room.title}
                          className="w-full h-full object-cover group-hover:scale-105 transition duration-300"
                        />
                        <span className="absolute bottom-1.5 left-1.5 bg-black/60 backdrop-blur-xs text-white text-[9px] font-bold px-1.5 py-0.5 rounded flex items-center gap-1">
                          📷 {room.photoCount}
                        </span>
                      </div>

                      {/* Information Details */}
                      <div className="flex-1 min-w-0 flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span
                              className={`text-[9px] font-extrabold px-2 py-0.5 rounded-full tracking-wide uppercase ${
                                room.rank === 1
                                  ? "bg-[#0F5F4A] text-white"
                                  : "bg-[#0F5F4A]/80 text-white"
                              }`}
                            >
                              {room.rankText}
                            </span>
                            <span className="text-[10px] font-bold text-[#0F5F4A] bg-[#E6F4EE] px-2 py-0.5 rounded-full border border-[#0F5F4A]/20 flex items-center gap-1">
                              <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
                              <span>Match {room.matchScore}%</span>
                            </span>
                          </div>

                          <h3
                            className="font-bold text-xs text-[#121E1A] truncate leading-snug group-hover:text-[#0F5F4A] transition-colors"
                            title={room.title}
                          >
                            {room.title}
                          </h3>

                          <div className="text-sm font-extrabold text-[#FF6B4A] mt-0.5">
                            {room.price}
                            <span className="text-[10px] font-normal text-[#6F7974]">/tháng</span>
                          </div>

                          <p className="text-[10px] text-[#6F7974] truncate mt-0.5 flex items-center gap-1">
                            <span className="material-symbols-outlined text-[13px] text-[#0F5F4A]">location_on</span>
                            <span>{room.address}</span>
                          </p>

                          <div className="text-[10px] font-semibold text-[#0F5F4A] mt-0.5 flex items-center gap-1">
                            <span>📍 {room.distance}</span>
                          </div>
                        </div>

                        {/* Tags */}
                        <div className="flex items-center gap-1.5 mt-1 text-[9px] text-[#3F4944] font-medium flex-wrap">
                          {room.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 bg-[#FAFBF9] border border-[#E8E4DC] rounded">
                              {t}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t border-[#F1F5F9]">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedRoomId(room.id);
                        }}
                        className="px-3 py-1.5 text-[11px] font-bold text-[#0F5F4A] hover:bg-[#E6F4EE] border border-[#0F5F4A]/30 rounded-full transition"
                      >
                        So sánh
                      </button>
                      <Link
                        href={`/phong-tro/${room.id}`}
                        onClick={(e) => e.stopPropagation()}
                        className="px-4 py-1.5 text-[11px] font-bold text-white bg-[#0F5F4A] hover:bg-[#004635] rounded-full transition shadow-xs"
                      >
                        Xem chi tiết
                      </Link>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          {/* ============================================================== */}
          {/* COLUMN 3: BẢN ĐỒ VỊ TRÍ & PHÂN TÍCH AGENT (Col span 4)         */}
          {/* ============================================================== */}
          <section className="lg:col-span-4 flex flex-col gap-4 h-[750px] lg:h-full overflow-hidden">
            {/* TOP CARD: 3. Bản đồ vị trí (48% height) */}
            <div className="bg-white rounded-2xl border border-[#E8E4DC] shadow-[0_2px_12px_rgba(15,95,74,0.04)] flex flex-col h-[48%] overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[#E8E4DC] flex items-center justify-between bg-white">
                <h2 className="text-sm font-bold text-[#0F5F4A] flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#0F5F4A]"></span>
                  <span>3. Bản đồ vị trí</span>
                </h2>
                <span className="text-[10px] bg-[#E6F4EE] text-[#0F5F4A] px-2.5 py-0.5 rounded-full font-bold">
                  Bán kính 1.5 km
                </span>
              </div>

              {/* Stylized Interactive Map Area */}
              <div className="flex-1 relative bg-[#F1F5F9] overflow-hidden flex items-center justify-center">
                {/* Map Grid Background Pattern */}
                <div
                  className="absolute inset-0 opacity-80"
                  style={{
                    backgroundImage: `
                      radial-gradient(#CBD5E1 1.2px, transparent 1.2px),
                      linear-gradient(to right, rgba(226,232,240,0.6) 1px, transparent 1px),
                      linear-gradient(to bottom, rgba(226,232,240,0.6) 1px, transparent 1px)
                    `,
                    backgroundSize: "24px 24px, 48px 48px, 48px 48px",
                  }}
                />

                {/* Map road network graphic elements */}
                <svg className="absolute inset-0 w-full h-full opacity-60 pointer-events-none" xmlns="http://www.w3.org/2000/svg">
                  <line stroke="#cbd5e1" strokeLinecap="round" strokeWidth="4" x1="0" x2="100%" y1="40" y2="160" />
                  <line stroke="#e2e8f0" strokeWidth="3" x1="20%" x2="60%" y1="0" y2="100%" />
                  <line stroke="#fcd34d" strokeDasharray="4,4" strokeWidth="3" x1="0" x2="100%" y1="180" y2="70" />
                  <line stroke="#a7f3d0" strokeWidth="2" x1="75%" x2="70%" y1="0" y2="100%" />
                </svg>

                {/* UIT Circle Radius (Translucent target ring in Homigo emerald) */}
                <div className="absolute w-44 h-44 rounded-full bg-[#0F5F4A]/10 border-2 border-[#0F5F4A]/30 flex items-center justify-center animate-pulse pointer-events-none"></div>

                {/* UIT Center Landmark Pin */}
                <div className="relative z-10 flex flex-col items-center">
                  <div className="w-10 h-10 rounded-full bg-[#0F5F4A] text-white flex items-center justify-center shadow-lg border-2 border-white">
                    <span className="material-symbols-outlined text-[20px]">school</span>
                  </div>
                  <span className="mt-1 px-2.5 py-0.5 bg-[#004635] text-white text-[10px] font-black rounded-full shadow-xs tracking-wider">
                    UIT
                  </span>
                </div>

                {/* Pins for Rooms */}
                {rooms.map((r) => {
                  const isCur = selectedRoomId === r.id;
                  return (
                    <div
                      key={r.id}
                      onClick={() => setSelectedRoomId(r.id)}
                      style={{ top: `${r.latPercent}%`, left: `${r.lngPercent}%` }}
                      className={`absolute z-20 flex flex-col items-center cursor-pointer transition-transform ${
                        isCur ? "scale-125 z-30" : "hover:scale-110"
                      }`}
                      title={`${r.rankText}: ${r.price} - ${r.distance}`}
                    >
                      <div
                        className={`px-2 py-0.5 rounded-full text-[10px] font-bold shadow-md border-2 border-white flex items-center gap-1 ${
                          isCur ? "bg-[#FF6B4A] text-white ring-2 ring-[#FF6B4A]/50" : "bg-[#0F5F4A] text-white"
                        }`}
                      >
                        <span>#{r.rank}</span>
                        <span>{r.priceNum}tr</span>
                      </div>
                      <div
                        className={`w-2 h-2 rotate-45 -mt-1 ${
                          isCur ? "bg-[#FF6B4A]" : "bg-[#0F5F4A]"
                        }`}
                      ></div>
                    </div>
                  );
                })}

                {/* Distance pill at bottom of map */}
                <div className="absolute bottom-2.5 bg-white/95 backdrop-blur-xs border border-[#E8E4DC] text-[#121E1A] text-[10px] font-bold px-3 py-1 rounded-full shadow-sm flex items-center gap-1.5 z-20">
                  <span className="text-[#0F5F4A]">📍</span>
                  <span>Khoảng cách tới UIT: ~ {selectedRoom.distance}</span>
                </div>

                {/* Map UI Zoom controls on right */}
                <div className="absolute right-2.5 top-2.5 z-20 flex flex-col bg-white rounded-lg shadow-sm border border-[#E8E4DC] overflow-hidden text-xs">
                  <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold border-b border-[#E8E4DC] transition">
                    +
                  </button>
                  <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#121E1A] font-bold transition">
                    -
                  </button>
                </div>

                {/* Location re-center target button */}
                <div className="absolute right-2.5 bottom-2.5 z-20 bg-white rounded-lg shadow-sm border border-[#E8E4DC]">
                  <button className="w-7 h-7 flex items-center justify-center hover:bg-[#E9F7F0] text-[#0F5F4A] transition" title="Định vị UIT">
                    <span className="material-symbols-outlined text-[16px]">my_location</span>
                  </button>
                </div>
              </div>
            </div>

            {/* BOTTOM CARD: 4. Phân tích & giải thích của Agent (52% height) */}
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
                    <span>Vì sao phòng #{selectedRoom.rank} ({selectedRoom.title}) được đề xuất?</span>
                  </div>
                  <ul className="text-[11px] text-[#3F4944] space-y-1.5 pl-1 leading-relaxed">
                    <li className="flex items-start gap-1.5">
                      <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
                      <span>
                        <strong className="text-[#121E1A]">Gần UIT nhất:</strong> {selectedRoom.distance}, lộ trình an toàn ít tắc xe.
                      </span>
                    </li>
                    <li className="flex items-start gap-1.5">
                      <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] mt-0.5 shrink-0">check_circle</span>
                      <span>
                        <strong className="text-[#121E1A]">Đầy đủ điều kiện bắt buộc:</strong> Giá {selectedRoom.price} (đạt ≤ 5tr), có sẵn máy lạnh Inverter & gác đúc cao.
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
          </section>
        </div>
      </main>

    </SiteLayout>
  );
}
