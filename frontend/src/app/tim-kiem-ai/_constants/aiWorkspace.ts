import type { ChatMessage, RoomItem } from "@/app/tim-kiem-ai/types";

export const USER_AVATAR = "/stitch/1_avatar_user_317ba717e1464aafbe096f8b685c3790.png";

export const DEFAULT_ROOM_ID = "room-1";
export const DEFAULT_FILTER_ID = "all";

export const SAMPLE_ROOMS: RoomItem[] = [
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

export const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: "msg-1",
    sender: "user",
    text: "Tìm phòng dưới 5 triệu, gần UIT, có máy lạnh, có gác, ưu tiên phòng mới.",
    avatar: USER_AVATAR,
  },
  {
    id: "msg-2",
    sender: "ai",
    text: "Mình hiểu nhu cầu của bạn:",
    mandatoryCriteria: ["Giá ≤ 5 triệu", "Gần UIT", "Có máy lạnh"],
    priorityCriteria: ["Phòng mới", "Có gác"],
    summaryCount: SAMPLE_ROOMS.length,
  },
];

export const AI_FOLLOW_UP_MESSAGE: Omit<ChatMessage, "id"> = {
  sender: "ai",
  text: "Đã cập nhật tiêu chí mới của bạn:",
  mandatoryCriteria: ["Giá ≤ 5 triệu", "Gần UIT", "Có máy lạnh", "Giờ tự do 24/7"],
  priorityCriteria: ["Phòng mới", "Có gác", "An ninh tốt"],
  summaryCount: 14,
};

export const AI_REPLY_DELAY_MS = 900;