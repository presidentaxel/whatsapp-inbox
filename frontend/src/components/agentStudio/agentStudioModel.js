export function createDefaultAgentStudioConfig(name = "Nouvel agent") {
  return {
    name,
    objective: {
      primaryGoal: "",
      kpi: [],
      audience: "",
    },
    routing: {
      fallback: "human",
      confidenceThreshold: 0.72,
      intents: [],
    },
    policies: {
      tone: "pro",
      forbiddenActions: [],
      escalationRules: [],
    },
    capabilities: {
      allowedTools: [],
      requireApprovalFor: [],
    },
    tests: [],
    deployment: {
      status: "draft",
      canaryPercent: null,
    },
  };
}

export function normalizeAgentStudioConfig(raw) {
  const base = createDefaultAgentStudioConfig();
  let parsed = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = null;
    }
  }
  if (!parsed || typeof parsed !== "object") return base;
  raw = parsed;
  const objectiveRaw = raw.objective || {};
  const routingRaw = raw.routing || {};
  const policiesRaw = raw.policies || {};
  const capsRaw = raw.capabilities || {};
  const deploymentRaw = raw.deployment || {};
  return {
    ...base,
    ...raw,
    objective: {
      ...base.objective,
      ...objectiveRaw,
      primaryGoal: objectiveRaw.primaryGoal ?? objectiveRaw.primary_goal ?? base.objective.primaryGoal,
    },
    routing: {
      ...base.routing,
      ...routingRaw,
      confidenceThreshold:
        routingRaw.confidenceThreshold ??
        routingRaw.confidence_threshold ??
        base.routing.confidenceThreshold,
    },
    policies: {
      ...base.policies,
      ...policiesRaw,
      forbiddenActions:
        policiesRaw.forbiddenActions ?? policiesRaw.forbidden_actions ?? base.policies.forbiddenActions,
      escalationRules:
        policiesRaw.escalationRules ?? policiesRaw.escalation_rules ?? base.policies.escalationRules,
    },
    capabilities: {
      ...base.capabilities,
      ...capsRaw,
      allowedTools: capsRaw.allowedTools ?? capsRaw.allowed_tools ?? base.capabilities.allowedTools,
      requireApprovalFor:
        capsRaw.requireApprovalFor ??
        capsRaw.require_approval_for ??
        base.capabilities.requireApprovalFor,
    },
    deployment: {
      ...base.deployment,
      ...deploymentRaw,
      canaryPercent:
        deploymentRaw.canaryPercent ?? deploymentRaw.canary_percent ?? base.deployment.canaryPercent,
    },
    tests: Array.isArray(raw.tests)
      ? raw.tests.map((t) => ({
          ...t,
          expectedBehavior: t.expectedBehavior ?? t.expected_behavior ?? "",
          expectedRoute: t.expectedRoute ?? t.expected_route ?? null,
        }))
      : [],
  };
}

export function validateAgentStudioConfig(config) {
  const cfg = normalizeAgentStudioConfig(config);
  const issues = [];
  if (!String(cfg.objective.primaryGoal || "").trim()) {
    issues.push({ severity: "error", message: "Objectif principal requis." });
  }
  const threshold = Number(cfg.routing.confidenceThreshold);
  if (!Number.isFinite(threshold) || threshold <= 0 || threshold > 1) {
    issues.push({
      severity: "error",
      message: "Le seuil de confiance doit être entre 0 et 1.",
    });
  }
  const keys = new Set();
  for (const intent of cfg.routing.intents || []) {
    const key = String(intent?.key || "").trim();
    if (!key) {
      issues.push({ severity: "error", message: "Une intention sans clé a été trouvée." });
      continue;
    }
    if (keys.has(key)) {
      issues.push({ severity: "error", message: `Intention en doublon: ${key}` });
    }
    keys.add(key);
  }
  if (cfg.deployment.status === "canary" && !cfg.deployment.canaryPercent) {
    issues.push({ severity: "error", message: "Canary % requis pour un déploiement canary." });
  }
  return issues;
}

