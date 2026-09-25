import assert from "node:assert/strict";
import {
  canRetryGeneration,
  detailStatusLabel,
  tripDetailShell,
} from "../src/lib/tripDetailState.ts";

const dated = { start_date: "2026-10-01", end_date: "2026-10-05" };

assert.equal(tripDetailShell({ status: "generating", ...dated }), "generating");
assert.equal(tripDetailShell({ status: "generation_failed", ...dated }), "failed");
assert.equal(tripDetailShell({ status: "draft", start_date: null, end_date: null }), "draft");
assert.equal(tripDetailShell({ status: "generated", start_date: null, end_date: null }), "draft");
assert.equal(tripDetailShell({ status: "generated", ...dated }), "ready");
assert.equal(tripDetailShell({ status: "generation_failed", start_date: null, end_date: null }), "failed");

assert.equal(canRetryGeneration({ status: "generation_failed", ...dated }), true);
assert.equal(canRetryGeneration({ status: "generation_failed", start_date: null, end_date: null }), false);
assert.equal(canRetryGeneration({ status: "generating", ...dated }), false);
assert.equal(canRetryGeneration({ status: "draft", start_date: null, end_date: null }), false);
assert.equal(canRetryGeneration({ status: "generated", ...dated }), false);

assert.equal(detailStatusLabel("generating"), "规划中");
assert.equal(detailStatusLabel("generation_failed"), "可重试");
assert.equal(detailStatusLabel("draft"), "草稿");
assert.equal(detailStatusLabel("generated"), "已生成");

console.log("trip detail shell checks passed");
