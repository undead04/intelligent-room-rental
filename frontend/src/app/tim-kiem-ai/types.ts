import type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
  AgentTraceEvent,
  HitlOption,
  HitlProposal,
} from "@/types/dto/agent";

export type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
  AgentTraceEvent,
  HitlOption,
  HitlProposal,
};

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  avatar?: string;
  mandatoryCriteria?: string[];
  priorityCriteria?: string[];
  summaryCount?: number;
  followUpQuestions?: string[];
  hitlProposal?: HitlProposal | null;
  selectedHitlAction?: string;
  groundingReport?: Record<string, unknown> | null;
  traceEvents?: AgentTraceEvent[];
  isStreaming?: boolean;
  statusText?: string;
}