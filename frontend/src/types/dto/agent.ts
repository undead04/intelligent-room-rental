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
  city_id?: number;
  district_id?: number;
  ward_id?: number;
  room_type?: string;
  room_type_id?: number;
  min_price?: number;
  max_price?: number;
  min_area?: number;
  max_area?: number;
  amenities?: string[];
  preferred_amenities?: string[];
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
  explain_match?: Record<string, unknown>;
}

export interface AgentTraceEvent {
  type: "model_request" | "model_response" | "tool_started" | "tool_finished" | "node_step" | "model_error" | string;
  step?: number;
  model_call_index?: number;
  model_name?: string;
  message_count?: number;
  tool_count?: number;
  system_prompt_chars?: number;
  message_chars?: number;
  elapsed_ms?: number;
  node?: string;
  label?: string;
  details?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    output_token_details?: {
      reasoning?: number;
    };
  } | null;
  tool_calls_requested?: Array<{ id?: string; name?: string }>;
  requested_tools?: string[];
  tool_call_id?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  args?: Record<string, unknown>;
  status?: string;
  result?: unknown;
  error?: string;
}

export interface AgentResponse {
  session_id?: string;
  text_reply: string;
  rooms: RoomItem[];
  insights?: DecisionInsight | null;
  current_preferences?: UserPreferenceState | null;
  need_clarification?: boolean;
  follow_up_questions?: string[];
  grounding_report?: Record<string, unknown> | null;
  trace_events?: AgentTraceEvent[];
}

export interface AgentChatRequest {
  message: string;
  conversation_history?: Array<{ role: string; content: string }>;
  session_id?: string;
  use_graph?: boolean;
}

