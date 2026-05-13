/**
 * Contrôles statiques du graphe Playground (aide à la conception, pas une garantie runtime).
 */

/**
 * Empreinte du graphe utile au contrôle (ignore les positions - le déplacement ne doit pas tout recalculer).
 * Utilisée pour déclencher la revalidation quand le contenu change vraiment.
 */
export function validationGraphFingerprint(nodes, edges) {
  const ns = [...(nodes || [])]
    .sort((a, b) => String(a.id).localeCompare(String(b.id)))
    .map((n) => ({ id: n.id, type: n.type, data: n.data }));
  const es = [...(edges || [])]
    .sort((a, b) => String(a.id).localeCompare(String(b.id)))
    .map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
    }));
  try {
    return JSON.stringify({ ns, es });
  } catch {
    return `${(nodes || []).length}-${(edges || []).length}`;
  }
}

export function formatPlaygroundApiError(err) {
  const d = err?.response?.data?.detail;
  if (typeof d === "string" && d.trim()) return d.trim();
  if (Array.isArray(d) && d.length) {
    const msgs = d
      .map((x) => (x && typeof x.msg === "string" ? x.msg : null))
      .filter(Boolean);
    if (msgs.length) return msgs.join(" · ");
  }
  const m = err?.message;
  if (typeof m === "string" && m.trim()) return m.trim();
  return "Erreur réseau ou serveur.";
}

/**
 * @returns {Array<{ severity: 'error' | 'warning', message: string, nodeId?: string }>}
 */
