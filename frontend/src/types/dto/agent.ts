export interface TradeOffAnalysis {
  compared_with: string;
  advantage: string;
  disadvantage: string;
}

export interface DecisionInsight {
  selected_top_1_id: string;
  top_1_reason: string;
  key_factors: string[];
  trade_offs: TradeOffAnalysis[];
  verification_checklist: string[];
}

export interface UserPreferenceState {
  location_text?: string;
  lat?: number;
  lng?: number;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  amenities?: string[];
  special_requirements?: string[];
}

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
  lat?: number;
  lng?: number;
  latPercent: number; // For map pin positioning
  lngPercent: number;
  source_url?: string;
  explain_match?: Record<string, any>;
}

export interface AgentResponse {
  session_id?: string;
  text_reply: string;
  rooms: RoomItem[];
  insights?: DecisionInsight | null;
  current_preferences?: UserPreferenceState | null;
  need_clarification?: boolean;
  follow_up_questions?: string[];
  grounding_report?: Record<string, any> | null;
}

export interface AgentChatRequest {
  message: string;
  conversation_history?: Array<{ role: string; content: string }>;
  session_id?: string;
}
