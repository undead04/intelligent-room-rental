"use client";

import { useState, type ReactNode } from "react";
import type { AgentTraceEvent, ChatMessage } from "@/app/tim-kiem-ai/types";
import { USER_AVATAR } from "@/app/tim-kiem-ai/_constants/aiWorkspace";

interface ChatMessageItemProps {
  message: ChatMessage;
  isLatest?: boolean;
  isTyping?: boolean;
  onSelectQuestion?: (question: string) => void;
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g);
  return tokens.map((token, idx) => {
    if (token.startsWith("**") && token.endsWith("**") && token.length > 4) {
      return (
        <strong key={idx} className="font-bold text-[#0F172A]">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`") && token.length > 2) {
      return (
        <code
          key={idx}
          className="px-1 py-0.5 rounded bg-[#F1F5F9] text-[#0F5F4A] font-mono text-[11px]"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (token.startsWith("*") && token.endsWith("*") && token.length > 2) {
      return (
        <em key={idx} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    }
    return token;
  });
}

function isTableSeparatorLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|") || !trimmed.endsWith("|")) return false;
  const cells = trimmed
    .slice(1, -1)
    .split("|")
    .map((c) => c.trim());
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}

function parseTableRow(line: string): string[] {
  const trimmed = line.trim();
  const inner = trimmed.replace(/^\|/, "").replace(/\|$/, "");
  return inner.split("|").map((c) => c.trim());
}

function renderFormattedMarkdown(text: string, isStreaming?: boolean): ReactNode {
  const lines = text.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const rawLine = lines[i];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      i++;
      continue;
    }

    // Horizontal rule: ***, ---, ___
    if (/^(\*{3,}|-{3,}|_{3,})$/.test(trimmed)) {
      blocks.push(<hr key={`hr-${i}`} className="my-2 border-[#E2E8F0]" />);
      i++;
      continue;
    }

    // Markdown table block
    if (
      trimmed.startsWith("|") &&
      trimmed.endsWith("|") &&
      i + 1 < lines.length &&
      isTableSeparatorLine(lines[i + 1])
    ) {
      const headers = parseTableRow(trimmed);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length) {
        const rowLine = lines[i].trim();
        if (!rowLine.startsWith("|")) break;
        if (!isTableSeparatorLine(rowLine)) {
          rows.push(parseTableRow(rowLine));
        }
        i++;
      }
      blocks.push(
        <div
          key={`tbl-${i}`}
          className="my-2 overflow-x-auto rounded-xl border border-[#E2E8F0] shadow-2xs"
        >
          <table className="w-full text-left border-collapse text-[11px]">
            <thead>
              <tr className="bg-[#E6F4EE]/70 text-[#0F5F4A] border-b border-[#E2E8F0]">
                {headers.map((h, hIdx) => (
                  <th key={hIdx} className="px-2.5 py-2 font-bold whitespace-nowrap">
                    {renderInlineMarkdown(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F1F5F9] bg-white">
              {rows.map((r, rIdx) => (
                <tr key={rIdx} className="hover:bg-[#F8FAFC]">
                  {r.map((cell, cIdx) => (
                    <td key={cIdx} className="px-2.5 py-2 align-top text-[#1E293B] leading-snug">
                      {renderInlineMarkdown(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Headings: #, ##, ###, ####
    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = headingMatch[2];
      const sizeClass =
        level <= 2
          ? "text-[13.5px] font-extrabold text-[#0F5F4A] pt-1"
          : "text-[12.5px] font-bold text-[#0F5F4A] pt-0.5";
      blocks.push(
        <div key={`h-${i}`} className={sizeClass}>
          {renderInlineMarkdown(content)}
        </div>
      );
      i++;
      continue;
    }

    // Unordered or ordered list block
    if (/^(\*|-|•|\d+\.)\s+/.test(trimmed)) {
      const listItems: { marker: string; content: string }[] = [];
      while (i < lines.length) {
        const lTrim = lines[i].trim();
        const m = lTrim.match(/^(\*|-|•|\d+\.)\s+(.+)$/);
        if (!m) break;
        listItems.push({ marker: m[1], content: m[2] });
        i++;
      }
      blocks.push(
        <ul key={`ul-${i}`} className="space-y-1.5 pl-1 my-1">
          {listItems.map((item, idx) => {
            const isNumbered = /^\d+\.$/.test(item.marker);
            return (
              <li key={idx} className="flex items-start gap-2 text-[#121E1A] leading-relaxed">
                {isNumbered ? (
                  <span className="font-bold text-[#0F5F4A] shrink-0 min-w-[16px]">
                    {item.marker}
                  </span>
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A] mt-2 shrink-0" />
                )}
                <span className="flex-1">{renderInlineMarkdown(item.content)}</span>
              </li>
            );
          })}
        </ul>
      );
      continue;
    }

    // Standard paragraph (merge consecutive plain lines)
    const paraLines: string[] = [];
    while (i < lines.length) {
      const pTrim = lines[i].trim();
      if (
        !pTrim ||
        /^(\*{3,}|-{3,}|_{3,})$/.test(pTrim) ||
        /^(#{1,4})\s+/.test(pTrim) ||
        /^(\*|-|•|\d+\.)\s+/.test(pTrim) ||
        (pTrim.startsWith("|") && pTrim.endsWith("|"))
      ) {
        break;
      }
      paraLines.push(pTrim);
      i++;
    }

    const isLastBlock = i >= lines.length;
    blocks.push(
      <p key={`p-${i}`} className="font-normal text-[#121E1A] leading-relaxed">
        {renderInlineMarkdown(paraLines.join(" "))}
        {isStreaming && isLastBlock && (
          <span className="inline-block w-1.5 h-3.5 ml-0.5 align-middle bg-[#0F5F4A] animate-pulse" />
        )}
      </p>
    );
  }

  return <div className="space-y-2 text-[12px]">{blocks}</div>;
}

function formatUsageText(ev: AgentTraceEvent): string {
  const parts: string[] = [];
  if (ev.usage) {
    const inTok = ev.usage.input_tokens ?? 0;
    const outTok = ev.usage.output_tokens ?? 0;
    const reasoning = ev.usage.output_token_details?.reasoning;
    let tokStr = `${inTok} in / ${outTok} out tokens`;
    if (reasoning) {
      tokStr += ` (suy nghĩ: ${reasoning} tokens)`;
    }
    parts.push(tokStr);
  }
  if (ev.elapsed_ms !== undefined && ev.elapsed_ms !== null) {
    parts.push(`${ev.elapsed_ms} ms`);
  }
  return parts.length > 0 ? ` — ${parts.join(" · ")}` : "";
}

function cleanCriteriaText(text: string, prefixRegex: RegExp): string {
  if (!text) return "";
  const cleaned = text.replace(prefixRegex, "").trim();
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : text;
}

export default function ChatMessageItem({
  message,
  isLatest = false,
  isTyping = false,
  onSelectQuestion,
}: ChatMessageItemProps) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(null);

  if (message.sender === "user") {
    return (
      <div className="flex items-start gap-2.5">
        <div className="w-8 h-8 rounded-full overflow-hidden border border-[#E8E4DC] shrink-0 shadow-2xs">
          <img
            src={message.avatar || USER_AVATAR}
            alt="User avatar"
            className="w-full h-full object-cover"
          />
        </div>
        <div className="bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#121E1A] p-3.5 rounded-2xl rounded-tl-xs max-w-[90%] shadow-2xs font-medium leading-normal">
          {message.text}
        </div>
      </div>
    );
  }

  const traceEvents = message.traceEvents || [];
  const hasTrace = traceEvents.length > 0 || Boolean(message.isStreaming);
  const nodeStepCount = traceEvents.filter((e) => e.type === "node_step").length;
  const modelCallCount = traceEvents.filter((e) => e.type === "model_request").length;
  const toolCallCount = traceEvents.filter((e) => e.type === "tool_started").length;

  const finishedToolsMap = new Map<string, AgentTraceEvent>();
  for (const ev of traceEvents) {
    if (ev.type === "tool_finished" && ev.tool_call_id) {
      finishedToolsMap.set(ev.tool_call_id, ev);
    }
  }

  // Mặc định mở khi đang stream và tự thu gọn khi hoàn tất (trừ khi người dùng chủ động bấm)
  const isTraceExpanded = manualToggle !== null ? manualToggle : Boolean(message.isStreaming);

  return (
    <div className="flex items-start gap-2.5">
      <div className="w-8 h-8 rounded-full bg-[#0F5F4A] shrink-0 flex items-center justify-center text-white shadow-2xs">
        <span className="material-symbols-outlined text-[17px]">auto_awesome</span>
      </div>
      <div className="bg-white border border-[#E8E4DC] rounded-2xl rounded-tl-xs p-4 shadow-sm flex-1 space-y-3 min-w-0">
        {/* Khung hiển thị quá trình suy nghĩ & các bước thực hiện giống Streamlit */}
        {hasTrace && (
          <div className="rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] overflow-hidden text-[11px]">
            <button
              type="button"
              onClick={() => setManualToggle(!isTraceExpanded)}
              className="w-full px-3 py-2 flex items-center justify-between gap-2 text-left hover:bg-[#F1F5F9] transition cursor-pointer"
            >
              <div className="flex items-center gap-2 min-w-0">
                {message.isStreaming ? (
                  <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-ping shrink-0" />
                ) : (
                  <span className="material-symbols-outlined text-[15px] text-[#0F5F4A] shrink-0">
                    route
                  </span>
                )}
                <span className="font-semibold text-[#1E293B] truncate">
                  {message.isStreaming
                    ? message.statusText || "Đang xử lý..."
                    : nodeStepCount > 0
                    ? `Tiến trình LangGraph (${nodeStepCount} node, ${modelCallCount} model call, ${toolCallCount} tool call)`
                    : `Các bước thực hiện (${modelCallCount} model call, ${toolCallCount} tool call)`}
                </span>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {message.isStreaming && (
                  <span className="text-[10px] text-[#64748B] font-medium">
                    {modelCallCount} model · {toolCallCount} tool
                  </span>
                )}
                <span className="material-symbols-outlined text-[16px] text-[#64748B]">
                  {isTraceExpanded ? "expand_less" : "expand_more"}
                </span>
              </div>
            </button>

            {isTraceExpanded && (
              <div className="px-3 pb-3 pt-1.5 border-t border-[#E2E8F0] space-y-2 max-h-72 overflow-y-auto">
                {traceEvents.length === 0 ? (
                  <p className="text-[11px] text-[#64748B] italic">
                    Đang khởi tạo kết nối tới mô hình AI...
                  </p>
                ) : (
                  traceEvents.map((ev, idx) => {
                    if (ev.type === "node_step") {
                      const isOk = ev.status === "ok";
                      const isWarn = ev.status === "warning";
                      const statusIcon = isOk ? "check_circle" : isWarn ? "warning" : "error";
                      const statusColor = isOk ? "text-emerald-600" : isWarn ? "text-amber-600" : "text-rose-600";
                      return (
                        <div key={idx} className="flex items-start gap-1.5 text-[#334155] py-1 border-b border-[#F1F5F9] last:border-b-0">
                          <span className={`material-symbols-outlined text-[14px] ${statusColor} shrink-0 mt-0.5`}>
                            {statusIcon}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-bold text-[#0F172A]">{ev.label || ev.node}</span>
                              <code className="text-[9.5px] px-1 py-0.2 bg-[#F1F5F9] text-[#0F5F4A] rounded font-mono">
                                {ev.node}
                              </code>
                            </div>
                            {ev.details && (
                              <p className="text-[10px] text-[#64748B] truncate mt-0.5">{ev.details}</p>
                            )}
                          </div>
                        </div>
                      );
                    }

                    if (ev.type === "model_error") {
                      return (
                        <div key={idx} className="flex items-center gap-1.5 text-rose-600 text-[10.5px]">
                          <span className="material-symbols-outlined text-[14px]">error</span>
                          <span>Lỗi mô hình: {ev.error}</span>
                        </div>
                      );
                    }

                    if (ev.type === "model_request") {
                      return (
                        <div key={idx} className="flex items-center gap-1.5 text-[#334155] pt-0.5">
                          <span className="material-symbols-outlined text-[14px] text-[#0F5F4A]">
                            smart_toy
                          </span>
                          <span className="font-bold">Model call #{ev.model_call_index}</span>
                          <span className="text-[#64748B]">
                            | {ev.message_count ?? 0} messages | {ev.tool_count ?? 0} tools
                          </span>
                        </div>
                      );
                    }

                    if (ev.type === "model_response") {
                      const reqTools =
                        ev.requested_tools && ev.requested_tools.length > 0
                          ? ev.requested_tools
                          : (ev.tool_calls_requested || [])
                              .map((t) => t.name)
                              .filter(Boolean) as string[];
                      return (
                        <div key={idx} className="pl-4 text-[10.5px] text-[#475569]">
                          {reqTools.length > 0 ? (
                            <span>
                              ↳ yêu cầu {reqTools.length} tool call:{" "}
                              <code className="px-1 py-0.5 bg-[#E2E8F0] rounded text-[#0F5F4A] font-mono">
                                {reqTools.join(", ")}
                              </code>
                              {formatUsageText(ev)}
                            </span>
                          ) : (
                            <span>
                              ↳ trả câu trả lời, không yêu cầu tool
                              {formatUsageText(ev)}
                            </span>
                          )}
                        </div>
                      );
                    }

                    if (ev.type === "tool_started") {
                      const done = ev.tool_call_id
                        ? finishedToolsMap.get(ev.tool_call_id)
                        : undefined;
                      const resObj = done?.result;
                      const isFailed =
                        done &&
                        (done.status === "error" ||
                          done.status === "exception" ||
                          (resObj && typeof resObj === "object" && (resObj as Record<string, unknown>).ok === false));

                      const argsObj = ev.arguments || ev.args || {};

                      return (
                        <div
                          key={idx}
                          className="rounded-lg border border-[#CBD5E1] bg-white p-2.5 space-y-1.5 shadow-2xs"
                        >
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-1.5">
                              <span className="material-symbols-outlined text-[14px] text-[#0F5F4A]">
                                build
                              </span>
                              <span className="font-bold text-[#0F172A] font-mono">
                                {ev.tool_name}
                              </span>
                              {!done ? (
                                <span className="px-1.5 py-0.5 text-[9.5px] font-bold rounded bg-[#FEF3C7] text-[#D97706]">
                                  đang chạy
                                </span>
                              ) : isFailed ? (
                                <span className="px-1.5 py-0.5 text-[9.5px] font-bold rounded bg-[#FEE2E2] text-[#DC2626]">
                                  lỗi
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 text-[9.5px] font-bold rounded bg-[#DCFCE7] text-[#15803D]">
                                  ok
                                </span>
                              )}
                            </div>
                            {done?.elapsed_ms !== undefined && (
                              <span className="text-[10px] text-[#64748B] font-mono">
                                {done.elapsed_ms} ms
                              </span>
                            )}
                          </div>

                          <div className="text-[10px] text-[#64748B] font-mono">
                            Args:
                            <pre className="mt-0.5 p-1.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded text-[10px] text-[#1E293B] overflow-x-auto whitespace-pre-wrap">
                              {JSON.stringify(argsObj, null, 2)}
                            </pre>
                          </div>

                          {done && done.result !== undefined && (
                            <details className="text-[10px] text-[#475569]">
                              <summary className="cursor-pointer font-semibold text-[#0F5F4A] hover:underline select-none">
                                Xem kết quả (Result)
                              </summary>
                              <pre className="mt-1 p-1.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded text-[10px] text-[#1E293B] max-h-40 overflow-auto whitespace-pre-wrap font-mono">
                                {typeof done.result === "string"
                                  ? done.result
                                  : JSON.stringify(done.result, null, 2)}
                              </pre>
                            </details>
                          )}
                        </div>
                      );
                    }

                    return null;
                  })
                )}
              </div>
            )}
          </div>
        )}

        {/* Nội dung văn bản trả lời (stream từng từ theo thời gian thực + định dạng Markdown) */}
        {message.text ? (
          renderFormattedMarkdown(message.text, message.isStreaming)
        ) : message.isStreaming ? (
          <p className="text-[11px] text-[#64748B] italic">
            {message.statusText || "AI đang suy nghĩ và xử lý yêu cầu..."}
          </p>
        ) : null}

        {/* Condition: Bắt buộc */}
        {message.mandatoryCriteria && (
          <div className="space-y-1.5">
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#E6F4EE] text-[#0F5F4A] text-[10px] font-bold rounded-full border border-[#0F5F4A]/20">
              <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]"></span>
              <span>Bắt buộc</span>
            </span>
            <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
              {message.mandatoryCriteria.map((criteria, index) => (
                <li key={index} className="flex items-center gap-2 text-[#0F5F4A]">
                  <span className="material-symbols-outlined text-[15px] font-bold">check_circle</span>
                  <span>{cleanCriteriaText(criteria, /^(?:bắt buộc|bat buoc)[:\s-]*/i)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Condition: Ưu tiên */}
        {message.priorityCriteria && (
          <div className={`space-y-1.5 ${message.mandatoryCriteria ? "pt-2 border-t border-[#F1F5F9]" : ""}`}>
            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-[#FFF5E6] text-[#D97706] text-[10px] font-bold rounded-full border border-[#FFE0B2]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#FF6B4A]"></span>
              <span>Ưu tiên</span>
            </span>
            <ul className="space-y-1.5 pl-1 text-[11px] text-[#3F4944] font-medium">
              {message.priorityCriteria.map((criteria, index) => (
                <li key={index} className="flex items-center gap-2 text-[#B45309]">
                  <span className="material-symbols-outlined text-[15px] font-bold text-[#D97706]">star</span>
                  <span>{cleanCriteriaText(criteria, /^(?:ưu tiên|uu tien)[:\s-]*/i)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Clarification prompt text */}
        {message.summaryCount ? (
          <p className="text-[11px] text-[#6F7974] pt-1 leading-normal border-t border-[#F1F5F9]">
            Homigo đã tìm thấy <span className="font-bold text-[#0F5F4A]">{message.summaryCount} phòng</span> phù hợp nhất với các tiêu chí của bạn.
          </p>
        ) : null}

        {/* Self-RAG Grounding Verification Badge */}
        {message.groundingReport?.is_grounded && !message.isStreaming && message.summaryCount ? (
          <div className="pt-1">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-[10.5px] font-semibold">
              <span className="material-symbols-outlined text-[14px] text-emerald-600">verified</span>
              <span>
                Đã kiểm chứng tính xác thực (Self-RAG Grounded
                {message.groundingReport.groundedness_score
                  ? ` ${Math.round(Number(message.groundingReport.groundedness_score) * 100)}%`
                  : ""}
                )
              </span>
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}