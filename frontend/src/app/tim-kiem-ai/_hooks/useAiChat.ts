"use client";

import { useEffect, useState } from "react";
import type { ChatMessage, DecisionInsight, RoomItem, UserPreferenceState } from "@/app/tim-kiem-ai/types";
import {
  DEFAULT_ROOM_ID,
  INITIAL_MESSAGES,
  USER_AVATAR,
  CANONICAL_AMENITIES_MAP,
  CANONICAL_ROOM_TYPES_MAP,
} from "@/app/tim-kiem-ai/_constants/aiWorkspace";
import { agentApi } from "@/lib/api/client";
import { mergeTraceEvents } from "@/app/tim-kiem-ai/_components/traceUtils";

const STORAGE_KEY = "homigo_ai_workspace_session_v2";
const PAGE_SIZE = 5;

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [isPaging, setIsPaging] = useState(false);
  const [rooms, setRooms] = useState<RoomItem[]>([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [totalRooms, setTotalRooms] = useState(0);
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
          if (typeof parsed.currentPage === "number" && parsed.currentPage > 0) setCurrentPage(parsed.currentPage);
          if (typeof parsed.totalPages === "number" && parsed.totalPages >= 0) setTotalPages(parsed.totalPages);
          if (typeof parsed.totalRooms === "number" && parsed.totalRooms >= 0) setTotalRooms(parsed.totalRooms);
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
            currentPage,
            totalPages,
            totalRooms,
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
  }, [messages, rooms, currentPage, totalPages, totalRooms, insights, preferences, selectedRoomId, sessionId, isHydrated]);

  // Xoá lịch sử phiên làm việc hiện tại để bắt đầu hội thoại mới
  const resetConversation = () => {
    if (sessionId) {
      agentApi.clearSession(sessionId);
    }
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {}
    setMessages(INITIAL_MESSAGES);
    setRooms([]);
    setCurrentPage(1);
    setTotalPages(0);
    setTotalRooms(0);
    setIsPaging(false);
    setInsights(null);
    setPreferences(null);
    setSelectedRoomId(DEFAULT_ROOM_ID);
    setSessionId(null);
  };

  // Chuyển trang danh sách phòng theo session đã pre-fetch (tối đa 10 trang)
  const goToPage = async (targetPage: number) => {
    if (!sessionId || isPaging || isTyping) return;
    if (totalPages > 0 && (targetPage < 1 || targetPage > totalPages)) return;
    if (targetPage === currentPage) return;

    setIsPaging(true);
    setConnectionError(null);
    try {
      const pageData = await agentApi.getSessionRooms(sessionId, targetPage, PAGE_SIZE);
      setRooms(pageData.rooms || []);
      setCurrentPage(pageData.page);
      setTotalPages(pageData.total_pages);
      setTotalRooms(pageData.total_rooms);
      if (pageData.rooms && pageData.rooms.length > 0) {
        setSelectedRoomId(pageData.rooms[0].id);
      }
    } catch (e) {
      console.warn("Could not switch room page", e);
      setConnectionError("Không thể tải trang phòng yêu cầu. Vui lòng thử lại.");
    } finally {
      setIsPaging(false);
    }
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

    setMessages((prev) => [...prev, userMessage, placeholderAiMessage]);
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
            if (traceEv.type === "node_step") {
              nextStatus = `${traceEv.label || traceEv.node || "Đang xử lý"}...`;
            } else if (traceEv.type === "model_request") {
              nextStatus = `Đang suy nghĩ (LLM #${traceEv.model_call_index || 1})...`;
            } else if (traceEv.type === "model_response") {
              if (traceEv.requested_tools && traceEv.requested_tools.length > 0) {
                nextStatus = `Chuẩn bị gọi tool: ${traceEv.requested_tools.join(", ")}...`;
              } else if (traceEv.node === "understand_node") {
                nextStatus = "Đã phân tích xong yêu cầu...";
              } else {
                nextStatus = "Đang viết câu trả lời...";
              }
            } else if (traceEv.type === "tool_started") {
              nextStatus = `Đang chạy tool ${traceEv.tool_name || traceEv.tool}...`;
            } else if (traceEv.type === "tool_finished") {
              nextStatus = `Hoàn tất ${traceEv.tool_name || traceEv.tool} (${traceEv.elapsed_ms ?? traceEv.duration_ms ?? 0} ms)...`;
            } else if (traceEv.type === "adaptive_radius_expansion") {
              nextStatus = `Mở rộng bán kính tìm kiếm lên ${traceEv.to_radius ?? "?"} km...`;
            } else if (traceEv.type === "verifier_decision") {
              nextStatus = traceEv.passed
                ? "Đã kiểm chứng DoD đạt chuẩn..."
                : "Phát hiện sai lệch, đang xử lý kiểm chứng...";
            } else if (traceEv.type === "model_error") {
              nextStatus = "Gặp lỗi khi gọi mô hình AI...";
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
        const nextPage = res.page && res.page > 0 ? res.page : 1;
        const pageChanged = nextPage !== currentPage || res.searched === true;
        setRooms(res.rooms);
        setCurrentPage(nextPage);
        setTotalPages(res.total_pages ?? 1);
        setTotalRooms(res.total_rooms ?? res.rooms.length);

        // Tự động focus đúng phòng nếu câu hỏi người dùng chỉ định rõ Top N / phòng số N
        const rankMatch = textToSend.toLowerCase().match(/(?:top|phòng(?:\s*số)?)\s*(\d+)/);
        const requestedRank = rankMatch ? Number(rankMatch[1]) : null;
        const matchedByRank = requestedRank
          ? res.rooms.find((r) => r.rank === requestedRank)
          : undefined;
        if (matchedByRank) {
          setSelectedRoomId(matchedByRank.id);
        } else if (pageChanged) {
          setSelectedRoomId(res.rooms[0].id);
        } else {
          setSelectedRoomId((prev) => (res.rooms.some((r) => r.id === prev) ? prev : res.rooms[0].id));
        }
      } else if (
        res.grounding_report?.blocked_by_guardrail ||
        /^(?:tìm mới|tim moi|reset|bỏ hết|bo het|xóa hết|xoa het)/i.test(textToSend) ||
        (res.searched === true && res.rooms && res.rooms.length === 0)
      ) {
        // Chỉ làm trống danh sách phòng khi tìm kiếm thực sự ra 0 kết quả, bị chặn, hoặc người dùng yêu cầu reset
        setRooms([]);
        setCurrentPage(1);
        setTotalPages(0);
        setTotalRooms(0);
        setSelectedRoomId(DEFAULT_ROOM_ID);
        setInsights(null);
      }
      // Khi là lượt hỏi Kỹ năng chuyên sâu (Advisory), Hỏi làm rõ, hoặc Followup (searched !== true): giữ nguyên danh sách phòng và bản đồ hiện có

      if (res.insights) {
        setInsights(res.insights);
      }

      if (res.current_preferences) {
        setPreferences(res.current_preferences);
      }

      // Trích xuất tiêu chí hiển thị trực quan chuẩn hoá tiếng Việt
      const mandatory: string[] = [];
      const priority: string[] = [];

      if (res.current_preferences) {
        const pref = res.current_preferences;
        if (pref.allowed_room_types && pref.allowed_room_types.length > 0) {
          const labels = pref.allowed_room_types
            .map((rt) => CANONICAL_ROOM_TYPES_MAP[rt] || rt)
            .join(", ");
          mandatory.push(`Loại: ${labels}`);
        }
        if (pref.min_price && pref.max_price) {
          const minTr = (pref.min_price / 1_000_000).toFixed(1).replace(".0", "");
          const maxTr = (pref.max_price / 1_000_000).toFixed(1).replace(".0", "");
          mandatory.push(`Giá: ${minTr} - ${maxTr} triệu`);
        } else if (pref.max_price) {
          const maxTr = (pref.max_price / 1_000_000).toFixed(1).replace(".0", "");
          mandatory.push(`Giá ≤ ${maxTr} triệu`);
        } else if (pref.min_price) {
          const minTr = (pref.min_price / 1_000_000).toFixed(1).replace(".0", "");
          mandatory.push(`Giá ≥ ${minTr} triệu`);
        }
        if (pref.location_text) {
          const cleanLoc = pref.location_text
            .replace(/\s*\((?:ví dụ|vd|vd:)[^)]*\)/gi, "")
            .replace(/^(?:khu vực\s+)?(?:lân cận|quanh)\s+/gi, "")
            .trim();
          if (cleanLoc) {
            mandatory.push(`Khu vực: ${cleanLoc}`);
          }
        }
        if (pref.min_area || pref.max_area) {
          const areaDesc =
            pref.min_area && pref.max_area
              ? `${pref.min_area} - ${pref.max_area} m²`
              : pref.min_area
              ? `≥ ${pref.min_area} m²`
              : `≤ ${pref.max_area} m²`;
          mandatory.push(`Diện tích: ${areaDesc}`);
        }
        if (pref.amenities && pref.amenities.length > 0) {
          pref.amenities.forEach((a) => {
            const meta = CANONICAL_AMENITIES_MAP[a.toLowerCase()];
            mandatory.push(meta ? meta.label : a);
          });
        }
        if (pref.preferred_amenities && pref.preferred_amenities.length > 0) {
          pref.preferred_amenities.forEach((a) => {
            const meta = CANONICAL_AMENITIES_MAP[a.toLowerCase()];
            priority.push(meta ? meta.label : a);
          });
        }
        if (pref.special_requirements && pref.special_requirements.length > 0) {
          pref.special_requirements.forEach((req) => {
            const cleaned = req.replace(/^(?:ưu tiên|uu tien)[:\s-]*/i, "").trim();
            if (cleaned) {
              priority.push(cleaned.charAt(0).toUpperCase() + cleaned.slice(1));
            }
          });
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
                traceEvents: mergeTraceEvents(m.traceEvents || [], res.trace_events),
                mandatoryCriteria: mandatory.length > 0 ? mandatory : undefined,
                priorityCriteria: priority.length > 0 ? priority : undefined,
                summaryCount: res.rooms && res.rooms.length > 0 ? res.rooms.length : undefined,
                followUpQuestions:
                  res.follow_up_questions && res.follow_up_questions.length > 0
                    ? res.follow_up_questions
                    : undefined,
                groundingReport: res.grounding_report || undefined,
              }
            : m
        )
      );
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Lỗi kết nối tới AI Agent";
      setConnectionError(errorMsg);
      const isQuotaError = /429|quota|resource_exhausted|rate limit|hạn mức|exceeded/i.test(errorMsg);
      const displayText = isQuotaError
        ? `⚠️ **Hạn mức sử dụng AI tạm thời bị gián đoạn (Quota Exceeded / 429)**\n\n${errorMsg}\n\n💡 **Cách khắc phục:**\n1. Tạo API Key mới tại [Google AI Studio](https://aistudio.google.com/).\n2. Mở file \`ai-agent/.env\`, cập nhật giá trị \`OPENAI_API_KEY\` bằng key mới.\n3. Khởi động lại dịch vụ AI Agent để tiếp tục sử dụng.`
        : `⚠️ Không thể kết nối tới máy chủ AI Agent (Port 8001): ${errorMsg}.\n\nNếu đang phát triển cục bộ, bạn hãy kiểm tra microservice AI bằng lệnh:\n\`python ai-agent/main.py\``;

      setMessages((prev) =>
        prev.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                isStreaming: false,
                statusText: undefined,
                text: displayText,
                followUpQuestions: isQuotaError ? ["Thử gửi lại sau khi cập nhật key"] : ["Thử gửi lại yêu cầu"],
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
    isPaging,
    sendMessage,
    rooms,
    currentPage,
    totalPages,
    totalRooms,
    goToPage,
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