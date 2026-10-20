"use client";

import { useEffect, useState } from "react";
import type { ChatMessage, DecisionInsight, RoomItem, UserPreferenceState } from "@/app/tim-kiem-ai/types";
import {
  DEFAULT_ROOM_ID,
  INITIAL_MESSAGES,
  USER_AVATAR,
} from "@/app/tim-kiem-ai/_constants/aiWorkspace";
import { agentApi } from "@/lib/api/client";

const STORAGE_KEY = "homigo_ai_workspace_session_v1";

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [rooms, setRooms] = useState<RoomItem[]>([]);
  const [insights, setInsights] = useState<DecisionInsight | null>(null);
  const [preferences, setPreferences] = useState<UserPreferenceState | null>(null);
  const [selectedRoomId, setSelectedRoomId] = useState<string>(DEFAULT_ROOM_ID);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const [isHydrated, setIsHydrated] = useState(false);

  // Khôi phục trạng thái từ sessionStorage khi mount (chống mất chat khi Back từ trang chi tiết)
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        queueMicrotask(() => {
          if (parsed.messages && parsed.messages.length > 0) setMessages(parsed.messages);
          if (parsed.rooms && parsed.rooms.length > 0) setRooms(parsed.rooms);
          if (parsed.insights) setInsights(parsed.insights);
          if (parsed.preferences) setPreferences(parsed.preferences);
          if (parsed.selectedRoomId) setSelectedRoomId(parsed.selectedRoomId);
          if (parsed.sessionId) setSessionId(parsed.sessionId);
        });
      }
    } catch (e) {
      console.warn("Could not restore AI chat session", e);
    } finally {
      setIsHydrated(true);
    }
  }, []);

  // Tự động lưu trạng thái vào sessionStorage mỗi khi có tin nhắn hoặc kết quả phòng mới
  useEffect(() => {
    if (!isHydrated) return;

    if (messages.length > INITIAL_MESSAGES.length || rooms.length > 0) {
      try {
        sessionStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            messages,
            rooms,
            insights,
            preferences,
            selectedRoomId,
            sessionId,
          })
        );
      } catch (e) {
        console.warn("Could not persist AI chat session", e);
      }
    }
  }, [messages, rooms, insights, preferences, selectedRoomId, sessionId, isHydrated]);

  // Xoá lịch sử phiên làm việc hiện tại để bắt đầu hội thoại mới
  const resetConversation = () => {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {}
    setMessages(INITIAL_MESSAGES);
    setRooms([]);
    setInsights(null);
    setPreferences(null);
    setSelectedRoomId(DEFAULT_ROOM_ID);
    setSessionId(null);
  };

  const sendMessage = async (event?: React.FormEvent, customText?: string) => {
    event?.preventDefault();
    const textToSend = (customText || inputValue).trim();
    if (!textToSend || isTyping) return;

    if (!customText) {
      setInputValue("");
    }

    const now = Date.now();
    const userMessage: ChatMessage = {
      id: `msg-${now}`,
      sender: "user",
      text: textToSend,
      avatar: USER_AVATAR,
    };

    const aiMsgId = `msg-${now + 1}`;
    const placeholderAiMessage: ChatMessage = {
      id: aiMsgId,
      sender: "ai",
      text: "",
      traceEvents: [],
      isStreaming: true,
      statusText: "Đang suy nghĩ...",
    };

    const history = messages
      .filter((m) => m.id !== "msg-welcome")
      .map((m) => ({
        role: m.sender === "user" ? "user" : "assistant",
        content: m.text,
      }));

    setMessages((prev) => {
      // Nếu gửi từ một nút bấm (HITL hoặc gợi ý), đánh dấu hành động đã chọn vào tin nhắn bot gần nhất
      const updated = prev.map((m, idx) => {
        if (customText && idx === prev.length - 1 && m.sender === "ai") {
          return {
            ...m,
            selectedHitlAction: customText,
          };
        }
        return m;
      });
      return [...updated, userMessage, placeholderAiMessage];
    });
    setIsTyping(true);
    setConnectionError(null);

    try {
      const res = await agentApi.chatStream(
        {
          message: textToSend,
          conversation_history: history,
          session_id: sessionId || undefined,
        },
        {
          onTrace: (traceEv) => {
            let nextStatus = "Đang xử lý...";
            if (traceEv.type === "model_request") {
              nextStatus = `Đang suy nghĩ (Model call #${traceEv.model_call_index || 1})...`;
            } else if (traceEv.type === "model_response") {
              if (traceEv.requested_tools && traceEv.requested_tools.length > 0) {
                nextStatus = `Chuẩn bị gọi tool: ${traceEv.requested_tools.join(", ")}...`;
              } else {
                nextStatus = "Đang viết câu trả lời...";
              }
            } else if (traceEv.type === "tool_started") {
              nextStatus = `Đang chạy tool ${traceEv.tool_name}...`;
            } else if (traceEv.type === "tool_finished") {
              nextStatus = `Hoàn tất tool ${traceEv.tool_name} (${traceEv.elapsed_ms ?? 0} ms) — đang phân tích kết quả...`;
            }

            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId
                  ? {
                      ...m,
                      traceEvents: [...(m.traceEvents || []), traceEv],
                      statusText: nextStatus,
                    }
                  : m
              )
            );
          },
          onTextDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === aiMsgId
                  ? {
                      ...m,
                      text: (m.text || "") + delta,
                      statusText: "Đang viết câu trả lời...",
                    }
                  : m
              )
            );
          },
        }
      );

      if (res.session_id) {
        setSessionId(res.session_id);
      }

      if (res.rooms && res.rooms.length > 0) {
        setRooms(res.rooms);
        setSelectedRoomId(res.rooms[0].id);
      } else {
        // AI trả về danh sách rỗng (do Giữ nguyên tiêu chí hoặc không tìm thấy phòng)
        setRooms([]);
        setSelectedRoomId(DEFAULT_ROOM_ID);
        setInsights(null);
      }

      if (res.insights) {
        setInsights(res.insights);
      }

      if (res.current_preferences) {
        setPreferences(res.current_preferences);
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

      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                text: res.text_reply || m.text,
                isStreaming: false,
                statusText: undefined,
                traceEvents: res.trace_events && res.trace_events.length > 0 ? res.trace_events : m.traceEvents,
                mandatoryCriteria: mandatory.length > 0 ? mandatory : undefined,
                priorityCriteria: priority.length > 0 ? priority : undefined,
                summaryCount: res.rooms && res.rooms.length > 0 ? res.rooms.length : undefined,
                followUpQuestions:
                  res.follow_up_questions && res.follow_up_questions.length > 0
                    ? res.follow_up_questions
                    : undefined,
                hitlProposal: res.hitl_proposal || undefined,
                groundingReport: res.grounding_report || undefined,
              }
            : m
        )
      );
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Lỗi kết nối tới AI Agent";
      setConnectionError(errorMsg);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                isStreaming: false,
                statusText: undefined,
                text: `⚠️ Không thể kết nối tới máy chủ AI Agent (Port 8001): ${errorMsg}.\n\nNếu đang phát triển cục bộ, bạn hãy kiểm tra microservice AI bằng lệnh:\n\`cd ai-agent; uvicorn service:app --port 8001 --reload\``,
                followUpQuestions: ["Thử gửi lại yêu cầu"],
              }
            : m
        )
      );
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
    preferences,
    selectedRoomId,
    setSelectedRoomId,
    sessionId,
    connectionError,
    resetConversation,
    hasActiveSession: messages.length > INITIAL_MESSAGES.length || rooms.length > 0,
  };
}