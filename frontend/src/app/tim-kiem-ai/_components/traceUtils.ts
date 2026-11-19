import type {
  AgentTraceEvent,
  AgentTraceVersions,
  LocationRetryAttempt,
  VerifierFailureItem,
} from "@/types/dto/agent";

export interface NodeMeta {
  label: string;
  shortLabel: string;
  icon: string;
}

const NODE_META_MAP: Record<string, NodeMeta> = {
  guardrail_node: {
    label: "Kiểm tra an toàn (Guardrails)",
    shortLabel: "Guardrails",
    icon: "shield",
  },
  understand_node: {
    label: "Phân tích yêu cầu & Intent",
    shortLabel: "Phân tích",
    icon: "psychology",
  },
  clarification_node: {
    label: "Yêu cầu làm rõ tiêu chí",
    shortLabel: "Hỏi làm rõ",
    icon: "help",
  },
  advisory_node: {
    label: "Tư vấn kỹ năng & thị trường",
    shortLabel: "Tư vấn",
    icon: "menu_book",
  },
  retrieval_node: {
    label: "Tìm kiếm & Lọc phòng",
    shortLabel: "Tìm phòng",
    icon: "search",
  },
  decision_node: {
    label: "Đánh giá & Chọn Top phòng",
    shortLabel: "Xếp hạng",
    icon: "balance",
  },
  verify_node: {
    label: "Kiểm chứng DoD & Self-RAG",
    shortLabel: "Kiểm chứng",
    icon: "verified_user",
  },
  formatter_node: {
    label: "Đóng gói phản hồi",
    shortLabel: "Đóng gói",
    icon: "auto_awesome",
  },
};

export function getNodeMeta(nodeName?: string): NodeMeta {
  if (!nodeName) {
    return { label: "Xử lý Agent", shortLabel: "Agent", icon: "memory" };
  }
  return (
    NODE_META_MAP[nodeName] || {
      label: nodeName,
      shortLabel: nodeName.replace(/_node$/, ""),
      icon: "memory",
    }
  );
}

export interface StateDiffEntry {
  key: string;
  before: unknown;
  after: unknown;
}

