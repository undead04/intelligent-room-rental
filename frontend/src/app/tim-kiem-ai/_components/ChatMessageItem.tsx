"use client";

import { type ReactNode } from "react";
import AgentTracePanel from "@/app/tim-kiem-ai/_components/AgentTracePanel";
import type { ChatMessage } from "@/app/tim-kiem-ai/types";
import { USER_AVATAR } from "@/app/tim-kiem-ai/_constants/aiWorkspace";

interface ChatMessageItemProps {
  message: ChatMessage;
  isLatest?: boolean;
  isTyping?: boolean;
  onSelectQuestion?: (question: string) => void;
}

function isSafeHref(url: string): boolean {
  const trimmed = url.trim();
  return (
    trimmed.startsWith("https://") ||
    trimmed.startsWith("http://") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("#")
  );
}

function renderInlineMarkdown(text: string): ReactNode[] {
  const tokens = text.split(/(\[[^\]\n]+\]\([^)\s]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*)/g);
  return tokens.map((token, idx) => {
    const linkMatch = token.match(/^\[([^\]\n]+)\]\(([^)\s]+)\)$/);
    if (linkMatch) {
      const [, label, href] = linkMatch;
      if (isSafeHref(href)) {
        return (
          <a
            key={idx}
            href={href}
            target={href.startsWith("http") ? "_blank" : undefined}
            rel={href.startsWith("http") ? "noopener noreferrer" : undefined}
            className="font-semibold text-[#0F5F4A] underline decoration-[#0F5F4A]/40 underline-offset-2 hover:text-[#0B4A39]"
          >
            {label}
          </a>
        );
      }
      return label;
    }

    if (token.startsWith("**") && token.endsWith("**") && token.length > 4) {
      return (
        <strong key={idx} className="font-semibold text-[#0F172A]">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`") && token.length > 2) {
      return (
        <code
          key={idx}
          className="px-1.5 py-0.5 rounded-md bg-[#F1F5F9] text-[#0F5F4A] font-mono text-[11.5px] break-all"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (token.startsWith("*") && token.endsWith("*") && token.length > 2) {
      return (
        <em key={idx} className="italic text-[#334155]">
          {token.slice(1, -1)}
        </em>
      );
    }
    return token;
  });
}

function renderKeyValueOrInline(text: string): ReactNode {
  const trimmed = text.trim();
  // Nhấn nhẹ phần nhãn (vd: "Giá thuê: 4.500.000đ") khi không bắt đầu bằng markdown bold
  if (!trimmed.startsWith("**") && !trimmed.startsWith("[") && !trimmed.startsWith("`")) {
    const kvMatch = trimmed.match(/^([^:]{2,32}):\s+(.+)$/);
    if (kvMatch) {
      return (
        <>
          <span className="font-semibold text-[#334155]">{kvMatch[1]}:</span>{" "}
          <span>{renderInlineMarkdown(kvMatch[2])}</span>
        </>
      );
    }
  }
  return renderInlineMarkdown(text);
}

const SECTION_EMOJI_REGEX = /^(🏆|⚖️|📋|📊|💡|📌|📍|⚠️|👉|✅|🔍)\s+(.+)$/;
const LIST_ITEM_REGEX = /^(\s*)(\*|-|•|\d+\.)\s+(.+)$/;

function isEmojiSectionLine(line: string): boolean {
  return SECTION_EMOJI_REGEX.test(line.trim());
}

function isBlockStartLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return true;
  if (/^```/.test(trimmed)) return true;
  if (/^(\*{3,}|-{3,}|_{3,})$/.test(trimmed)) return true;
  if (/^(#{1,4})\s+/.test(trimmed)) return true;
  if (/^>\s+/.test(trimmed)) return true;
  if (LIST_ITEM_REGEX.test(line)) return true;
  if (trimmed.startsWith("|") && trimmed.endsWith("|")) return true;
  if (isEmojiSectionLine(trimmed)) return true;
  return false;
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

interface ParsedListItem {
  marker: string;
  content: string;
  children: { marker: string; content: string }[];
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

    // Fenced code block: ```...```
    if (trimmed.startsWith("```")) {
      i++;
      const codeLines: string[] = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length && lines[i].trim().startsWith("```")) {
        i++;
      }
      blocks.push(
        <pre
          key={`code-${i}`}
          className="rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] p-3 text-[11.5px] font-mono text-[#1E293B] overflow-x-auto whitespace-pre-wrap break-words"
        >
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
      continue;
    }

    // Horizontal rule: ***, ---, ___
    if (/^(\*{3,}|-{3,}|_{3,})$/.test(trimmed)) {
      blocks.push(<hr key={`hr-${i}`} className="my-2.5 border-[#E8E4DC]" />);
      i++;
      continue;
    }

    // Blockquote: > ...
    if (/^>\s+/.test(trimmed)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^>\s*/.test(lines[i].trim())) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i++;
      }
      blocks.push(
        <blockquote
          key={`bq-${i}`}
          className="border-l-3 border-[#0F5F4A] bg-[#F5F9F7] rounded-r-xl px-3 py-2 text-[#334155] space-y-1"
        >
          {quoteLines.map((qLine, qIdx) => (
            <p key={qIdx} className="leading-relaxed">
              {renderInlineMarkdown(qLine)}
            </p>
          ))}
        </blockquote>
      );
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
          className="overflow-x-auto rounded-xl border border-[#E2E8F0] shadow-2xs"
        >
          <table className="w-full text-left border-collapse text-[12px]">
            <thead>
              <tr className="bg-[#E6F4EE]/75 text-[#0F5F4A] border-b border-[#E2E8F0]">
                {headers.map((h, hIdx) => (
                  <th key={hIdx} className="px-3 py-2 font-bold whitespace-nowrap">
                    {renderInlineMarkdown(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[#F1F5F9] bg-white">
              {rows.map((r, rIdx) => (
                <tr key={rIdx} className="hover:bg-[#F8FAFC]">
                  {r.map((cell, cIdx) => (
                    <td key={cIdx} className="px-3 py-2 align-top text-[#1E293B] leading-snug">
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
      const hasPrev = blocks.length > 0;
      const sizeClass =
        level <= 2
          ? `text-[14px] font-bold text-[#0F5F4A] ${hasPrev ? "pt-2.5 border-t border-[#EDF2EE]" : ""}`
          : `text-[13px] font-bold text-[#0F5F4A] ${hasPrev ? "pt-1.5" : ""}`;
      blocks.push(
        <div key={`h-${i}`} className={sizeClass}>
          {renderInlineMarkdown(content)}
        </div>
      );
      i++;
      continue;
    }

    // Emoji section header / callout line (rất phổ biến trong phản hồi Homigo AI)
    const emojiMatch = trimmed.match(SECTION_EMOJI_REGEX);
    if (emojiMatch) {
      const emoji = emojiMatch[1];
      const body = emojiMatch[2];
      const hasPrev = blocks.length > 0;
      // Kiểm tra xem dòng này là tiêu đề dẫn vào list ngay sau đó hay là callout độc lập
      let nextNonEmptyIdx = i + 1;
      while (nextNonEmptyIdx < lines.length && !lines[nextNonEmptyIdx].trim()) {
        nextNonEmptyIdx++;
      }
      const nextIsList =
        nextNonEmptyIdx < lines.length && LIST_ITEM_REGEX.test(lines[nextNonEmptyIdx]);
      const isSectionHeading =
        nextIsList ||
        /:\*\*$/.test(trimmed) ||
        /:$/.test(trimmed);

      const isLastBlock = i >= lines.length - 1;

      if (isSectionHeading) {
        blocks.push(
          <div
            key={`sec-${i}`}
            className={`flex items-start gap-2 ${hasPrev ? "pt-3 border-t border-[#EDF2EE]" : ""}`}
          >
            <span className="text-[14px] leading-snug shrink-0">{emoji}</span>
            <div className="font-semibold text-[#0F5F4A] leading-snug">
              {renderInlineMarkdown(body)}
              {isStreaming && isLastBlock && (
                <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
              )}
            </div>
          </div>
        );
      } else {
        const calloutTone =
          emoji === "⚠️"
            ? "bg-amber-50/80 border-amber-200/80 text-amber-950"
            : emoji === "👉"
            ? "bg-[#E6F4EE]/60 border-[#0F5F4A]/20 text-[#121E1A]"
            : "bg-[#FAF8F4] border-[#E8E4DC] text-[#121E1A]";
        blocks.push(
          <div
            key={`call-${i}`}
            className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 ${calloutTone}`}
          >
            <span className="text-[14px] leading-relaxed shrink-0">{emoji}</span>
            <div className="flex-1 min-w-0 leading-relaxed">
              {renderInlineMarkdown(body)}
              {isStreaming && isLastBlock && (
                <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
              )}
            </div>
          </div>
        );
      }
      i++;
      continue;
    }

    // Unordered or ordered list block (hỗ trợ nested items)
    const firstListMatch = rawLine.match(LIST_ITEM_REGEX);
    if (firstListMatch) {
      const baseIndent = firstListMatch[1].length;
      const items: ParsedListItem[] = [];

      while (i < lines.length) {
        const curLine = lines[i];
        const m = curLine.match(LIST_ITEM_REGEX);
        if (!m) {
          // Cho phép bỏ qua dòng trống đơn nếu dòng sau vẫn thuộc cùng danh sách
          if (
            !curLine.trim() &&
            i + 1 < lines.length &&
            LIST_ITEM_REGEX.test(lines[i + 1])
          ) {
            i++;
            continue;
          }
          break;
        }

        const indent = m[1].length;
        const marker = m[2];
        const content = m[3];
        const isSubItem = indent > baseIndent && items.length > 0 && !/^\d+\.$/.test(marker);

        if (isSubItem) {
          items[items.length - 1].children.push({ marker, content });
        } else {
          items.push({ marker, content, children: [] });
        }
        i++;
      }

      const hasNestedChildren = items.some((it) => it.children.length > 0);
      const isLastBlock = i >= lines.length;

      if (hasNestedChildren) {
        // Nhóm mỗi mục cha + mục con thành thẻ tóm tắt tách bạch, tránh dính chùm
        blocks.push(
          <div key={`nlist-${i}`} className="space-y-2.5">
            {items.map((item, idx) => {
              const isNumbered = /^\d+\.$/.test(item.marker);
              const badgeText = isNumbered ? item.marker.replace(/\.$/, "") : "•";
              return (
                <div
                  key={idx}
                  className="rounded-xl border border-[#E8E4DC] bg-[#FAFBF9] px-3 py-2.5 space-y-1.5"
                >
                  <div className="flex items-start gap-2.5">
                    <span className="w-5 h-5 rounded-md bg-[#E6F4EE] text-[#0F5F4A] text-[11px] font-bold flex items-center justify-center shrink-0 mt-0.5">
                      {badgeText}
                    </span>
                    <div className="flex-1 min-w-0 font-medium text-[#121E1A] leading-snug">
                      {renderInlineMarkdown(item.content)}
                      {isStreaming && isLastBlock && idx === items.length - 1 && item.children.length === 0 && (
                        <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
                      )}
                    </div>
                  </div>
                  {item.children.length > 0 && (
                    <ul className="pl-7.5 space-y-1 text-[12px] text-[#4A5550]">
                      {item.children.map((sub, subIdx) => (
                        <li key={subIdx} className="flex items-start gap-2 leading-relaxed">
                          <span className="w-1 h-1 rounded-full bg-[#0F5F4A]/60 mt-2 shrink-0" />
                          <span className="flex-1 min-w-0">
                            {renderKeyValueOrInline(sub.content)}
                            {isStreaming &&
                              isLastBlock &&
                              idx === items.length - 1 &&
                              subIdx === item.children.length - 1 && (
                                <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
                              )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        );
      } else {
        blocks.push(
          <ul key={`ul-${i}`} className="space-y-2 pl-1">
            {items.map((item, idx) => {
              const isNumbered = /^\d+\.$/.test(item.marker);
              return (
                <li key={idx} className="flex items-start gap-2.5 text-[#121E1A] leading-relaxed">
                  {isNumbered ? (
                    <span className="font-bold text-[#0F5F4A] shrink-0 min-w-[18px]">
                      {item.marker}
                    </span>
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A] mt-2 shrink-0" />
                  )}
                  <span className="flex-1 min-w-0">
                    {renderKeyValueOrInline(item.content)}
                    {isStreaming && isLastBlock && idx === items.length - 1 && (
                      <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        );
      }
      continue;
    }

    // Standard paragraph (merge consecutive plain lines)
    const paraLines: string[] = [];
    while (i < lines.length) {
      if (isBlockStartLine(lines[i])) {
        break;
      }
      paraLines.push(lines[i].trim());
      i++;
    }

    const isLastBlock = i >= lines.length;
    blocks.push(
      <p key={`p-${i}`} className="font-normal text-[#121E1A] leading-relaxed">
        {renderInlineMarkdown(paraLines.join(" "))}
        {isStreaming && isLastBlock && (
          <span className="inline-block w-1.5 h-3.5 ml-1 align-middle bg-[#0F5F4A] animate-pulse" />
        )}
      </p>
    );
  }

  return (
    <div className="space-y-3 text-[13px] leading-[1.65] text-[#121E1A] break-words [overflow-wrap:anywhere]">
      {blocks}
    </div>
  );
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
  void isLatest;
  void isTyping;
  void onSelectQuestion;

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
        <div className="bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#121E1A] px-3.5 py-2.5 rounded-2xl rounded-tl-xs max-w-[85%] min-w-0 shadow-2xs text-[13px] font-medium leading-relaxed whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {message.text}
        </div>
      </div>
    );
  }

  const traceEvents = message.traceEvents || [];

  return (
    <div className="flex items-start gap-2.5">
      <div className="w-8 h-8 rounded-full bg-[#0F5F4A] shrink-0 flex items-center justify-center text-white shadow-2xs">
        <span className="material-symbols-outlined text-[17px]">auto_awesome</span>
      </div>
      <div className="bg-white border border-[#E8E4DC] rounded-2xl rounded-tl-xs p-4 shadow-sm flex-1 space-y-3.5 min-w-0">
        {/* Khung hiển thị quá trình suy nghĩ & từng bước LangGraph */}
        <AgentTracePanel
          traceEvents={traceEvents}
          isStreaming={message.isStreaming}
          statusText={message.statusText}
        />

        {/* Nội dung văn bản trả lời (stream từng từ theo thời gian thực + định dạng Markdown) */}
        {message.text ? (
          renderFormattedMarkdown(message.text, message.isStreaming)
        ) : message.isStreaming ? (
          <p className="text-[12px] text-[#64748B] italic">
            {message.statusText || "AI đang suy nghĩ và xử lý yêu cầu..."}
          </p>
        ) : null}

        {/* Tiêu chí đã nhận diện (Bắt buộc & Ưu tiên) */}
        {(message.mandatoryCriteria?.length || message.priorityCriteria?.length) ? (
          <div className="pt-3 border-t border-[#EDF2EE] space-y-2.5">
            {message.mandatoryCriteria && message.mandatoryCriteria.length > 0 && (
              <div className="space-y-1.5">
                <div className="inline-flex items-center gap-1.5 text-[10.5px] font-bold text-[#0F5F4A] uppercase tracking-wide">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A]" />
                  <span>Tiêu chí bắt buộc</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {message.mandatoryCriteria.map((criteria, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#E6F4EE] border border-[#0F5F4A]/15 text-[#0F5F4A] text-[11px] font-semibold"
                    >
                      <span className="material-symbols-outlined text-[13px]">check_circle</span>
                      <span>{cleanCriteriaText(criteria, /^(?:bắt buộc|bat buoc)[:\s-]*/i)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {message.priorityCriteria && message.priorityCriteria.length > 0 && (
              <div className="space-y-1.5">
                <div className="inline-flex items-center gap-1.5 text-[10.5px] font-bold text-[#B45309] uppercase tracking-wide">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#E88C38]" />
                  <span>Tiêu chí ưu tiên</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {message.priorityCriteria.map((criteria, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#FFF5E6] border border-[#FFE0B2] text-[#B45309] text-[11px] font-semibold"
                    >
                      <span className="material-symbols-outlined text-[13px] text-[#D97706]">star</span>
                      <span>{cleanCriteriaText(criteria, /^(?:ưu tiên|uu tien)[:\s-]*/i)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}

        {/* Tóm tắt số lượng & kiểm chứng Grounding */}
        {(message.summaryCount ||
          (message.groundingReport?.is_grounded && !message.isStreaming && message.summaryCount)) ? (
          <div className="pt-2.5 border-t border-[#EDF2EE] flex flex-wrap items-center justify-between gap-2">
            {message.summaryCount ? (
              <p className="text-[11.5px] text-[#6F7974] leading-normal">
                Homigo đã tìm thấy{" "}
                <span className="font-bold text-[#0F5F4A]">{message.summaryCount} phòng</span>{" "}
                phù hợp nhất với các tiêu chí của bạn.
              </p>
            ) : null}

            {message.groundingReport?.is_grounded && !message.isStreaming && message.summaryCount ? (
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
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}