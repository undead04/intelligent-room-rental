import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/app/tim-kiem-ai/types";
import {
  AI_FOLLOW_UP_MESSAGE,
  AI_REPLY_DELAY_MS,
  INITIAL_MESSAGES,
  USER_AVATAR,
} from "@/app/tim-kiem-ai/_constants/aiWorkspace";

export function useAiChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const replyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Rời trang giữa lúc AI đang trả lời thì huỷ timer, tránh set state sau unmount
  useEffect(() => () => {
    if (replyTimer.current) clearTimeout(replyTimer.current);
  }, []);

  const sendMessage = (event?: React.FormEvent) => {
    event?.preventDefault();
    if (!inputValue.trim()) return;

    const userText = inputValue;
    setInputValue("");

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: "user",
      text: userText,
      avatar: USER_AVATAR,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    replyTimer.current = setTimeout(() => {
      const aiMessage: ChatMessage = { ...AI_FOLLOW_UP_MESSAGE, id: `msg-${Date.now() + 1}` };
      setMessages((prev) => [...prev, aiMessage]);
      setIsTyping(false);
    }, AI_REPLY_DELAY_MS);
  };

  return { messages, inputValue, setInputValue, isTyping, sendMessage };
}