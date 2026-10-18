import type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
} from "@/types/dto";

export type {
  DecisionInsight,
  RoomItem,
  TradeOffAnalysis,
  UserPreferenceState,
  AgentResponse,
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
}