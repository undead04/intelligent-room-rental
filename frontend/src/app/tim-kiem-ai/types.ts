export interface RoomItem {
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

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  avatar?: string;
  mandatoryCriteria?: string[];
  priorityCriteria?: string[];
  summaryCount?: number;
}