export interface ModelCallTraceItem {
  kind: "model_call";
  uid: string;
  node: string;
  callIndex: number;
  status: "running" | "ok" | "error";
  durationMs?: number;
  messageCount?: number;
  toolCount?: number;
  tokensIn: number;
  tokensOut: number;
  cachedTokens: number;
  reasoningTokens: number;
  tokensEstimated: boolean;
  requestedTools: string[];
  input?: unknown;
  output?: unknown;
  error?: string | null;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface ToolCallTraceItem {
  kind: "tool_call";
  uid: string;
  node: string;
  toolName: string;
  toolCallId?: string;
  status: "running" | "ok" | "error";
  durationMs?: number;
  args: Record<string, unknown>;
  result?: unknown;
  resultSummary?: unknown;
  stateBefore?: unknown;
  stateAfter?: unknown;
  stateDiff: StateDiffEntry[];
  error?: string | null;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface VerifierTraceItem {
  kind: "verifier_decision";
  uid: string;
  node: string;
  passed: boolean;
  dodSummary: string;
  nextDecision: string;
  failedTier?: string | null;
  answerRetry: number;
  failures: Array<VerifierFailureItem | string>;
  verifierOutput?: Record<string, unknown>;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface AdaptiveRadiusTraceItem {
  kind: "adaptive_radius";
  uid: string;
  node: string;
  fromRadius?: number | null;
  toRadius?: number;
  validRoomsBefore?: number;
  reason?: string;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface SuspiciousListingTraceItem {
  kind: "suspicious_listing";
  uid: string;
  node: string;
  listingId?: string;
  rules: string[];
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface LocationRetryTraceItem {
  kind: "location_retry";
  uid: string;
  node: string;
  attempts: LocationRetryAttempt[];
  finalKind?: string;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export interface GenericTraceItem {
  kind: "generic";
  uid: string;
  node: string;
  eventType: string;
  seq?: number;
  ts?: number;
  rawEvents: AgentTraceEvent[];
}

export type TraceTimelineItem =
  | ModelCallTraceItem
  | ToolCallTraceItem
  | VerifierTraceItem
  | AdaptiveRadiusTraceItem
  | SuspiciousListingTraceItem
  | LocationRetryTraceItem
  | GenericTraceItem;

export interface TraceStepGroup {
  stepNumber: number;
  uid: string;
  node: string;
  label: string;
  shortLabel: string;
  icon: string;
  status: "running" | "ok" | "warning" | "error";
  details?: string;
  autoSummary: string;
  durationMs: number;
  items: TraceTimelineItem[];
  rawNodeStep?: AgentTraceEvent;
}

export interface TraceSummary {
  stepCount: number;
  modelCallCount: number;
  toolCallCount: number;
  totalDurationMs: number;
  wallClockMs: number | null;
  totalTokensIn: number;
  totalTokensOut: number;
  totalCachedTokens: number;
  tokensEstimated: boolean;
  verifierPassed: boolean | null;
  verifierDecision: string | null;
  dodSummary: string | null;
  hasWarning: boolean;
  hasError: boolean;
  runId: string | null;
  sessionId: string | null;
  versions: AgentTraceVersions | null;
}

export function formatNumber(n: number): string {
  return n.toLocaleString("vi-VN");
}

export function formatDuration(ms?: number | null): string {
  if (ms === undefined || ms === null || Number.isNaN(ms)) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2).replace(/\.00$/, "")}s`;
}

export function formatCompactPrice(val: unknown): string | null {
  if (typeof val !== "number" || Number.isNaN(val) || val <= 0) return null;
  if (val >= 1_000_000) {
    const tr = (val / 1_000_000).toFixed(1).replace(/\.0$/, "");
    return `${tr}tr`;
  }
  return `${Math.round(val / 1000)}k`;
}

export function formatScalarValue(val: unknown): string {
  if (val === null || val === undefined) return "null";
  if (typeof val === "boolean") return val ? "true" : "false";
  if (typeof val === "number") return String(val);
  if (typeof val === "string") return val;
  if (Array.isArray(val)) return val.map((x) => formatScalarValue(x)).join(", ");
  try {
    return JSON.stringify(val);
  } catch {
    return String(val);
  }
}

export function computeStateDiff(before: unknown, after: unknown): StateDiffEntry[] {
  if (!before || !after || typeof before !== "object" || typeof after !== "object") {
    return [];
  }
  const b = before as Record<string, unknown>;
  const a = after as Record<string, unknown>;
  const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)]));
  const diffs: StateDiffEntry[] = [];
  for (const key of keys) {
    const bVal = b[key];
    const aVal = a[key];
    if (JSON.stringify(bVal) !== JSON.stringify(aVal)) {
      diffs.push({ key, before: bVal, after: aVal });
    }
  }
  return diffs;
}

export function summarizeToolArgs(toolName: string, args: Record<string, unknown>): Array<{ label: string; value: string }> {
  if (!args || typeof args !== "object") return [];
  const pills: Array<{ label: string; value: string }> = [];

  if (args.query && typeof args.query === "string") {
    pills.push({ label: "query", value: args.query });
  }
  if (args.kind && typeof args.kind === "string") {
    pills.push({ label: "loại", value: args.kind });
  }
  if (args.region_hint && typeof args.region_hint === "string") {
    pills.push({ label: "vùng", value: args.region_hint });
  }
  if (typeof args.lat === "number" && typeof args.lng === "number") {
    pills.push({ label: "tọa độ", value: `${args.lat.toFixed(4)}, ${args.lng.toFixed(4)}` });
  }

  const minP = formatCompactPrice(args.min_price);
  const maxP = formatCompactPrice(args.max_price);
  if (minP && maxP) {
    pills.push({ label: "giá", value: `${minP}–${maxP}` });
  } else if (maxP) {
    pills.push({ label: "giá ≤", value: maxP });
  } else if (minP) {
    pills.push({ label: "giá ≥", value: minP });
  }

  if (typeof args.max_distance_km === "number") {
    pills.push({ label: "bán kính", value: `${args.max_distance_km} km` });
  }
  if (args.room_type) {
    pills.push({ label: "loại phòng", value: formatScalarValue(args.room_type) });
  }
  if (Array.isArray(args.excluded_room_types) && args.excluded_room_types.length > 0) {
    pills.push({ label: "loại trừ", value: args.excluded_room_types.join(", ") });
  }
  if (Array.isArray(args.amenities) && args.amenities.length > 0) {
    pills.push({ label: "tiện ích", value: args.amenities.join(", ") });
  }
  if (args.listing_id && typeof args.listing_id === "string") {
    pills.push({ label: "phòng", value: args.listing_id });
  }
  if (args.skill_name && typeof args.skill_name === "string") {
    pills.push({ label: "skill", value: args.skill_name });
  }
  if (args.area_name && typeof args.area_name === "string") {
    pills.push({ label: "khu vực", value: args.area_name });
  }

  if (pills.length === 0) {
    for (const [k, v] of Object.entries(args)) {
      if (v === null || v === undefined || v === "" || (Array.isArray(v) && v.length === 0)) continue;
      if (pills.length >= 4) break;
      const strVal = formatScalarValue(v);
      pills.push({ label: k, value: strVal.length > 50 ? `${strVal.slice(0, 47)}...` : strVal });
    }
  }

  return pills;
}

export function summarizeToolResult(item: ToolCallTraceItem): string {
  if (item.status === "running") return "Đang thực thi...";
  if (item.error) return `Lỗi: ${item.error}`;

  const summary = item.resultSummary;
  if (summary && typeof summary === "object") {
    const s = summary as Record<string, unknown>;
    if (typeof s.rooms_found === "number") {
      return `Tìm thấy ${s.rooms_found} phòng`;
    }
    if (s.kind && typeof s.lat === "number" && typeof s.lng === "number") {
      return `${String(s.kind)} (${s.lat.toFixed(4)}, ${s.lng.toFixed(4)})`;
    }
    if (typeof s.candidates === "number" && s.candidates > 0) {
      return `${String(s.kind || "ambiguous")} (${s.candidates} ứng viên)`;
    }
    const parts = Object.entries(s)
      .filter(([, v]) => v !== null && v !== undefined && v !== "")
      .slice(0, 4)
      .map(([k, v]) => `${k}: ${formatScalarValue(v)}`);
    if (parts.length > 0) return parts.join(" · ");
  }

  const res = item.result;
  if (res && typeof res === "object") {
    const r = res as Record<string, unknown>;
    if (Array.isArray(r.rooms)) return `Trả về ${r.rooms.length} phòng`;
    if (r.status) return `status: ${String(r.status)}`;
    if (r.ok === true) return "Thành công";
  }
  if (typeof res === "string" && res.trim()) {
    const line = res.trim().replace(/\s+/g, " ");
    return line.length > 100 ? `${line.slice(0, 97)}...` : line;
  }
  return item.status === "ok" ? "Hoàn tất" : "Lỗi thực thi";
}

export function summarizeModelOutput(item: ModelCallTraceItem): string {
  if (item.status === "running") return "Đang chờ phản hồi từ LLM...";
  if (item.error) return `Lỗi: ${item.error}`;
  if (item.requestedTools.length > 0) {
    return `Yêu cầu gọi ${item.requestedTools.length} tool: ${item.requestedTools.join(", ")}`;
  }

  const out = item.output;
  if (!out) return "Hoàn tất (không có nội dung văn bản)";

  if (typeof out === "object" && !Array.isArray(out)) {
    const obj = out as Record<string, unknown>;
    if (typeof obj.content === "string" && obj.content.trim()) {
      const cleaned = obj.content.trim().replace(/\s+/g, " ");
      return cleaned.length > 140 ? `${cleaned.slice(0, 137)}...` : cleaned;
    }
    const highlights: string[] = [];
    if (obj.intent) highlights.push(`intent=${String(obj.intent)}`);
    if (obj.page_action) highlights.push(`page_action=${String(obj.page_action)}`);
    if (typeof obj.target_page === "number") highlights.push(`trang=${obj.target_page}`);
    if (obj.location_text) highlights.push(`vị trí="${String(obj.location_text)}"`);
    const maxP = formatCompactPrice(obj.max_price);
    if (maxP) highlights.push(`giá ≤ ${maxP}`);
    if (Array.isArray(obj.amenities) && obj.amenities.length > 0) {
      highlights.push(`tiện ích=[${obj.amenities.join(", ")}]`);
    }
    if (typeof obj.is_grounded === "boolean") {
      highlights.push(`grounded=${obj.is_grounded ? "true" : "false"}`);
    }
    if (highlights.length > 0) return highlights.join(" · ");
  }

  if (typeof out === "string") {
    const cleaned = out.trim().replace(/\s+/g, " ");
    return cleaned.length > 140 ? `${cleaned.slice(0, 137)}...` : cleaned;
  }

  const raw = JSON.stringify(out);
  return raw.length > 140 ? `${raw.slice(0, 137)}...` : raw;
}

function buildAutoStepSummary(group: TraceStepGroup): string {
  if (group.details) return group.details;
  const parts: string[] = [];

  for (const item of group.items) {
    if (item.kind === "tool_call") {
      parts.push(`${item.toolName} → ${summarizeToolResult(item)}`);
    } else if (item.kind === "verifier_decision") {
      parts.push(item.dodSummary || (item.passed ? "Đạt DoD" : "Không đạt DoD"));
    } else if (item.kind === "adaptive_radius") {
      parts.push(`Mở rộng ${item.fromRadius ?? "?"}km → ${item.toRadius ?? "?"}km`);
    } else if (item.kind === "suspicious_listing") {
      parts.push(`Loại tin ${item.listingId || ""}`.trim());
    } else if (item.kind === "location_retry") {
      parts.push(`Retry định vị (${item.attempts.length} lần) → ${item.finalKind || "unknown"}`);
    } else if (item.kind === "model_call") {
      parts.push(summarizeModelOutput(item));
    }
  }

  return parts.join(" · ") || "Thực thi hoàn tất.";
}

function deriveGroupStatus(group: TraceStepGroup): "running" | "ok" | "warning" | "error" {
  const nodeStatus = group.rawNodeStep?.status;
  if (group.items.some((it) => (it.kind === "model_call" || it.kind === "tool_call") && it.status === "running")) {
    return "running";
  }
  if (
    nodeStatus === "error" ||
    group.items.some(
      (it) =>
        ((it.kind === "model_call" || it.kind === "tool_call") && it.status === "error") ||
        (it.kind === "verifier_decision" && !it.passed),
    )
  ) {
    return "error";
  }
  if (
    nodeStatus === "warning" ||
    group.items.some(
      (it) =>
        it.kind === "adaptive_radius" ||
        it.kind === "suspicious_listing" ||
        (it.kind === "location_retry" && it.finalKind !== "resolved"),
    )
  ) {
    return "warning";
  }
  return "ok";
}

/**
 * Chuyển danh sách event phẳng thành các Bước (Step Groups) theo trình tự thực thi từng Node,
 * đồng thời ghép cặp (model_request + model_response/error) và (tool_started + tool_finished).
 */
export function buildTraceStepGroups(events: AgentTraceEvent[]): TraceStepGroup[] {
  if (!events || events.length === 0) return [];

  interface RawBucket {
    node: string;
    nodeStep?: AgentTraceEvent;
    events: AgentTraceEvent[];
  }

  const buckets: RawBucket[] = [];

  for (const ev of events) {
    if (ev.type === "node_step") {
      const nodeName = ev.node || "agent";
      buckets.push({
        node: nodeName,
        nodeStep: ev,
        events: [],
      });
      continue;
    }

    const nodeName = ev.node || "agent";
    const lastBucket = buckets[buckets.length - 1];
    if (lastBucket && lastBucket.node === nodeName) {
      lastBucket.events.push(ev);
    } else {
      buckets.push({
        node: nodeName,
        events: [ev],
      });
    }
  }

  let runningModelIdx = 0;

  return buckets.map((bucket, idx) => {
    const meta = getNodeMeta(bucket.node);
    const items: TraceTimelineItem[] = [];
    const pendingModels: ModelCallTraceItem[] = [];
    const pendingToolsById = new Map<string, ToolCallTraceItem>();
    const pendingToolsByName: ToolCallTraceItem[] = [];

    for (let eIdx = 0; eIdx < bucket.events.length; eIdx++) {
      const ev = bucket.events[eIdx];
      const baseUid = ev.id || `step-${idx}-ev-${eIdx}`;

      if (ev.type === "model_request") {
        runningModelIdx += 1;
        const callIdx = ev.model_call_index || runningModelIdx;
        const modelItem: ModelCallTraceItem = {
          kind: "model_call",
          uid: baseUid,
          node: bucket.node,
          callIndex: callIdx,
          status: "running",
          messageCount: ev.message_count,
          toolCount: ev.tool_count,
          tokensIn: 0,
          tokensOut: 0,
          cachedTokens: 0,
          reasoningTokens: 0,
          tokensEstimated: false,
          requestedTools: [],
          input: ev.input,
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        };
        pendingModels.push(modelItem);
        items.push(modelItem);
        continue;
      }

      if (ev.type === "model_response" || ev.type === "model_error") {
        const reqTools =
          ev.requested_tools && ev.requested_tools.length > 0
            ? ev.requested_tools
            : ((ev.tool_calls_requested || []).map((t) => t.name).filter(Boolean) as string[]);

        const tokensIn = ev.tokens_in ?? ev.prompt_tokens ?? ev.usage?.input_tokens ?? 0;
        const tokensOut = ev.tokens_out ?? ev.usage?.output_tokens ?? 0;
        const cachedTokens = ev.cached_tokens ?? 0;
        const reasoningTokens = ev.usage?.output_token_details?.reasoning ?? 0;
        const durationMs = ev.duration_ms ?? ev.elapsed_ms;
        const isErr = ev.type === "model_error" || Boolean(ev.error);

        let target: ModelCallTraceItem | undefined;
        if (ev.model_call_index !== undefined) {
          target = pendingModels.find((m) => m.callIndex === ev.model_call_index);
        }
        if (!target) {
          target = pendingModels.shift();
        } else {
          const pos = pendingModels.indexOf(target);
          if (pos >= 0) pendingModels.splice(pos, 1);
        }

        if (target) {
          target.status = isErr ? "error" : "ok";
          target.durationMs = durationMs;
          target.tokensIn = tokensIn;
          target.tokensOut = tokensOut;
          target.cachedTokens = cachedTokens;
          target.reasoningTokens = reasoningTokens;
          target.tokensEstimated = Boolean(ev.tokens_estimated);
          target.requestedTools = reqTools;
          target.output = ev.output;
          target.error = ev.error;
          if (target.input === undefined && ev.input !== undefined) {
            target.input = ev.input;
          }
          target.rawEvents.push(ev);
        } else {
          runningModelIdx += 1;
          items.push({
            kind: "model_call",
            uid: baseUid,
            node: bucket.node,
            callIndex: ev.model_call_index || runningModelIdx,
            status: isErr ? "error" : "ok",
            durationMs,
            messageCount: ev.message_count,
            toolCount: ev.tool_count,
            tokensIn,
            tokensOut,
            cachedTokens,
            reasoningTokens,
            tokensEstimated: Boolean(ev.tokens_estimated),
            requestedTools: reqTools,
            input: ev.input,
            output: ev.output,
            error: ev.error,
            seq: ev.seq,
            ts: ev.ts ?? ev.timestamp,
            rawEvents: [ev],
          });
        }
        continue;
      }

      if (ev.type === "tool_started") {
        const toolName = ev.tool_name || ev.tool || "tool";
        const args = (ev.arguments || ev.args || {}) as Record<string, unknown>;
        const toolItem: ToolCallTraceItem = {
          kind: "tool_call",
          uid: baseUid,
          node: bucket.node,
          toolName,
          toolCallId: ev.tool_call_id,
          status: "running",
          args,
          stateBefore: ev.state_before,
          stateDiff: [],
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        };
        if (ev.tool_call_id) {
          pendingToolsById.set(ev.tool_call_id, toolItem);
        }
        pendingToolsByName.push(toolItem);
        items.push(toolItem);
        continue;
      }

      if (ev.type === "tool_finished") {
        const toolName = ev.tool_name || ev.tool || "tool";
        const resObj = ev.result;
        const isFailed =
          ev.status === "error" ||
          ev.status === "exception" ||
          Boolean(ev.error) ||
          (Boolean(resObj) &&
            typeof resObj === "object" &&
            (resObj as Record<string, unknown>).ok === false);
        const durationMs = ev.duration_ms ?? ev.elapsed_ms;

        let target = ev.tool_call_id ? pendingToolsById.get(ev.tool_call_id) : undefined;
        if (!target) {
          target = pendingToolsByName.find((t) => t.toolName === toolName && t.status === "running");
        }

        if (target) {
          if (ev.tool_call_id) pendingToolsById.delete(ev.tool_call_id);
          const pos = pendingToolsByName.indexOf(target);
          if (pos >= 0) pendingToolsByName.splice(pos, 1);

          target.status = isFailed ? "error" : "ok";
          target.durationMs = durationMs;
          target.result = ev.result;
          target.resultSummary = ev.result_summary;
          if (ev.state_before !== undefined) target.stateBefore = ev.state_before;
          if (ev.state_after !== undefined) target.stateAfter = ev.state_after;
          target.stateDiff = computeStateDiff(target.stateBefore, target.stateAfter);
          target.error = ev.error;
          target.rawEvents.push(ev);
        } else {
          const args = (ev.arguments || ev.args || {}) as Record<string, unknown>;
          items.push({
            kind: "tool_call",
            uid: baseUid,
            node: bucket.node,
            toolName,
            toolCallId: ev.tool_call_id,
            status: isFailed ? "error" : "ok",
            durationMs,
            args,
            result: ev.result,
            resultSummary: ev.result_summary,
            stateBefore: ev.state_before,
            stateAfter: ev.state_after,
            stateDiff: computeStateDiff(ev.state_before, ev.state_after),
            error: ev.error,
            seq: ev.seq,
            ts: ev.ts ?? ev.timestamp,
            rawEvents: [ev],
          });
        }
        continue;
      }

      if (ev.type === "verifier_decision") {
        const failures =
          ev.failures && ev.failures.length > 0
            ? ev.failures
            : Array.isArray(ev.verifier_output?.failures)
            ? ev.verifier_output.failures
            : [];
        items.push({
          kind: "verifier_decision",
          uid: baseUid,
          node: bucket.node,
          passed: Boolean(ev.passed ?? ev.verifier_output?.passed),
          dodSummary: ev.dod_summary || (ev.passed ? "DoD đạt chuẩn." : "DoD chưa đạt."),
          nextDecision: ev.next_decision || "pass",
          failedTier: ev.failed_tier,
          answerRetry: ev.answer_retry ?? 0,
          failures,
          verifierOutput: ev.verifier_output,
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        });
        continue;
      }

      if (ev.type === "adaptive_radius_expansion") {
        items.push({
          kind: "adaptive_radius",
          uid: baseUid,
          node: bucket.node,
          fromRadius: ev.from_radius,
          toRadius: ev.to_radius,
          validRoomsBefore: ev.valid_rooms_before,
          reason: ev.reason,
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        });
        continue;
      }

      if (ev.type === "resolve_location_retry") {
        items.push({
          kind: "location_retry",
          uid: baseUid,
          node: bucket.node,
          attempts: Array.isArray(ev.attempts) ? ev.attempts : [],
          finalKind: ev.final_kind,
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        });
        continue;
      }

      if (ev.type === "suspicious_listing") {
        items.push({
          kind: "suspicious_listing",
          uid: baseUid,
          node: bucket.node,
          listingId: ev.listing_id,
          rules: ev.rules || [],
          seq: ev.seq,
          ts: ev.ts ?? ev.timestamp,
          rawEvents: [ev],
        });
        continue;
      }

      items.push({
        kind: "generic",
        uid: baseUid,
        node: bucket.node,
        eventType: ev.type,
        seq: ev.seq,
        ts: ev.ts ?? ev.timestamp,
        rawEvents: [ev],
      });
    }

    const durationMs = items.reduce((acc, it) => {
      if (it.kind === "model_call" || it.kind === "tool_call") {
        return acc + (it.durationMs || 0);
      }
      return acc;
    }, 0);

    const group: TraceStepGroup = {
      stepNumber: idx + 1,
      uid: `group-${idx}-${bucket.node}`,
      node: bucket.node,
      label: bucket.nodeStep?.label || meta.label,
      shortLabel: meta.shortLabel,
      icon: meta.icon,
      status: "ok",
      details: bucket.nodeStep?.details,
      autoSummary: "",
      durationMs,
      items,
      rawNodeStep: bucket.nodeStep,
    };

    group.status = deriveGroupStatus(group);
    group.autoSummary = buildAutoStepSummary(group);
    return group;
  });
}

export function summarizeTrace(events: AgentTraceEvent[], groups: TraceStepGroup[]): TraceSummary {
  let modelCallCount = 0;
  let toolCallCount = 0;
  let totalDurationMs = 0;
  let totalTokensIn = 0;
  let totalTokensOut = 0;
  let totalCachedTokens = 0;
  let tokensEstimated = false;
  let verifierPassed: boolean | null = null;
  let verifierDecision: string | null = null;
  let dodSummary: string | null = null;
  let hasWarning = false;
  let hasError = false;

  for (const g of groups) {
    if (g.status === "warning") hasWarning = true;
    if (g.status === "error") hasError = true;

    for (const it of g.items) {
      if (it.kind === "model_call") {
        modelCallCount += 1;
        totalDurationMs += it.durationMs || 0;
        totalTokensIn += it.tokensIn;
        totalTokensOut += it.tokensOut;
        totalCachedTokens += it.cachedTokens;
        if (it.tokensEstimated) tokensEstimated = true;
      } else if (it.kind === "tool_call") {
        toolCallCount += 1;
        totalDurationMs += it.durationMs || 0;
      } else if (it.kind === "verifier_decision") {
        verifierPassed = it.passed;
        verifierDecision = it.nextDecision;
        dodSummary = it.dodSummary;
      }
    }
  }

  let minTs: number | null = null;
  let maxTs: number | null = null;
  let runId: string | null = null;
  let sessionId: string | null = null;
  let versions: AgentTraceVersions | null = null;

  for (const ev of events) {
    const t = ev.ts ?? ev.timestamp;
    if (typeof t === "number") {
      minTs = minTs === null ? t : Math.min(minTs, t);
      maxTs = maxTs === null ? t : Math.max(maxTs, t);
    }
    if (!runId && ev.run_id) runId = ev.run_id;
    if (!sessionId && ev.session_id) sessionId = ev.session_id;
    if (!versions && ev.versions) versions = ev.versions;
  }

  const wallClockMs =
    minTs !== null && maxTs !== null && maxTs >= minTs ? Math.round((maxTs - minTs) * 1000) : null;

  return {
    stepCount: groups.length,
    modelCallCount,
    toolCallCount,
    totalDurationMs,
    wallClockMs,
    totalTokensIn,
    totalTokensOut,
    totalCachedTokens,
    tokensEstimated,
    verifierPassed,
    verifierDecision,
    dodSummary,
    hasWarning,
    hasError,
    runId,
    sessionId,
    versions,
  };
}

export function mergeTraceEvents(
  streamed: AgentTraceEvent[],
  authoritative?: AgentTraceEvent[],
): AgentTraceEvent[] {
  if (!authoritative || authoritative.length === 0) {
    return streamed;
  }
  if (!streamed || streamed.length === 0) {
    return authoritative;
  }

  const authById = new Map<string, AgentTraceEvent>();
  const matchedAuthIndices = new Set<number>();

  authoritative.forEach((ev) => {
    if (ev.id) authById.set(ev.id, ev);
  });

  const merged: AgentTraceEvent[] = streamed.map((ev) => {
    if (ev.type === "node_step") return ev;
    if (ev.id && authById.has(ev.id)) {
      const idx = authoritative.findIndex((a) => a.id === ev.id);
      if (idx >= 0) matchedAuthIndices.add(idx);
      return authById.get(ev.id)!;
    }
    return ev;
  });

  // Bổ sung những span trong authoritative chưa từng có trong stream (phòng trường hợp rớt event)
  const extras = authoritative.filter((_, idx) => !matchedAuthIndices.has(idx));
  if (extras.length > 0) {
    // Nếu stream không chứa span nào ngoài node_step, gộp trực tiếp theo node hoặc append
    const hasNonNodeStepInStream = streamed.some((e) => e.type !== "node_step");
    if (!hasNonNodeStepInStream) {
      return [...merged, ...extras];
    }
    // Chèn các span bị sót vào trước formatter_node (nếu có) hoặc cuối danh sách
    const fmtIdx = merged.findIndex((e) => e.type === "node_step" && e.node === "formatter_node");
    if (fmtIdx >= 0) {
      merged.splice(fmtIdx, 0, ...extras);
    } else {
      merged.push(...extras);
    }
  }

  return merged;
}

export function traceEventsToJsonl(events: AgentTraceEvent[]): string {
  return events.map((ev) => JSON.stringify(ev)).join("\n");
}
