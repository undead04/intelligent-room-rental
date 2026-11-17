"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { AgentTraceEvent, VerifierFailureItem } from "@/types/dto/agent";
import {
  buildTraceStepGroups,
  formatDuration,
  formatNumber,
  formatScalarValue,
  summarizeModelOutput,
  summarizeToolArgs,
  summarizeToolResult,
  summarizeTrace,
  traceEventsToJsonl,
  type ModelCallTraceItem,
  type ToolCallTraceItem,
  type TraceStepGroup,
  type TraceTimelineItem,
  type VerifierTraceItem,
} from "@/app/tim-kiem-ai/_components/traceUtils";

interface AgentTracePanelProps {
  traceEvents: AgentTraceEvent[];
  isStreaming?: boolean;
  statusText?: string;
}

type InspectorFilter = "all" | "model" | "tool" | "verifier";

function formatPrettyJson(data: unknown): string {
  if (typeof data === "string") {
    try {
      const parsed = JSON.parse(data);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return data;
    }
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function StatusBadge({ status }: { status: "running" | "ok" | "warning" | "error" }) {
  if (status === "running") {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-[#E6F4EE] text-[#0F5F4A] text-[9.5px] font-bold">
        <span className="w-1.5 h-1.5 rounded-full bg-[#0F5F4A] animate-pulse" />
        đang chạy
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-red-50 border border-red-200 text-[#DC2626] text-[9.5px] font-bold">
        <span className="material-symbols-outlined text-[11px]">error</span>
        lỗi
      </span>
    );
  }
  if (status === "warning") {
    return (
      <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-amber-50 border border-amber-200 text-[#D97706] text-[9.5px] font-bold">
        <span className="material-symbols-outlined text-[11px]">warning</span>
        lưu ý
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-[#E6F4EE] text-[#0F5F4A] text-[9.5px] font-bold">
      <span className="material-symbols-outlined text-[11px]">check_circle</span>
      ok
    </span>
  );
}

function FailureDetailRow({ failure }: { failure: VerifierFailureItem | string }) {
  if (typeof failure === "string") {
    return (
      <div className="px-2 py-1 rounded bg-red-50/80 border border-red-200 text-[10px] text-[#991B1B]">
        {failure}
      </div>
    );
  }
  return (
    <div className="p-2 rounded-lg bg-red-50/80 border border-red-200 space-y-1 text-[10px]">
      <div className="flex items-center justify-between gap-1.5 flex-wrap">
        <code className="px-1.5 py-0.5 rounded bg-white border border-red-200 text-[#DC2626] font-mono font-semibold">
          {failure.condition_id || "condition"}
        </code>
        {(failure.tier || failure.verifier_type) && (
          <span className="text-[9.5px] font-semibold text-[#B91C1C]">
            {failure.tier || failure.verifier_type}
          </span>
        )}
      </div>
      {failure.message && <p className="text-[#7F1D1D] leading-snug">{failure.message}</p>}
      {(failure.actual !== undefined || failure.expected !== undefined) && (
        <div className="flex flex-wrap gap-2 text-[9.5px] text-[#991B1B] font-mono">
          {failure.actual !== undefined && <span>Thực tế: {formatScalarValue(failure.actual)}</span>}
          {failure.expected !== undefined && <span>Kỳ vọng: {formatScalarValue(failure.expected)}</span>}
        </div>
      )}
    </div>
  );
}

function RenderInputMessages({ input }: { input: unknown }) {
  if (Array.isArray(input)) {
    return (
      <div className="space-y-1.5">
        {input.map((msg, idx) => {
          const m = msg && typeof msg === "object" ? (msg as Record<string, unknown>) : null;
          if (!m) {
            return (
              <pre
                key={idx}
                className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10.5px] font-mono whitespace-pre-wrap break-words"
              >
                {formatPrettyJson(msg)}
              </pre>
            );
          }
          const role = String(m.role || m.type || `msg_${idx + 1}`);
          const roleColor =
            role === "system"
              ? "bg-slate-100 text-slate-700"
              : role === "human" || role === "user"
              ? "bg-[#E6F4EE] text-[#0F5F4A]"
              : role === "tool"
              ? "bg-amber-50 text-[#B45309]"
              : "bg-indigo-50 text-indigo-700";
          return (
            <div key={idx} className="rounded-lg border border-[#E8E4DC] bg-[#FAF8F4] p-2 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[9.5px] font-bold uppercase ${roleColor}`}>
                  {role}
                </span>
                <span className="text-[9.5px] text-[#6F7974]">#{idx + 1}</span>
              </div>
              <pre className="text-[10.5px] text-[#121E1A] font-mono whitespace-pre-wrap break-words max-h-64 overflow-auto">
                {typeof m.content === "string" ? m.content : formatPrettyJson(m)}
              </pre>
            </div>
          );
        })}
      </div>
    );
  }
  return (
    <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10.5px] text-[#121E1A] font-mono whitespace-pre-wrap break-words max-h-72 overflow-auto">
      {formatPrettyJson(input)}
    </pre>
  );
}

function InlineModelCallCard({ item }: { item: ModelCallTraceItem }) {
  const [tab, setTab] = useState<"none" | "input" | "output" | "json">("none");

  const toggleTab = (next: "input" | "output" | "json") => {
    setTab((prev) => (prev === next ? "none" : next));
  };

  const hasTokens = item.tokensIn > 0 || item.tokensOut > 0;

  return (
    <div className="rounded-lg border border-[#D8E4DF] bg-white p-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="material-symbols-outlined text-[14px] text-[#0F5F4A] shrink-0">smart_toy</span>
          <span className="font-bold text-[#121E1A]">LLM #{item.callIndex}</span>
          <StatusBadge status={item.status} />
          {item.messageCount !== undefined && (
            <span className="text-[10px] text-[#6F7974]">
              {item.messageCount} msg{item.toolCount ? ` · ${item.toolCount} tool` : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-[#4A5550]">
          {hasTokens && (
            <span className="px-1.5 py-0.5 rounded bg-[#F5F2EB] text-[#121E1A]">
              {item.tokensEstimated ? "~" : ""}
              {formatNumber(item.tokensIn)} in / {formatNumber(item.tokensOut)} out
              {item.cachedTokens > 0 ? ` (${formatNumber(item.cachedTokens)} cache)` : ""}
            </span>
          )}
          {item.durationMs !== undefined && (
            <span className="font-semibold text-[#0F5F4A]">{formatDuration(item.durationMs)}</span>
          )}
        </div>
      </div>

      {item.error ? (
        <div className="p-1.5 rounded bg-red-50 border border-red-200 text-[#DC2626] text-[10.5px] break-words">
          {item.error}
        </div>
      ) : (
        <p className="text-[10.5px] text-[#4A5550] leading-snug break-words">
          {summarizeModelOutput(item)}
        </p>
      )}

      <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
        {item.input !== undefined && (
          <button
            type="button"
            onClick={() => toggleTab("input")}
            className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
              tab === "input"
                ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
            }`}
          >
            Input
          </button>
        )}
        {item.output !== undefined && (
          <button
            type="button"
            onClick={() => toggleTab("output")}
            className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
              tab === "output"
                ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
            }`}
          >
            Output
          </button>
        )}
        <button
          type="button"
          onClick={() => toggleTab("json")}
          className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
            tab === "json"
              ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
              : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
          }`}
        >
          JSON
        </button>
      </div>

      {tab === "input" && item.input !== undefined && (
        <div className="pt-1 max-h-60 overflow-y-auto">
          <RenderInputMessages input={item.input} />
        </div>
      )}
      {tab === "output" && item.output !== undefined && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-60 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.output)}
        </pre>
      )}
      {tab === "json" && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-60 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.rawEvents)}
        </pre>
      )}
    </div>
  );
}

function InlineToolCallCard({ item }: { item: ToolCallTraceItem }) {
  const [tab, setTab] = useState<"none" | "args" | "result" | "state" | "json">("none");
  const argPills = useMemo(() => summarizeToolArgs(item.toolName, item.args), [item.toolName, item.args]);

  const toggleTab = (next: "args" | "result" | "state" | "json") => {
    setTab((prev) => (prev === next ? "none" : next));
  };

  return (
    <div className="rounded-lg border border-[#D8E4DF] bg-white p-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="material-symbols-outlined text-[14px] text-[#E88C38] shrink-0">build</span>
          <code className="font-bold text-[#121E1A] font-mono text-[11px]">{item.toolName}</code>
          <StatusBadge status={item.status} />
        </div>
        {item.durationMs !== undefined && (
          <span className="text-[10px] font-mono font-semibold text-[#0F5F4A]">
            {formatDuration(item.durationMs)}
          </span>
        )}
      </div>

      {argPills.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {argPills.map((p, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[#FAF8F4] border border-[#E8E4DC] text-[10px] text-[#4A5550] max-w-full"
            >
              <span className="text-[#6F7974]">{p.label}:</span>
              <span className="font-semibold text-[#121E1A] truncate max-w-[200px]">{p.value}</span>
            </span>
          ))}
        </div>
      )}

      <div className="text-[10.5px] text-[#121E1A] flex items-start gap-1">
        <span className="text-[#0F5F4A] font-bold shrink-0">→</span>
        <span className={item.error ? "text-[#DC2626] font-medium" : "text-[#4A5550]"}>
          {summarizeToolResult(item)}
        </span>
      </div>

      {item.stateDiff.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 text-[9.5px] bg-[#E6F4EE]/60 border border-[#0F5F4A]/15 rounded px-1.5 py-1">
          <span className="font-bold text-[#0F5F4A]">Δ State:</span>
          {item.stateDiff.map((d) => (
            <span key={d.key} className="font-mono text-[#121E1A]">
              {d.key}: {formatScalarValue(d.before)} → <strong>{formatScalarValue(d.after)}</strong>
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
        <button
          type="button"
          onClick={() => toggleTab("args")}
          className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
            tab === "args"
              ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
              : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
          }`}
        >
          Args
        </button>
        {item.result !== undefined && (
          <button
            type="button"
            onClick={() => toggleTab("result")}
            className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
              tab === "result"
                ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
            }`}
          >
            Result
          </button>
        )}
        {(item.stateBefore !== undefined || item.stateAfter !== undefined) && (
          <button
            type="button"
            onClick={() => toggleTab("state")}
            className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
              tab === "state"
                ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
            }`}
          >
            State
          </button>
        )}
        <button
          type="button"
          onClick={() => toggleTab("json")}
          className={`px-2 py-0.5 rounded text-[9.5px] font-semibold border transition cursor-pointer ${
            tab === "json"
              ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
              : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
          }`}
        >
          JSON
        </button>
      </div>

      {tab === "args" && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-52 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.args)}
        </pre>
      )}
      {tab === "result" && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-60 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.result)}
        </pre>
      )}
      {tab === "state" && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-52 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson({ state_before: item.stateBefore, state_after: item.stateAfter })}
        </pre>
      )}
      {tab === "json" && (
        <pre className="p-2 bg-[#FAF8F4] border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-60 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.rawEvents)}
        </pre>
      )}
    </div>
  );
}

