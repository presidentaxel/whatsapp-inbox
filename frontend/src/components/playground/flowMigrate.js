/**
 * Normalise les nœuds chargés (clés de variables, anciens types if/or).
 */
export function makeVarKeyFromId(id) {
  const s = String(id).replace(/-/g, "");
  return `réponse_${s.slice(0, 12)}`;
}

export function migrateNode(node) {
  if (!node || typeof node !== "object") return node;
  let type = node.type;
  const data = { ...(node.data || {}) };

  if (type === "ifNode") {
    type = "logicNode";
    data.logicMode = data.logicMode || "si";
  } else if (type === "orNode") {
    type = "logicNode";
    data.logicMode = "ou";
  }

  if (type === "start") {
    if (!data.varKey) data.varKey = "réponse_entrée";
    if (!data.triggerType) data.triggerType = "message_in";
    if (!data.messageMatch) data.messageMatch = "contains";
    if (!data.scheduleRepeat) data.scheduleRepeat = "none";
    if (data.audienceBroadcastGroupId == null) data.audienceBroadcastGroupId = "";
    if (data.campaignScheduledFor == null) data.campaignScheduledFor = "";
  } else if (!data.varKey) {
    data.varKey = makeVarKeyFromId(node.id);
  }

  if (type === "logicNode" && !data.logicMode) data.logicMode = "si";
  if (type === "sendTemplate" && data.variableValues == null)
    data.variableValues = {};
  if (type === "sendTemplate" && !Array.isArray(data.quickReplyButtons)) {
    data.quickReplyButtons = [];
  }

  if (type === "gemini") {
    if (!Array.isArray(data.intents)) data.intents = [];
    if (data.systemPrompt == null) data.systemPrompt = "";
  }
  if (type === "interactiveNode") {
    if (!data.body) data.body = "";
    if (!data.uiKind) data.uiKind = "buttons";
    if (!Array.isArray(data.choices) || !data.choices.length) {
      data.choices = [{ title: "Oui" }, { title: "Non" }];
    }
    data.choices = data.choices.map((c, i) => ({
      ...c,
      id: c.id != null && String(c.id).trim() ? c.id : `btn_${i}`,
    }));
    if (data.listButtonText == null) data.listButtonText = "Voir les options";
    if (data.timeoutUnit == null || data.timeoutUnit === "") data.timeoutUnit = "h";
  }
  if (type === "routerNode") {
    if (!Array.isArray(data.routes) || !data.routes.length) {
      data.routes = [
        { label: "Option A", match: "Option A" },
        { label: "Option B", match: "Option B" },
      ];
    }
  }
  if (type === "handoffNode") {
    if (data.tagsText == null) data.tagsText = "";
    if (data.assignAgent == null) data.assignAgent = "";
    if (data.internalMessage == null) data.internalMessage = "";
  }

  if (type === "delayNode") {
    if (data.duration == null || data.duration === "") data.duration = "5";
    if (!data.unit) data.unit = "s";
  }
  if (type === "waitUntilNode") {
    if (data.until == null) data.until = "";
  }
  if (type === "timeWindowNode") {
    if (!Array.isArray(data.activeDays) || data.activeDays.length === 0) {
      data.activeDays = ["1", "2", "3", "4", "5"];
    }
    if (!data.startTime) data.startTime = "09:00";
    if (!data.endTime) data.endTime = "18:00";
  }

  return { ...node, type, data };
}

export function migrateFlowPayload(payload) {
  if (!payload?.nodes) return payload;
  return {
    ...payload,
    nodes: payload.nodes.map(migrateNode),
  };
}
