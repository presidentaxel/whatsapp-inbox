import { describe, expect, it } from "vitest";
import {
  createDefaultAgentStudioConfig,
  normalizeAgentStudioConfig,
  validateAgentStudioConfig,
} from "./agentStudioModel";

describe("agentStudioModel", () => {
  it("creates default config", () => {
    const cfg = createDefaultAgentStudioConfig();
    expect(cfg.routing.fallback).toBe("human");
    expect(cfg.deployment.status).toBe("draft");
  });

  it("normalizes partial input with defaults", () => {
    const cfg = normalizeAgentStudioConfig({
      name: "Support",
      objective: { primaryGoal: "Réduire délai de réponse" },
    });
    expect(cfg.name).toBe("Support");
    expect(cfg.objective.primaryGoal).toContain("délai");
    expect(cfg.routing.confidenceThreshold).toBe(0.72);
  });

  it("normalizes JSON string config from API", () => {
    const raw =
      '{"name":"Agent SAV","objective":{"primary_goal":"SAV","kpi":[],"audience":"Louis"}}';
    const cfg = normalizeAgentStudioConfig(raw);
    expect(cfg.name).toBe("Agent SAV");
    expect(cfg.objective.primaryGoal).toBe("SAV");
    expect(cfg.objective.audience).toBe("Louis");
  });

  it("returns validation issues for invalid config", () => {
    const issues = validateAgentStudioConfig({
      objective: { primaryGoal: "" },
      routing: {
        confidenceThreshold: 0,
        intents: [{ key: "support", handler: "A" }, { key: "support", handler: "B" }],
      },
      deployment: { status: "canary", canaryPercent: null },
    });
    expect(issues.length).toBeGreaterThan(0);
    expect(issues.some((i) => i.message.includes("Objectif principal"))).toBe(true);
    expect(issues.some((i) => i.message.includes("doublon"))).toBe(true);
  });
});

