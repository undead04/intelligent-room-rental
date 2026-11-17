import test from "node:test";
import assert from "node:assert/strict";
import {
  buildTraceStepGroups,
  computeStateDiff,
  mergeTraceEvents,
  summarizeTrace,
  traceEventsToJsonl,
} from "./traceUtils.ts";

test("Nhóm 1: Happy Path - nhóm đầy đủ các node, ghép cặp LLM/Tool, tính token và state diff", () => {
  const events = [
    { type: "node_step", node: "guardrail_node", label: "Kiểm tra an toàn", details: "Hợp lệ", status: "ok" },
    { type: "node_step", node: "understand_node", label: "Phân tích Intent", details: "Vị trí: UIT", status: "ok" },
    { type: "model_request", id: "e1", seq: 1, ts: 100.0, node: "understand_node", model_call_index: 1, message_count: 2, tool_count: 0, input: [{ role: "user", content: "gần UIT dưới 3tr" }] },
    { type: "model_response", id: "e2", seq: 2, ts: 101.2, node: "understand_node", tokens_in: 120, tokens_out: 45, cached_tokens: 20, tokens_estimated: false, output: { intent: "new_search", location_text: "UIT", max_price: 3000000 }, duration_ms: 1200 },
    { type: "node_step", node: "retrieval_node", label: "Tìm phòng", details: "Tìm thấy 5 phòng", status: "ok" },
    {
      type: "tool_started",
      id: "e3",
      seq: 3,
      ts: 101.21,
      node: "retrieval_node",
      tool_name: "resolve_location",
      tool_call_id: "tc_1",
      args: { query: "UIT", kind: "place" },
      state_before: { lat: null, lng: null },
    },
    {
      type: "tool_finished",
      id: "e4",
      seq: 4,
      ts: 101.25,
      node: "retrieval_node",
      tool_name: "resolve_location",
      tool_call_id: "tc_1",
      status: "ok",
      duration_ms: 40,
      result: { lat: 10.87, lng: 106.803 },
      result_summary: { kind: "point", lat: 10.87, lng: 106.803 },
      state_before: { lat: null, lng: null },
      state_after: { lat: 10.87, lng: 106.803 },
    },
    {
      type: "adaptive_radius_expansion",
      id: "e5",
      seq: 5,
      ts: 101.3,
      node: "retrieval_node",
      from_radius: 2.5,
      to_radius: 3.5,
      valid_rooms_before: 1,
      reason: "Mở rộng bán kính lên 3.5km",
    },
    { type: "node_step", node: "verify_node", label: "Kiểm chứng", details: "Đạt chuẩn", status: "ok" },
    {
      type: "verifier_decision",
      id: "e6",
      seq: 6,
      ts: 102.0,
      node: "verify_node",
      passed: true,
      failures: [],
      next_decision: "pass",
      dod_summary: "DoD đạt (4/4).",
    },
    { type: "node_step", node: "formatter_node", label: "Đóng gói", details: "Hoàn tất", status: "ok" },
  ];

  const groups = buildTraceStepGroups(events);
  assert.equal(groups.length, 5);
  assert.equal(groups[0].node, "guardrail_node");
  assert.equal(groups[1].items.length, 1);
  assert.equal(groups[1].items[0].kind, "model_call");
  if (groups[1].items[0].kind === "model_call") {
    assert.equal(groups[1].items[0].tokensIn, 120);
    assert.equal(groups[1].items[0].tokensOut, 45);
    assert.equal(groups[1].items[0].cachedTokens, 20);
    assert.equal(groups[1].items[0].status, "ok");
  }

  assert.equal(groups[2].node, "retrieval_node");
  assert.equal(groups[2].status, "warning"); // do có adaptive_radius_expansion
  assert.equal(groups[2].items.length, 2);
  if (groups[2].items[0].kind === "tool_call") {
    assert.equal(groups[2].items[0].stateDiff.length, 2);
  }

  const summary = summarizeTrace(events, groups);
  assert.equal(summary.stepCount, 5);
  assert.equal(summary.modelCallCount, 1);
  assert.equal(summary.toolCallCount, 1);
  assert.equal(summary.totalTokensIn, 120);
  assert.equal(summary.totalTokensOut, 45);
  assert.equal(summary.verifierPassed, true);
  assert.equal(summary.wallClockMs, 2000);
});