function InlineVerifierCard({ item }: { item: VerifierTraceItem }) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div
      className={`rounded-lg border p-2 space-y-1.5 ${
        item.passed ? "border-[#0F5F4A]/25 bg-[#E6F4EE]/50" : "border-red-200 bg-red-50/50"
      }`}
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span
            className={`material-symbols-outlined text-[14px] ${
              item.passed ? "text-[#0F5F4A]" : "text-[#DC2626]"
            }`}
          >
            {item.passed ? "verified_user" : "gpp_bad"}
          </span>
          <span className="font-bold text-[#121E1A]">
            DoD Verifier: {item.passed ? "Đạt chuẩn" : "Không đạt"}
          </span>
        </div>
        <div className="flex items-center gap-1 text-[9.5px] font-mono">
          <span className="px-1.5 py-0.5 rounded bg-white border border-[#D8E4DF] text-[#121E1A] font-semibold">
            next: {item.nextDecision}
          </span>
          {item.failedTier && (
            <span className="px-1.5 py-0.5 rounded bg-red-100 text-[#DC2626] font-semibold">
              tier: {item.failedTier}
            </span>
          )}
          {item.answerRetry > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-amber-100 text-[#B45309] font-semibold">
              retry #{item.answerRetry}
            </span>
          )}
        </div>
      </div>

      <p className="text-[10.5px] text-[#4A5550]">{item.dodSummary}</p>

      {item.failures.length > 0 && (
        <div className="space-y-1">
          {item.failures.map((f, i) => (
            <FailureDetailRow key={i} failure={f} />
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={() => setShowRaw((v) => !v)}
        className="px-2 py-0.5 rounded text-[9.5px] font-semibold border bg-white text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB] cursor-pointer"
      >
        {showRaw ? "Ẩn Verifier JSON" : "Xem Verifier JSON"}
      </button>

      {showRaw && (
        <pre className="p-2 bg-white border border-[#E8E4DC] rounded-lg text-[10px] text-[#121E1A] font-mono max-h-52 overflow-auto whitespace-pre-wrap break-words">
          {formatPrettyJson(item.rawEvents)}
        </pre>
      )}
    </div>
  );
}

function StepGroupCard({
  group,
  isFocused,
  onRegisterRef,
}: {
  group: TraceStepGroup;
  isFocused: boolean;
  onRegisterRef: (uid: string, el: HTMLDivElement | null) => void;
}) {
  const hasDetails = group.items.length > 0;
  const [expanded, setExpanded] = useState<boolean>(
    group.status === "error" || group.status === "warning" || group.status === "running" || hasDetails,
  );

  return (
    <div
      ref={(el) => onRegisterRef(group.uid, el)}
      className={`rounded-xl border transition ${
        isFocused
          ? "border-[#0F5F4A] ring-2 ring-[#0F5F4A]/20 bg-white"
          : group.status === "error"
          ? "border-red-200 bg-red-50/30"
          : group.status === "warning"
          ? "border-amber-200 bg-amber-50/30"
          : "border-[#D8E4DF] bg-[#FAF8F4]/80"
      }`}
    >
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((prev) => !prev)}
        className={`w-full px-2.5 py-2 flex items-start gap-2 text-left ${
          hasDetails ? "cursor-pointer hover:bg-[#F5F2EB]/60 rounded-xl" : "cursor-default"
        }`}
      >
        <span
          className={`w-5 h-5 rounded-full text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5 ${
            group.status === "error"
              ? "bg-red-100 text-[#DC2626]"
              : group.status === "warning"
              ? "bg-amber-100 text-[#D97706]"
              : group.status === "running"
              ? "bg-[#0F5F4A] text-white animate-pulse"
              : "bg-[#E6F4EE] text-[#0F5F4A]"
          }`}
        >
          {group.stepNumber}
        </span>

        <div className="flex-1 min-w-0 space-y-0.5">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
              <span className="material-symbols-outlined text-[13px] text-[#0F5F4A] shrink-0">
                {group.icon}
              </span>
              <span className="font-bold text-[#121E1A] text-[11.5px] leading-snug">
                {group.label}
              </span>
              <code className="text-[9.5px] px-1 py-0.2 bg-white border border-[#E8E4DC] text-[#4A5550] rounded font-mono">
                {group.node}
              </code>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              {group.durationMs > 0 && (
                <span className="text-[10px] font-mono text-[#6F7974] whitespace-nowrap">
                  {formatDuration(group.durationMs)}
                </span>
              )}
              <StatusBadge status={group.status} />
              {hasDetails && (
                <span className="material-symbols-outlined text-[15px] text-[#6F7974]">
                  {expanded ? "expand_less" : "expand_more"}
                </span>
              )}
            </div>
          </div>

          <p className="text-[11px] text-[#4A5550] leading-snug break-words">{group.autoSummary}</p>
        </div>
      </button>

      {hasDetails && expanded && (
        <div className="px-2.5 pb-2.5 pt-1 space-y-1.5 border-t border-[#E8E4DC]/70">
          {group.items.map((item) => {
            if (item.kind === "model_call") {
              return <InlineModelCallCard key={item.uid} item={item} />;
            }
            if (item.kind === "tool_call") {
              return <InlineToolCallCard key={item.uid} item={item} />;
            }
            if (item.kind === "verifier_decision") {
              return <InlineVerifierCard key={item.uid} item={item} />;
            }
            if (item.kind === "adaptive_radius") {
              return (
                <div
                  key={item.uid}
                  className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[10.5px] text-[#92400E] flex items-start gap-1.5"
                >
                  <span className="material-symbols-outlined text-[14px] text-[#D97706] shrink-0 mt-0.5">
                    radar
                  </span>
                  <div>
                    <span className="font-bold">
                      Mở rộng bán kính: {item.fromRadius ?? "?"} km → {item.toRadius ?? "?"} km
                    </span>
                    {item.reason && <p className="text-[10px] mt-0.5">{item.reason}</p>}
                  </div>
                </div>
              );
            }
            if (item.kind === "location_retry") {
              const isResolved = item.finalKind === "resolved";
              const stageLabels: Record<string, string> = {
                primary: "Lần đầu",
                retry_1_variant: "Biến thể",
                retry_1_llm_rewrite: "LLM viết lại",
                retry_2_llm_rewrite: "LLM viết lại (2)",
              };
              return (
                <div
                  key={item.uid}
                  className={
                    isResolved
                      ? "rounded-lg border border-sky-200 bg-sky-50/80 p-2 text-[10.5px] text-[#075985]"
                      : "rounded-lg border border-amber-200 bg-amber-50 p-2 text-[10.5px] text-[#92400E]"
                  }
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="material-symbols-outlined text-[14px] shrink-0">
                        {isResolved ? "edit_location_alt" : "location_off"}
                      </span>
                      <span>Retry định vị ({item.attempts.length} bước)</span>
                    </div>
                    {item.finalKind && (
                      <span
                        className={
                          isResolved
                            ? "rounded px-1.5 py-0.5 text-[9.5px] font-semibold bg-emerald-100 text-emerald-800"
                            : "rounded px-1.5 py-0.5 text-[9.5px] font-semibold bg-amber-100 text-amber-800"
                        }
                      >
                        {item.finalKind}
                      </span>
                    )}
                  </div>
                  {item.attempts.length > 0 && (
                    <div className="mt-1.5 space-y-1 border-t border-black/10 pt-1.5">
                      {item.attempts.map((att, idx) => (
                        <div
                          key={`${item.uid}-att-${idx}`}
                          className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[10px]"
                        >
                          <span className="font-semibold opacity-80">
                            {idx + 1}. {stageLabels[att.stage || ""] || att.stage || "attempt"}:
                          </span>
                          <span className="font-mono bg-white/70 px-1 rounded">
                            {att.query || "—"}
                          </span>
                          {att.region_hint && (
                            <span className="opacity-75">({att.region_hint})</span>
                          )}
                          <span className="opacity-60">→</span>
                          <span
                            className={
                              att.result_kind === "resolved"
                                ? "font-semibold text-emerald-700"
                                : "font-medium opacity-85"
                            }
                          >
                            {att.result_kind || "?"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            }
            if (item.kind === "suspicious_listing") {
              return (
                <div
                  key={item.uid}
                  className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-[10.5px] text-[#92400E] flex items-start gap-1.5"
                >
                  <span className="material-symbols-outlined text-[14px] text-[#D97706] shrink-0 mt-0.5">
                    security
                  </span>
                  <div>
                    <span className="font-bold">Loại tin nghi vấn: {item.listingId}</span>
                    {item.rules.length > 0 && (
                      <p className="text-[10px] font-mono mt-0.5">Rules: {item.rules.join(", ")}</p>
                    )}
                  </div>
                </div>
              );
            }
            return (
              <details key={item.uid} className="rounded-lg border border-[#E8E4DC] bg-white p-2 text-[10px]">
                <summary className="cursor-pointer font-semibold text-[#4A5550]">
                  Sự kiện: {item.eventType}
                </summary>
                <pre className="mt-1 font-mono whitespace-pre-wrap break-words">
                  {formatPrettyJson(item.rawEvents)}
                </pre>
              </details>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TraceInspectorModal({
  isOpen,
  onClose,
  groups,
  traceEvents,
  initialSelectedUid,
}: {
  isOpen: boolean;
  onClose: () => void;
  groups: TraceStepGroup[];
  traceEvents: AgentTraceEvent[];
  initialSelectedUid?: string | null;
}) {
  const [filter, setFilter] = useState<InspectorFilter>("all");
  const [selectedUid, setSelectedUid] = useState<string | null>(initialSelectedUid ?? null);
  const [copied, setCopied] = useState(false);

  const summary = useMemo(() => summarizeTrace(traceEvents, groups), [traceEvents, groups]);

  const selectableItems = useMemo(() => {
    const out: Array<{ group: TraceStepGroup; item?: TraceTimelineItem; uid: string }> = [];
    for (const g of groups) {
      if (g.items.length === 0) {
        if (filter === "all") {
          out.push({ group: g, uid: g.uid });
        }
        continue;
      }
      for (const it of g.items) {
        if (filter === "model" && it.kind !== "model_call") continue;
        if (filter === "tool" && it.kind !== "tool_call") continue;
        if (
          filter === "verifier" &&
          it.kind !== "verifier_decision" &&
          it.kind !== "adaptive_radius" &&
          it.kind !== "suspicious_listing"
        ) {
          continue;
        }
        out.push({ group: g, item: it, uid: it.uid });
      }
    }
    return out;
  }, [groups, filter]);

  const activeEntry =
    selectableItems.find((e) => e.uid === selectedUid) || selectableItems[0] || null;

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  if (!isOpen || typeof document === "undefined") return null;

  const handleCopyJsonl = async () => {
    try {
      await navigator.clipboard.writeText(traceEventsToJsonl(traceEvents));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // ignore clipboard errors
    }
  };

  const handleDownloadJsonl = () => {
    const blob = new Blob([traceEventsToJsonl(traceEvents)], { type: "application/x-ndjson;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${summary.runId || "homigo-trace"}.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 bg-[#121E1A]/50 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Chi tiết Trace LangGraph"
    >
      <div
        className="bg-white border border-[#D8E4DF] rounded-2xl shadow-2xl w-full max-w-5xl h-[86vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-4 py-3 border-b border-[#E8E4DC] bg-[#FAF8F4] flex items-center justify-between gap-3 flex-wrap shrink-0">
          <div className="space-y-0.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="material-symbols-outlined text-[18px] text-[#0F5F4A]">route</span>
              <h3 className="text-sm font-bold text-[#121E1A]">
                Thanh tra Trace LangGraph từng bước
              </h3>
              {summary.verifierPassed !== null && (
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    summary.verifierPassed
                      ? "bg-[#E6F4EE] text-[#0F5F4A]"
                      : "bg-red-50 text-[#DC2626] border border-red-200"
                  }`}
                >
                  {summary.verifierPassed ? "DoD PASS" : "DoD FAIL"}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap text-[11px] text-[#4A5550]">
              <span>{summary.stepCount} bước</span>
              <span>·</span>
              <span>{summary.modelCallCount} LLM calls</span>
              <span>·</span>
              <span>{summary.toolCallCount} Tool calls</span>
              {(summary.wallClockMs ?? summary.totalDurationMs) > 0 && (
                <>
                  <span>·</span>
                  <span className="font-mono font-semibold text-[#0F5F4A]">
                    {formatDuration(summary.wallClockMs ?? summary.totalDurationMs)}
                  </span>
                </>
              )}
              {(summary.totalTokensIn > 0 || summary.totalTokensOut > 0) && (
                <>
                  <span>·</span>
                  <span className="font-mono">
                    {summary.tokensEstimated ? "~" : ""}
                    {formatNumber(summary.totalTokensIn)} in / {formatNumber(summary.totalTokensOut)} out tok
                  </span>
                </>
              )}
              {summary.runId && (
                <>
                  <span>·</span>
                  <code className="text-[10px] font-mono text-[#6F7974]">{summary.runId}</code>
                </>
              )}
              {summary.versions?.model && (
                <code className="px-1.5 py-0.5 rounded bg-white border border-[#E8E4DC] text-[10px] font-mono">
                  {summary.versions.model}
                </code>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={handleCopyJsonl}
              className="px-2.5 py-1.5 rounded-xl border border-[#D8E4DF] bg-white hover:bg-[#F5F2EB] text-[#121E1A] text-xs font-semibold inline-flex items-center gap-1 transition cursor-pointer"
            >
              <span className="material-symbols-outlined text-[14px]">
                {copied ? "check" : "content_copy"}
              </span>
              <span>{copied ? "Đã copy" : "Copy JSONL"}</span>
            </button>
            <button
              type="button"
              onClick={handleDownloadJsonl}
              className="px-2.5 py-1.5 rounded-xl border border-[#D8E4DF] bg-white hover:bg-[#F5F2EB] text-[#121E1A] text-xs font-semibold inline-flex items-center gap-1 transition cursor-pointer"
            >
              <span className="material-symbols-outlined text-[14px]">download</span>
              <span>Tải .jsonl</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 rounded-xl border border-[#D8E4DF] bg-white hover:bg-[#F5F2EB] flex items-center justify-center text-[#4A5550] cursor-pointer"
              aria-label="Đóng"
            >
              <span className="material-symbols-outlined text-[18px]">close</span>
            </button>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="px-4 py-2 border-b border-[#E8E4DC] bg-white flex items-center gap-1.5 flex-wrap shrink-0">
          {(
            [
              { id: "all", label: "Tất cả" },
              { id: "model", label: `LLM Calls (${summary.modelCallCount})` },
              { id: "tool", label: `Tools (${summary.toolCallCount})` },
              { id: "verifier", label: "Verifier & Cảnh báo" },
            ] as const
          ).map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1 rounded-full text-xs font-semibold border transition cursor-pointer ${
                filter === f.id
                  ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                  : "bg-[#FAF8F4] text-[#4A5550] border-[#D8E4DF] hover:bg-[#F5F2EB]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Body: 2-Column Master/Detail */}
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-12">
          {/* Left: Timeline */}
          <div className="md:col-span-5 border-b md:border-b-0 md:border-r border-[#E8E4DC] overflow-y-auto p-3 space-y-1.5 bg-[#FAF8F4]/50 max-h-60 md:max-h-none">
            {selectableItems.length === 0 ? (
              <p className="text-xs text-[#6F7974] italic p-3">Không có sự kiện nào khớp bộ lọc.</p>
            ) : (
              selectableItems.map(({ group, item, uid }) => {
                const isSelected = activeEntry?.uid === uid;
                const itemIdx = item ? group.items.findIndex((x) => x.uid === item.uid) : -1;
                const stepPrefix =
                  group.items.length > 1 && itemIdx >= 0
                    ? `Bước ${group.stepNumber}.${itemIdx + 1}`
                    : `Bước ${group.stepNumber}`;
                let title = group.label;
                let subtitle = group.autoSummary;
                let badgeText = group.node;
                let status: "running" | "ok" | "warning" | "error" = group.status;
                let duration: number | undefined = group.durationMs || undefined;

                if (item?.kind === "model_call") {
                  title = `${stepPrefix}: LLM #${item.callIndex}`;
                  subtitle = summarizeModelOutput(item);
                  badgeText = group.node;
                  status = item.status;
                  duration = item.durationMs;
                } else if (item?.kind === "tool_call") {
                  title = `${stepPrefix}: ${item.toolName}`;
                  subtitle = summarizeToolResult(item);
                  badgeText = group.node;
                  status = item.status;
                  duration = item.durationMs;
                } else if (item?.kind === "verifier_decision") {
                  title = `${stepPrefix}: DoD Verifier (${item.passed ? "PASS" : "FAIL"})`;
                  subtitle = item.dodSummary;
                  badgeText = `next: ${item.nextDecision}`;
                  status = item.passed ? "ok" : "error";
                } else if (item?.kind === "adaptive_radius") {
                  title = `${stepPrefix}: Mở rộng bán kính`;
                  subtitle = `${item.fromRadius ?? "?"}km → ${item.toRadius ?? "?"}km`;
                  badgeText = group.node;
                  status = "warning";
                } else if (item?.kind === "suspicious_listing") {
                  title = `${stepPrefix}: Tin nghi vấn`;
                  subtitle = item.listingId || "";
                  badgeText = group.node;
                  status = "warning";
                } else {
                  title = `${stepPrefix}: ${group.label}`;
                }

                return (
                  <button
                    key={uid}
                    type="button"
                    onClick={() => setSelectedUid(uid)}
                    className={`w-full text-left p-2.5 rounded-xl border transition cursor-pointer space-y-1 ${
                      isSelected
                        ? "bg-white border-[#0F5F4A] ring-2 ring-[#0F5F4A]/15 shadow-xs"
                        : "bg-white border-[#E8E4DC] hover:border-[#0F5F4A]/40"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-xs text-[#121E1A] truncate">{title}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {duration !== undefined && duration > 0 && (
                          <span className="text-[10px] font-mono text-[#6F7974]">
                            {formatDuration(duration)}
                          </span>
                        )}
                        <StatusBadge status={status} />
                      </div>
                    </div>
                    <p className="text-[11px] text-[#4A5550] line-clamp-2">{subtitle}</p>
                    <div className="flex items-center justify-between text-[10px] text-[#6F7974] font-mono">
                      <span>{badgeText}</span>
                      {item?.seq !== undefined && <span>seq #{item.seq}</span>}
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Right: Inspector Detail */}
          <div className="md:col-span-7 overflow-y-auto p-4 space-y-4 bg-white">
            {!activeEntry ? (
              <p className="text-xs text-[#6F7974]">Chọn một bước bên trái để xem chi tiết.</p>
            ) : activeEntry.item?.kind === "model_call" ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2 flex-wrap pb-2 border-b border-[#E8E4DC]">
                  <div>
                    <h4 className="text-sm font-bold text-[#121E1A]">
                      LLM Call #{activeEntry.item.callIndex} · {activeEntry.group.label}
                    </h4>
                    <p className="text-xs text-[#6F7974] font-mono">
                      node: {activeEntry.group.node}
                      {activeEntry.item.seq ? ` · seq #${activeEntry.item.seq}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span className="px-2 py-0.5 rounded bg-[#F5F2EB] text-[#121E1A]">
                      {activeEntry.item.tokensEstimated ? "~" : ""}
                      {formatNumber(activeEntry.item.tokensIn)} in /{" "}
                      {formatNumber(activeEntry.item.tokensOut)} out
                    </span>
                    {activeEntry.item.durationMs !== undefined && (
                      <span className="font-bold text-[#0F5F4A]">
                        {formatDuration(activeEntry.item.durationMs)}
                      </span>
                    )}
                  </div>
                </div>

                {activeEntry.item.error && (
                  <div className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-xs text-[#DC2626]">
                    {activeEntry.item.error}
                  </div>
                )}

                {activeEntry.item.input !== undefined && (
                  <div className="space-y-1.5">
                    <h5 className="text-xs font-bold text-[#0F5F4A] uppercase tracking-wide">
                      Input ({activeEntry.item.messageCount ?? "?"} messages)
                    </h5>
                    <RenderInputMessages input={activeEntry.item.input} />
                  </div>
                )}

                {activeEntry.item.output !== undefined && (
                  <div className="space-y-1.5">
                    <h5 className="text-xs font-bold text-[#0F5F4A] uppercase tracking-wide">
                      Output
                    </h5>
                    <pre className="p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[11px] font-mono whitespace-pre-wrap break-words max-h-80 overflow-auto">
                      {formatPrettyJson(activeEntry.item.output)}
                    </pre>
                  </div>
                )}

                <details className="pt-1">
                  <summary className="text-xs font-semibold text-[#4A5550] cursor-pointer hover:text-[#0F5F4A]">
                    Raw Span JSON
                  </summary>
                  <pre className="mt-2 p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[10.5px] font-mono whitespace-pre-wrap break-words max-h-72 overflow-auto">
                    {formatPrettyJson(activeEntry.item.rawEvents)}
                  </pre>
                </details>
              </div>
            ) : activeEntry.item?.kind === "tool_call" ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2 flex-wrap pb-2 border-b border-[#E8E4DC]">
                  <div>
                    <h4 className="text-sm font-bold text-[#121E1A] font-mono">
                      {activeEntry.item.toolName}
                    </h4>
                    <p className="text-xs text-[#6F7974] font-mono">
                      node: {activeEntry.group.node}
                      {activeEntry.item.toolCallId ? ` · ${activeEntry.item.toolCallId}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={activeEntry.item.status} />
                    {activeEntry.item.durationMs !== undefined && (
                      <span className="text-xs font-mono font-bold text-[#0F5F4A]">
                        {formatDuration(activeEntry.item.durationMs)}
                      </span>
                    )}
                  </div>
                </div>

                {activeEntry.item.error && (
                  <div className="p-2.5 rounded-xl bg-red-50 border border-red-200 text-xs text-[#DC2626]">
                    {activeEntry.item.error}
                  </div>
                )}

                {activeEntry.item.stateDiff.length > 0 && (
                  <div className="p-2.5 rounded-xl bg-[#E6F4EE]/60 border border-[#0F5F4A]/20 space-y-1">
                    <h5 className="text-xs font-bold text-[#0F5F4A]">Thay đổi State</h5>
                    <div className="space-y-0.5 text-xs font-mono">
                      {activeEntry.item.stateDiff.map((d) => (
                        <div key={d.key}>
                          <span className="text-[#4A5550]">{d.key}:</span>{" "}
                          <span>{formatScalarValue(d.before)}</span> →{" "}
                          <strong className="text-[#0F5F4A]">{formatScalarValue(d.after)}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="space-y-1.5">
                  <h5 className="text-xs font-bold text-[#0F5F4A] uppercase tracking-wide">
                    Arguments
                  </h5>
                  <pre className="p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[11px] font-mono whitespace-pre-wrap break-words max-h-60 overflow-auto">
                    {formatPrettyJson(activeEntry.item.args)}
                  </pre>
                </div>

                {activeEntry.item.result !== undefined && (
                  <div className="space-y-1.5">
                    <h5 className="text-xs font-bold text-[#0F5F4A] uppercase tracking-wide">
                      Result
                    </h5>
                    <pre className="p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[11px] font-mono whitespace-pre-wrap break-words max-h-80 overflow-auto">
                      {formatPrettyJson(activeEntry.item.result)}
                    </pre>
                  </div>
                )}

                <details>
                  <summary className="text-xs font-semibold text-[#4A5550] cursor-pointer hover:text-[#0F5F4A]">
                    Raw Span JSON
                  </summary>
                  <pre className="mt-2 p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[10.5px] font-mono whitespace-pre-wrap break-words max-h-72 overflow-auto">
                    {formatPrettyJson(activeEntry.item.rawEvents)}
                  </pre>
                </details>
              </div>
            ) : activeEntry.item?.kind === "verifier_decision" ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-2 pb-2 border-b border-[#E8E4DC]">
                  <div>
                    <h4 className="text-sm font-bold text-[#121E1A]">
                      DoD Verifier · {activeEntry.item.passed ? "Đạt chuẩn" : "Không đạt"}
                    </h4>
                    <p className="text-xs text-[#4A5550]">{activeEntry.item.dodSummary}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-[#F5F2EB] text-xs font-mono font-semibold">
                    next: {activeEntry.item.nextDecision}
                  </span>
                </div>

                {activeEntry.item.failures.length > 0 && (
                  <div className="space-y-1.5">
                    <h5 className="text-xs font-bold text-[#DC2626] uppercase">Danh sách lỗi</h5>
                    {activeEntry.item.failures.map((f, idx) => (
                      <FailureDetailRow key={idx} failure={f} />
                    ))}
                  </div>
                )}

                <div className="space-y-1.5">
                  <h5 className="text-xs font-bold text-[#0F5F4A] uppercase">Verifier Payload</h5>
                  <pre className="p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[11px] font-mono whitespace-pre-wrap break-words max-h-80 overflow-auto">
                    {formatPrettyJson(activeEntry.item.rawEvents)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <h4 className="text-sm font-bold text-[#121E1A]">{activeEntry.group.label}</h4>
                <p className="text-xs text-[#4A5550]">{activeEntry.group.autoSummary}</p>
                <pre className="p-2.5 bg-[#FAF8F4] border border-[#E8E4DC] rounded-xl text-[11px] font-mono whitespace-pre-wrap break-words">
                  {formatPrettyJson(activeEntry.item ? activeEntry.item.rawEvents : activeEntry.group.rawNodeStep)}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function AgentTracePanel({
  traceEvents,
  isStreaming = false,
  statusText,
}: AgentTracePanelProps) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [focusedGroupUid, setFocusedGroupUid] = useState<string | null>(null);
  const stepRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const groups = useMemo(() => buildTraceStepGroups(traceEvents), [traceEvents]);
  const summary = useMemo(() => summarizeTrace(traceEvents, groups), [traceEvents, groups]);

  const hasTrace = traceEvents.length > 0 || isStreaming;
  if (!hasTrace) return null;

  // Mặc định mở khi đang stream (hoặc khi có lỗi/cảnh báo DoD fail), thu gọn khi hoàn tất bình thường
  const isExpanded =
    manualToggle !== null ? manualToggle : isStreaming || summary.hasError;

  const registerStepRef = (uid: string, el: HTMLDivElement | null) => {
    if (el) {
      stepRefs.current.set(uid, el);
    } else {
      stepRefs.current.delete(uid);
    }
  };

  const handleStepPillClick = (uid: string) => {
    setManualToggle(true);
    setFocusedGroupUid(uid);
    setTimeout(() => {
      stepRefs.current.get(uid)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, 30);
  };

  const totalTimeMs = summary.wallClockMs ?? summary.totalDurationMs;

  return (
    <>
      <div className="rounded-xl border border-[#D8E4DF] bg-[#FAF8F4] overflow-hidden text-[11px]">
        {/* Header */}
        <div className="px-2.5 py-2 flex items-center justify-between gap-2 bg-[#F5F2EB]/70">
          <button
            type="button"
            onClick={() => setManualToggle(!isExpanded)}
            className="flex-1 min-w-0 flex items-center gap-2 text-left cursor-pointer"
          >
            {isStreaming ? (
              <span className="w-2 h-2 rounded-full bg-[#0F5F4A] animate-ping shrink-0" />
            ) : summary.hasError ? (
              <span className="material-symbols-outlined text-[15px] text-[#DC2626] shrink-0">
                error
              </span>
            ) : summary.hasWarning ? (
              <span className="material-symbols-outlined text-[15px] text-[#D97706] shrink-0">
                warning
              </span>
            ) : (
              <span className="material-symbols-outlined text-[15px] text-[#0F5F4A] shrink-0">
                route
              </span>
            )}

            <div className="min-w-0 flex-1">
              <div className="font-bold text-[#121E1A] text-[11.5px] leading-snug truncate">
                {isStreaming
                  ? statusText || "Đang xử lý từng bước..."
                  : `Luồng AI (${summary.stepCount} bước)`}
              </div>
              {!isStreaming && (
                <div className="flex items-center gap-1.5 flex-wrap text-[10px] text-[#4A5550] mt-0.5">
                  <span>
                    {summary.modelCallCount} LLM · {summary.toolCallCount} Tool
                  </span>
                  {totalTimeMs > 0 && (
                    <span className="font-mono font-semibold text-[#0F5F4A]">
                      · {formatDuration(totalTimeMs)}
                    </span>
                  )}
                  {(summary.totalTokensIn > 0 || summary.totalTokensOut > 0) && (
                    <span className="font-mono">
                      · {summary.tokensEstimated ? "~" : ""}
                      {formatNumber(summary.totalTokensIn)}/{formatNumber(summary.totalTokensOut)} tok
                    </span>
                  )}
                  {summary.verifierPassed !== null && (
                    <span
                      className={`px-1.5 py-0.2 rounded font-semibold ${
                        summary.verifierPassed
                          ? "bg-[#E6F4EE] text-[#0F5F4A]"
                          : "bg-red-50 text-[#DC2626] border border-red-200"
                      }`}
                    >
                      {summary.verifierPassed ? "DoD Pass" : "DoD Fail"}
                    </span>
                  )}
                </div>
              )}
            </div>
          </button>

          <div className="flex items-center gap-0.5 shrink-0">
            {traceEvents.length > 0 && (
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                title="Xem chi tiết Trace từng bước"
                aria-label="Xem chi tiết Trace từng bước"
                className="w-6 h-6 rounded-md hover:bg-[#E6F4EE]/80 text-[#6F7974] hover:text-[#0F5F4A] flex items-center justify-center transition cursor-pointer"
              >
                <span className="material-symbols-outlined text-[16px]">visibility</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setManualToggle(!isExpanded)}
              className="w-6 h-6 rounded-lg hover:bg-white/80 flex items-center justify-center text-[#4A5550] cursor-pointer"
              aria-label={isExpanded ? "Thu gọn trace" : "Mở rộng trace"}
            >
              <span className="material-symbols-outlined text-[16px]">
                {isExpanded ? "expand_less" : "expand_more"}
              </span>
            </button>
          </div>
        </div>

        {/* Expanded Timeline Body */}
        {isExpanded && (
          <div className="px-2.5 pb-2.5 pt-2 border-t border-[#E8E4DC] space-y-2">
            {groups.length === 0 ? (
              <p className="text-[11px] text-[#6F7974] italic px-1">
                Đang khởi tạo kết nối tới mô hình AI...
              </p>
            ) : (
              <>
                {/* Pipeline Stepper Pills */}
                <div className="flex items-center gap-1 flex-wrap pb-1">
                  {groups.map((g, idx) => (
                    <div key={g.uid} className="inline-flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleStepPillClick(g.uid)}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border transition cursor-pointer ${
                          focusedGroupUid === g.uid
                            ? "bg-[#0F5F4A] text-white border-[#0F5F4A]"
                            : g.status === "error"
                            ? "bg-red-50 text-[#DC2626] border-red-200 hover:bg-red-100"
                            : g.status === "warning"
                            ? "bg-amber-50 text-[#D97706] border-amber-200 hover:bg-amber-100"
                            : "bg-white text-[#121E1A] border-[#D8E4DF] hover:bg-[#E6F4EE]"
                        }`}
                      >
                        <span>{g.stepNumber}.</span>
                        <span>{g.shortLabel}</span>
                      </button>
                      {idx < groups.length - 1 && (
                        <span className="text-[#6F7974] text-[10px]">→</span>
                      )}
                    </div>
                  ))}
                </div>

                {/* Step Cards */}
                <div className="space-y-1.5 max-h-96 overflow-y-auto pr-0.5">
                  {groups.map((group) => (
                    <StepGroupCard
                      key={group.uid}
                      group={group}
                      isFocused={focusedGroupUid === group.uid}
                      onRegisterRef={registerStepRef}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {modalOpen && (
        <TraceInspectorModal
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          groups={groups}
          traceEvents={traceEvents}
        />
      )}
    </>
  );
}
