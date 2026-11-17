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
  allowed_room_types?: string[];
  excluded_room_types?: string[];
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
  source_url?: string;
  explain_match?: Record<string, unknown>;
}

export interface AgentTraceVersions {
  prompt?: string;
  skill?: string;
  model?: string;
}

export interface VerifierFailureItem {
  condition_id?: string;
  actual?: unknown;
  expected?: unknown;
  verifier_type?: string;
  message?: string;
  tier?: string;
}

export interface AgentTraceEvent {
  type:
    | "model_request"
    | "model_response"
    | "model_error"
    | "tool_started"
    | "tool_finished"
    | "node_step"
    | "verifier_decision"
    | "adaptive_radius_expansion"
    | "suspicious_listing"
    | string;
  id?: string;
  run_id?: string;
  session_id?: string;
  case_id?: string;
  seq?: number;
  ts?: number;
  timestamp?: number;
  versions?: AgentTraceVersions;
  step?: number;
  model_call_index?: number;
  model_name?: string;
  message_count?: number;
  tool_count?: number;
  system_prompt_chars?: number;
  message_chars?: number;
  duration_ms?: number;
  elapsed_ms?: number;
  node?: string;
  label?: string;
  details?: string;
  input?: unknown;
  output?: unknown;
  tokens_in?: number;
  tokens_out?: number;
  prompt_tokens?: number;
  cached_tokens?: number;
  tokens_estimated?: boolean;
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
  tool?: string;
  tool_call_id?: string;
  tool_name?: string;
  arguments?: Record<string, unknown>;
  args?: Record<string, unknown>;
  status?: string;
  result?: unknown;
  result_summary?: Record<string, unknown> | unknown;
  state_before?: Record<string, unknown> | unknown;
  state_after?: Record<string, unknown> | unknown;
  error?: string | null;
  passed?: boolean;
  failures?: Array<VerifierFailureItem | string>;
  next_decision?: string;
  failed_tier?: string | null;
  answer_retry?: number;
  dod_summary?: string;
  verifier_output?: {
    passed?: boolean;
    failures?: Array<VerifierFailureItem | string>;
    [key: string]: unknown;
  };
  from_radius?: number | null;
  to_radius?: number;
  valid_rooms_before?: number;
  reason?: string;
  listing_id?: string;
  rules?: string[];
}

export interface AgentResponse {
  session_id?: string;
  text_reply: string;
  rooms: RoomItem[];
  page?: number;
  page_size?: number;
  total_rooms?: number;
  total_pages?: number;
  insights?: DecisionInsight | null;
  current_preferences?: UserPreferenceState | null;
  need_clarification?: boolean;
  follow_up_questions?: string[];
  grounding_report?: Record<string, unknown> | null;
  trace_events?: AgentTraceEvent[];
  searched?: boolean;
}

export interface SessionRoomsPageResponse {
  session_id: string;
  rooms: RoomItem[];
  page: number;
  page_size: number;
  total_rooms: number;
  total_pages: number;
  has_prev: boolean;
  has_next: boolean;
}

export interface AgentChatRequest {
  message: string;
  conversation_history?: Array<{ role: string; content: string }>;
  session_id?: string;
}