test("Nhóm 2: Boundary & Edge Cases - mảng rỗng, không có node_step, verifier fail, retry 2 vòng", () => {
  assert.deepEqual(buildTraceStepGroups([]), []);
  assert.deepEqual(computeStateDiff(null, { a: 1 }), []);

  // Không có node_step (REST fallback) + retry vòng 2
  const retryEvents = [
    { type: "model_request", id: "m1", seq: 1, node: "decision_node", model_call_index: 1 },
    { type: "model_response", id: "m2", seq: 2, node: "decision_node", tokens_in: 50, tokens_out: 20, output: "3KM" },
    {
      type: "verifier_decision",
      id: "v1",
      seq: 3,
      node: "verify_node",
      passed: false,
      failed_tier: "external_cross_check",
      next_decision: "retry",
      answer_retry: 1,
      failures: [{ condition_id: "cond_factual_grounding", message: "Sai khoảng cách" }],
    },
    { type: "model_request", id: "m3", seq: 4, node: "decision_node", model_call_index: 2 },
    { type: "model_error", id: "m4", seq: 5, node: "decision_node", error: "429 Quota exceeded", duration_ms: 300 },
    { type: "suspicious_listing", id: "s1", seq: 6, node: "retrieval_node", listing_id: "room_9", rules: ["prompt_injection"] },
    { type: "custom_unknown_span", id: "u1", seq: 7, node: "retrieval_node" },
  ];

  const groups = buildTraceStepGroups(retryEvents);
  assert.equal(groups.length, 4);
  assert.equal(groups[0].node, "decision_node");
  assert.equal(groups[1].node, "verify_node");
  assert.equal(groups[1].status, "error");
  assert.equal(groups[2].node, "decision_node");
  assert.equal(groups[2].status, "error");
  assert.equal(groups[3].items.length, 2); // suspicious_listing + generic
  assert.equal(groups[3].items[1].kind, "generic");
});

test("Nhóm 3: Immutability & Merge consistency - giữ node_step khi stream xong và không mutate input", () => {
  const streamed = Object.freeze([
    Object.freeze({ type: "node_step", node: "guardrail_node", label: "An toàn", status: "ok" }),
    Object.freeze({ type: "node_step", node: "understand_node", label: "Phân tích", status: "ok" }),
    Object.freeze({ type: "model_request", id: "ev_1", seq: 1, node: "understand_node", model_call_index: 1 }),
    Object.freeze({ type: "node_step", node: "formatter_node", label: "Đóng gói", status: "ok" }),
  ]);

  const authoritative = Object.freeze([
    Object.freeze({ type: "model_request", id: "ev_1", seq: 1, node: "understand_node", model_call_index: 1, run_id: "run_abc" }),
    Object.freeze({ type: "model_response", id: "ev_2", seq: 2, node: "understand_node", tokens_in: 80, tokens_out: 30, run_id: "run_abc" }),
  ]);

  const merged = mergeTraceEvents([...streamed], [...authoritative]);
  assert.equal(merged.filter((e) => e.type === "node_step").length, 3);
  assert.equal(merged.some((e) => e.id === "ev_1" && e.run_id === "run_abc"), true);
  assert.equal(merged.some((e) => e.id === "ev_2" && e.tokens_in === 80), true);
  // ev_2 được chèn trước formatter_node
  const ev2Idx = merged.findIndex((e) => e.id === "ev_2");
  const fmtIdx = merged.findIndex((e) => e.type === "node_step" && e.node === "formatter_node");
  assert.ok(ev2Idx >= 0 && ev2Idx < fmtIdx);
});

test("Nhóm 4: Persistence JSONL - xuất và parse lại từng dòng nguyên vẹn", () => {
  const sample = [
    { id: "ev_1", seq: 1, type: "model_request", node: "understand_node", run_id: "run_1" },
    { id: "ev_2", seq: 2, type: "verifier_decision", node: "verify_node", passed: true, run_id: "run_1" },
  ];
  const jsonl = traceEventsToJsonl(sample);
  const parsed = jsonl.split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(parsed, sample);
});
