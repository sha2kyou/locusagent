import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  mergeTodoPlans,
  resolveTodoPlan,
  type TodoPlan,
} from "./todo.ts";

function plan(steps: { id: string; title: string; status: string }[], planId = "tp_test"): TodoPlan {
  return {
    plan_id: planId,
    title: "Task",
    steps: steps.map((s) => ({
      id: s.id,
      title: s.title,
      status: s.status as TodoPlan["steps"][number]["status"],
    })),
  };
}

describe("mergeTodoPlans", () => {
  it("keeps done status when session snapshot lags message snapshot", () => {
    const session = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "in_progress" },
    ]);
    const fromParts = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "done" },
    ]);
    const merged = mergeTodoPlans(session, fromParts);
    assert.equal(merged.steps[1]?.status, "done");
  });

  it("keeps done status when message snapshot lags session snapshot", () => {
    const session = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "done" },
    ]);
    const fromParts = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "in_progress" },
    ]);
    const merged = mergeTodoPlans(session, fromParts);
    assert.equal(merged.steps[1]?.status, "done");
  });
});

describe("resolveTodoPlan", () => {
  it("prefers session plan when plan_id differs from stale message snapshot", () => {
    const session = plan([{ id: "s1", title: "A", status: "pending" }], "tp_new");
    const fromParts = plan([{ id: "s1", title: "A", status: "in_progress" }], "tp_old");
    const resolved = resolveTodoPlan(fromParts, session, true, true);
    assert.equal(resolved?.plan_id, "tp_new");
    assert.equal(resolved?.steps[0]?.status, "pending");
  });

  it("merges same plan_id snapshots for the last assistant message", () => {
    const session = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "in_progress" },
    ]);
    const fromParts = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "done" },
    ]);
    const resolved = resolveTodoPlan(fromParts, session, true, true);
    assert.equal(resolved?.steps[1]?.status, "done");
  });

  it("marks pending steps interrupted on historical assistant messages", () => {
    const fromParts = plan([
      { id: "s1", title: "A", status: "done" },
      { id: "s2", title: "B", status: "in_progress" },
    ]);
    const resolved = resolveTodoPlan(fromParts, null, false, true);
    assert.equal(resolved?.steps[1]?.status, "interrupted");
  });
});
