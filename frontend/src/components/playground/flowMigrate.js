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
    if (data.playgroundAudienceScope == null || data.playgroundAudienceScope === "") {
      data.playgroundAudienceScope = (data.audienceBroadcastGroupId || "").trim()
        ? "group"
        : "all";
    }
    if (!Array.isArray(data.playgroundAudiencePhones)) data.playgroundAudiencePhones = [];
  } else if (!data.varKey) {
    data.varKey = makeVarKeyFromId(node.id);
  }

  if (type === "logicNode" && !data.logicMode) data.logicMode = "si";
  if (type === "sendTemplate" && data.variableValues == null)
    data.variableValues = {};
  if (type === "sendTemplate" && !Array.isArray(data.quickReplyButtons)) {
    data.quickReplyButtons = [];
  }
  if (type === "sendTemplate") {
    if (data.timeoutUnit == null || data.timeoutUnit === "") data.timeoutUnit = "h";
    if (data.templateStatus == null || data.templateStatus === "") {
      data.templateStatus = "unknown";
    }
  }

  if (type === "sendText") {
    const b = data.body;
    if (b == null || String(b).trim() === "") {
      const alt = data.message ?? data.text ?? data.content ?? data.value;
      if (alt != null && String(alt).trim() !== "") {
        data.body = String(alt);
      }
    }
  }

  if (type === "gemini") {
    if (!Array.isArray(data.intents)) data.intents = [];
    data.intents = data.intents.map((intent) => {
      if (!intent || typeof intent !== "object") return { keyword: "", label: "" };
      const kw = intent.keyword || intent.match || intent.value || intent.text || "";
      const lbl = intent.label || intent.title || intent.name || kw;
      return { ...intent, keyword: String(kw).trim(), label: String(lbl).trim() };
    });
    if (data.systemPrompt == null) data.systemPrompt = "";
    if (data.toneInstructions == null) data.toneInstructions = "";
    if (data.clarifyOnUnknown == null) data.clarifyOnUnknown = true;
    if (data.maxClarifyAttempts == null || data.maxClarifyAttempts === "")
      data.maxClarifyAttempts = 3;
    if (data.useEmbeddingSimilarity == null) data.useEmbeddingSimilarity = false;
    if (data.embeddingSimilarityThreshold == null || data.embeddingSimilarityThreshold === "")
      data.embeddingSimilarityThreshold = 0.62;
    if (data.structuredMemory == null) data.structuredMemory = true;
  }
  if (type === "interactiveNode") {
    if (!data.body) {
      const alt = data.bodyText ?? data.text ?? data.message ?? data.content;
      data.body = alt != null && String(alt).trim() ? String(alt) : "";
    }
    if (!data.uiKind) {
      const it = data.interactiveType || data.type_interactive || "";
      data.uiKind = String(it).toLowerCase().includes("list") ? "list" : "buttons";
    }
    if (!Array.isArray(data.choices) || !data.choices.length) {
      const raw = data.buttons || data.options || data.items;
      if (Array.isArray(raw) && raw.length) {
        data.choices = raw.map((item, idx) => {
          if (typeof item === "string" && item.trim()) return { id: `btn_${idx}`, title: item.trim() };
          if (item && typeof item === "object") {
            const title = item.title || item.text || item.label || item.name || item.value || "";
            return { id: item.id || `btn_${idx}`, title: String(title).trim() || `Option ${idx + 1}` };
          }
          return { id: `btn_${idx}`, title: `Option ${idx + 1}` };
        });
      } else {
        data.choices = [{ title: "Oui" }, { title: "Non" }];
      }
    }
    data.choices = data.choices.map((c, i) => ({
      ...c,
      id: c.id != null && String(c.id).trim() ? c.id : `btn_${i}`,
    }));
    if (data.listButtonText == null) data.listButtonText = "Voir les options";
    if (data.timeoutUnit == null || data.timeoutUnit === "") data.timeoutUnit = "h";
  }
  if (type === "routerNode") {
    const normalizeRoutes = (arr) => {
      if (!Array.isArray(arr) || !arr.length) return null;
      const out = [];
      for (const item of arr) {
        if (typeof item === "string" && item.trim()) {
          const s = item.trim();
          out.push({ label: s, match: s });
          continue;
        }
        if (!item || typeof item !== "object") continue;
        const matchRaw = [
          item.match,
          item.keyword,
          item.value,
          item.text,
          item.pattern,
          item.reply,
          item.id,
          item.message,
        ].find((x) => typeof x === "string" && x.trim());
        const labelRaw = [item.label, item.title, item.name].find(
          (x) => typeof x === "string" && x.trim()
        );
        const match = (matchRaw && matchRaw.trim()) || (labelRaw && labelRaw.trim()) || "";
        let label = (labelRaw && labelRaw.trim()) || "";
        if (!match) continue;
        if (!label) label = match;
        out.push({ label, match });
      }
      return out.length ? out : null;
    };
    const keys = ["routes", "branches", "options", "conditions"];
    let fixed = null;
    for (const k of keys) {
      fixed = normalizeRoutes(data[k]);
      if (fixed) {
        data.routes = fixed;
        break;
      }
    }
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
    if (data.untilFromVarKey == null) data.untilFromVarKey = "";
    if (data.timezoneNote == null || data.timezoneNote === "") {
      data.timezoneNote = "Europe/Paris";
    }
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

function validSourceHandles(node) {
  const t = node.type;
  const d = node.data || {};
  if (t === "start") return new Set([null, undefined]);
  if (t === "sendText" || t === "delayNode" || t === "waitUntilNode")
    return new Set([null, undefined]);
  if (t === "sendTemplate") {
    const s = new Set([null, undefined]);
    if (Array.isArray(d.quickReplyButtons) && d.quickReplyButtons.length) s.add("timeout");
    return s;
  }
  if (t === "timeWindowNode") return new Set([null, undefined, "inside", "outside"]);
  if (t === "interactiveNode") return new Set([null, undefined, "timeout"]);
  if (t === "gemini") {
    const s = new Set([null, undefined]);
    const intents = Array.isArray(d.intents) ? d.intents : [];
    intents.forEach((_, i) => s.add(`intent-${i}`));
    if (intents.length) s.add("intent-unknown");
    return s;
  }
  if (t === "routerNode") {
    const s = new Set([null, undefined]);
    const routes = Array.isArray(d.routes) ? d.routes : [];
    routes.forEach((_, i) => s.add(`route-${i}`));
    s.add("escape");
    return s;
  }
  if (t === "logicNode") {
    const mode = d.logicMode || "si";
    if (mode === "si") return new Set([null, undefined, "true", "false"]);
    if (mode === "ou") return new Set([null, undefined, "a", "b"]);
    return new Set([null, undefined]);
  }
  if (t === "handoffNode") return new Set([null, undefined]);
  return null;
}

export function migrateFlowPayload(payload) {
  if (!payload?.nodes) return payload;
  const nodes = payload.nodes.map(migrateNode);
  let edges = Array.isArray(payload.edges) ? payload.edges : [];

  const nodeMap = {};
  for (const n of nodes) nodeMap[n.id] = n;

  edges = edges
    .map((e) => {
      const srcNode = nodeMap[e.source];
      if (!srcNode) return e;
      const allowed = validSourceHandles(srcNode);
      if (allowed === null) return e;
      const handle = e.sourceHandle ?? null;
      if (!allowed.has(handle) && handle != null) {
        return { ...e, sourceHandle: null };
      }
      return e;
    })
    .filter((e) => {
      const srcNode = nodeMap[e.source];
      if (!srcNode) return false;
      const allowed = validSourceHandles(srcNode);
      if (allowed === null) return true;
      const handle = e.sourceHandle ?? null;
      return allowed.has(handle);
    });

  const seen = new Set();
  edges = edges.filter((e) => {
    const key = `${e.source}::${e.sourceHandle ?? ""}::${e.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return { ...payload, nodes, edges };
}
