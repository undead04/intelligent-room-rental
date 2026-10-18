import { useState } from "react";
import type { ChatMessage, DecisionInsight, RoomItem } from "@/app/tim-kiem-ai/types";
import {
  DEFAULT_ROOM_ID,
  INITIAL_MESSAGES,
  SAMPLE_ROOMS,
  USER_AVATAR,
} from "@/app/tim-kiem-ai/_constants/aiWorkspace";
import { agentApi } from "@/lib/api/client";

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [rooms, setRooms] = useState<RoomItem[]>(SAMPLE_ROOMS);
  const [insights, setInsights] = useState<DecisionInsight | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string>(DEFAULT_ROOM_ID);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const sendMessage = async (event?: React.FormEvent, customText?: string) => {
    event?.preventDefault();
    const textToSend = (customText || inputValue).trim();
    if (!textToSend || isTyping) return;

    if (!customText) {
      setInputValue("");
    }

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: "user",
      text: textToSend,
      avatar: USER_AVATAR,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    try {
      const history = messages.map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

      const res = await agentApi.chat({
        message: textToSend,
        conversation_history: history,
        session_id: sessionId || undefined,
      });

      if (res.session_id) {
        setSessionId(res.session_id);
      }

      if (res.rooms && res.rooms.length > 0) {
        setRooms(res.rooms);
        setSelectedRoomId(res.rooms[0].id);
      }

      if (res.insights) {
        setInsights(res.insights);
      }

      // Trích xuất tiêu chí hiển thị trực quan
      const mandatory: string[] = [];
      const priority: string[] = [];

      if (res.current_preferences) {
        const pref = res.current_preferences;
        if (pref.max_price) {
          const maxTr = (pref.max_price / 1_000_000).toFixed(1).replace(".0", "");
          mandatory.push(`Giá ≤ ${maxTr} triệu`);
        }
        if (pref.location_text) {
          mandatory.push(`Khu vực: ${pref.location_text}`);
        }
        if (pref.amenities && pref.amenities.length > 0) {
          priority.push(...pref.amenities);
        }
        if (pref.special_requirements && pref.special_requirements.length > 0) {
          priority.push(...pref.special_requirements);
        }
      }

      const aiMessage: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: "ai",
        text: res.text_reply,
        mandatoryCriteria: mandatory.length > 0 ? mandatory : undefined,
        priorityCriteria: priority.length > 0 ? priority : undefined,
        summaryCount: res.rooms && res.rooms.length > 0 ? res.rooms.length : undefined,
        followUpQuestions: res.follow_up_questions && res.follow_up_questions.length > 0 ? res.follow_up_questions : undefined,
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Lỗi kết nối tới AI Agent";
      const fallbackAiMessage: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: "ai",
        text: `⚠️ Không thể kết nối tới AI Agent Server (Port 8001): ${errorMsg}. Bạn vui lòng kiểm tra microservice đã khởi chạy bằng lệnh: cd ai-agent; uvicorn service:app --port 8001 --reload`,
      };
      setMessages((prev) => [...prev, fallbackAiMessage]);
    } finally {
      setIsTyping(false);
    }
  };

  return {
    messages,
    inputValue,
    setInputValue,
    isTyping,
    sendMessage,
    rooms,
    insights,
    selectedRoomId,
    setSelectedRoomId,
    sessionId,
  };
}