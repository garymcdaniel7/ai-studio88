import assert from "node:assert/strict";
import { test } from "node:test";
import {
  assemblePrompt,
  clampNumber,
  classifyQueueError,
  DEFAULT_WORKSHOP_CONTROLS,
  FRAME_GRID_VALUES,
  serializeWorkshopRequest,
  snapFrameGrid,
} from "./make-contract.ts";

test("uses the exact H3 frame-grid contract and snaps invalid values", () => {
  assert.deepEqual(FRAME_GRID_VALUES, [124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600]);
  assert.equal(snapFrameGrid(216), 209);
  assert.equal(snapFrameGrid(280), 277);
  assert.equal(snapFrameGrid(600), 600);
});

test("assembles H3 prompt sections and optional workshop injectors", () => {
  const prompt = assemblePrompt(
    { subject: "A runner", action: "is moving quickly", camera: "tracking shot", lighting: "soft light", sound: "footsteps" },
    { antiPlastic: true, speedVerbs: true, frameGrid: true },
    226,
  );
  assert.match(prompt, /### Subject/);
  assert.match(prompt, /### Action\nmoving quickly/);
  assert.match(prompt, /### Anti-Plastic/);
  assert.match(prompt, /### Frame Grid\n226/);
});

test("serializes bounded tier controls without an organization selector or secret", () => {
  const request = serializeWorkshopRequest(
    { ...DEFAULT_WORKSHOP_CONTROLS, cfg: 99, steps: 0, batchSize: 50, frameGrid: 243, seedMode: "random" },
    "### Subject\nA subject",
    99,
  );
  assert.equal(request.cfg_scale, 30);
  assert.equal(request.steps, 1);
  assert.equal(request.batch_size, 16);
  assert.equal(request.variation_count, 50);
  assert.equal(request.seed, undefined);
  assert.equal("org_id" in request, false);
  assert.equal("api_key" in request, false);
});

test("clamps non-finite input and classifies queue failure recovery", () => {
  assert.equal(clampNumber(Number.NaN, 1, 4), 1);
  assert.equal(clampNumber(9, 1, 4), 4);
  assert.equal(classifyQueueError("CUDA out of memory"), "oom");
  assert.equal(classifyQueueError("RunComfy provider unreachable"), "provider-down");
  assert.equal(classifyQueueError("request timed out"), "timeout");
  assert.equal(classifyQueueError("invalid workflow"), "generic");
});