export function validatePlaygroundGraph(nodes, edges) {
  const issues = [];
  if (!Array.isArray(nodes) || nodes.length === 0) {
    issues.push({
      severity: "error",
      message: "Le scénario est vide.",
    });
    return issues;
  }

  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const starts = nodes.filter((n) => n.type === "start");

  if (starts.length === 0) {
    issues.push({
      severity: "error",
      message: "Ajoutez au moins un bloc Déclencheur (entrée du scénario).",
    });
  }

  const outgoing = new Map();
  const incomingCount = new Map();
  for (const n of nodes) {
    outgoing.set(n.id, []);
    incomingCount.set(n.id, 0);
  }
  for (const e of edges || []) {
    if (!e?.source || !e?.target) continue;
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) continue;
    outgoing.get(e.source).push(e.target);
    incomingCount.set(e.target, (incomingCount.get(e.target) || 0) + 1);
  }

  for (const s of starts) {
    const out = outgoing.get(s.id) || [];
    if (out.length === 0) {
      issues.push({
        severity: "warning",
        message: "Déclencheur sans liaison sortante : reliez-le à un bloc.",
        nodeId: s.id,
      });
    }
  }

  if (starts.length > 0) {
    const reachable = new Set();
    const queue = starts.map((s) => s.id);
    while (queue.length) {
      const id = queue.shift();
      if (reachable.has(id)) continue;
      reachable.add(id);
      for (const t of outgoing.get(id) || []) {
        if (!reachable.has(t)) queue.push(t);
      }
    }
    for (const n of nodes) {
      if (n.type === "start") continue;
      if (!reachable.has(n.id)) {
        const label = n.data?.varKey ? ` (${n.data.varKey})` : "";
        issues.push({
          severity: "warning",
          message: `Bloc « ${nodeTypeLabel(n.type)} »${label} non relié au déclencheur.`,
          nodeId: n.id,
        });
      }
    }
  }

  for (const n of nodes) {
    const d = n.data || {};
    const type = n.type;

    if (type === "sendText") {
      const body = String(d.body ?? "").trim();
      if (!body) {
        issues.push({
          severity: "warning",
          message: "Message texte vide.",
          nodeId: n.id,
        });
      }
    }

    if (type === "sendTemplate") {
      const key = String(d.selectedTemplateKey ?? "").trim();
      const name = String(d.templateName ?? "").trim();
      const lang = String(d.templateLanguage ?? "").trim();
      const hasTemplate = Boolean(key || (name && lang));
      if (!hasTemplate) {
        issues.push({
          severity: "warning",
          message: "Template non choisi ou nom/langue manquants.",
          nodeId: n.id,
        });
      } else if (d.templateStatus === "rejected") {
        issues.push({
          severity: "warning",
          message: "Template indiqué comme rejeté par Meta.",
          nodeId: n.id,
        });
      }
    }

    if (type === "gemini") {
      const sys = String(d.systemPrompt ?? "").trim();
      if (!sys) {
        issues.push({
          severity: "warning",
          message: "Bloc Gemini sans consigne (prompt système) renseignée.",
          nodeId: n.id,
        });
      }
    }

    if (type === "logicNode") {
      const mode = d.logicMode || "si";
      const cond = String(d.condition ?? "").trim();
      if (mode === "si" && !cond) {
        issues.push({
          severity: "warning",
          message: "Bloc logique sans condition.",
          nodeId: n.id,
        });
      }
    }

    if (type === "routerNode") {
      const routes = Array.isArray(d.routes) ? d.routes : [];
      if (routes.length === 0) {
        issues.push({
          severity: "warning",
          message: "Routeur sans branche définie.",
          nodeId: n.id,
        });
      }
    }

    if (type === "interactiveNode") {
      const body = String(d.body ?? "").trim();
      if (!body) {
        issues.push({
          severity: "warning",
          message: "Bloc interactif sans texte de message.",
          nodeId: n.id,
        });
      }
    }
  }

  const handleKey = (src, h) => `${src}::${h ?? ""}`;
  const byHandle = new Map();
  for (const e of edges || []) {
    if (!e?.source || !e?.target) continue;
    if (!nodeById.has(e.source) || !nodeById.has(e.target)) continue;
    const k = handleKey(e.source, e.sourceHandle ?? null);
    if (!byHandle.has(k)) byHandle.set(k, []);
    byHandle.get(k).push(e.target);
  }
  for (const [k, tgts] of byHandle) {
    const uniq = new Set(tgts);
    if (uniq.size > 1) {
      const id = k.split("::")[0];
      issues.push({
        severity: "warning",
        message:
          "Plusieurs liaisons depuis la même sortie : le moteur ne suivra qu’une seule branche. Une seule liaison par poignée.",
        nodeId: id,
      });
    }
  }

  for (const n of nodes) {
    if (n.type === "routerNode") {
      const routes = Array.isArray(n.data?.routes) ? n.data.routes : [];
      if (routes.length === 0) continue;
      const outgoing = (edges || []).filter((e) => e.source === n.id);
      if (outgoing.length === 0) continue;
      const hasEscape = outgoing.some((e) => e.sourceHandle === "escape");
      if (!hasEscape) {
        issues.push({
          severity: "warning",
          message:
            "Routeur : ajoutez une branche « escape » pour le texte libre ou les formulations imprévues.",
          nodeId: n.id,
        });
      }
    }
    if (n.type === "gemini") {
      const intents = Array.isArray(n.data?.intents) ? n.data.intents : [];
      if (intents.length === 0) continue;
      const outgoingG = (edges || []).filter((e) => e.source === n.id);
      if (outgoingG.length === 0) continue;
      const hasUnknown = outgoingG.some((e) => e.sourceHandle === "intent-unknown");
      if (!hasUnknown) {
        issues.push({
          severity: "warning",
          message:
            "Bloc IA avec intentions : reliez la sortie « inconnu » (intent-unknown) vers un handoff ou un message utile.",
          nodeId: n.id,
        });
      }
      const maxC = Number(n.data?.maxClarifyAttempts);
      if (maxC === 1) {
        issues.push({
          severity: "warning",
          message:
            "Pour du langage naturel, augmentez le nombre max de précisions (ex. 2–4) avant la branche « inconnu ».",
          nodeId: n.id,
        });
      }
    }
  }

  return issues;
}

function nodeTypeLabel(type) {
  const labels = {
    start: "Déclencheur",
    sendText: "Texte",
    sendTemplate: "Template",
    gemini: "Gemini",
    interactiveNode: "Interactif",
    routerNode: "Routeur",
    handoffNode: "Handoff",
    delayNode: "Délai",
    waitUntilNode: "Jusqu'à date",
    timeWindowNode: "Fenêtre horaire",
    logicNode: "Logique",
  };
  return labels[type] || type || "?";
}
