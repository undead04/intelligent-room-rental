import type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
  AgentTraceEvent,
} from "@/types/dto/agent";

export type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
  AgentTraceEvent,
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
  groundingReport?: Record<string, unknown> | null;
  traceEvents?: AgentTraceEvent[];
  isStreaming?: boolean;
  statusText?: string;
}