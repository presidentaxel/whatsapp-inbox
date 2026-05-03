import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import {
  FiPlus, FiSend, FiTrash2, FiCheckCircle, FiCircle, FiLoader,
  FiX, FiCopy, FiCheck, FiMessageSquare, FiGitBranch, FiFileText,
  FiCpu, FiGrid, FiClock, FiShuffle, FiArrowRight, FiLogOut,
  FiCalendar, FiStar,
} from "react-icons/fi";
import {
  createPlaygroundAssistThread,
  deletePlaygroundAssistThread,
  listPlaygroundAssistThreads,
  postPlaygroundAssistant,
  updatePlaygroundAssistThread,
} from "../../api/playgroundFlowsApi";
import {
  ASSIST_PROGRESS_SHAPE_EXP,
  getExpectedAssistDurationMs,
  recordAssistDuration,
} from "./playgroundAssistTiming.js";
import { summarizeWaitUntilCanvas } from "./nodeShared";

const ASSIST_MODE_KEY = "whatsapp-inbox.playground-assist-mode";

function readStoredMode() {
  try {
    const v = localStorage.getItem(ASSIST_MODE_KEY);
    if (v === "ask" || v === "agent") return v;
  } catch {
    /* ignore */
  }
  return "agent";
}

const QUICK_STARTERS = [
  { icon: <FiMessageSquare aria-hidden />, label: "Répondre Bonjour", text: "Quand quelqu'un envoie un message, réponds \"Bonjour\"" },
  { icon: <FiGitBranch aria-hidden />, label: "Salut\u2192Salut sinon Bonjour", text: "Si la personne dit \"salut\" réponds \"salut\", sinon réponds \"Bonjour\"" },
  { icon: <FiFileText aria-hidden />, label: "Qualifier un lead", text: "Demande au contact s'il est indépendant ou en société avec des boutons, puis envoie un message adapté selon sa réponse" },
  { icon: <FiCpu aria-hidden />, label: "Accueil + Gemini", text: "Envoie un message de bienvenue puis laisse Gemini répondre aux questions du client" },
];

function graphSummary(graph) {
  if (!graph?.nodes?.length) return null;
  const nodes = graph.nodes;
  const counts = {};
  const labels = {
    start: "entrée", sendText: "message", sendTemplate: "template",
    gemini: "Gemini", interactiveNode: "interactif", routerNode: "routeur",
    handoffNode: "handoff", delayNode: "délai", waitUntilNode: "attente",
    timeWindowNode: "fenêtre horaire", logicNode: "logique",
  };
  for (const n of nodes) {
    const t = n.type || "?";
    counts[t] = (counts[t] || 0) + 1;
  }
  const parts = Object.entries(counts).map(
    ([t, c]) => `${c} ${labels[t] || t}`
  );
  const edgeCount = graph.edges?.length || 0;
  return `${nodes.length} nœud${nodes.length > 1 ? "s" : ""} (${parts.join(", ")}) · ${edgeCount} lien${edgeCount !== 1 ? "s" : ""}`;
}

/** Bulle d'attente : phrases plus longues, rotation lente, humour tech (pas de vraies étapes). */
const ASSIST_WAIT_ROTATION_MS = 5800;

const ASSIST_WAITING_THOUGHTS = [
  "Je parcours ton graphe comme on relit un mail à 23 h avant de cliquer « Envoyer » - sauf que là, c'est un POST vers un modèle qui fait semblant d'avoir lu toute ta vie professionnelle.",
  "Négociation en cours avec le tokenizer : il refuse catégoriquement d'ajouter un emoji licorne dans le JSON de réponse. On avance quand même, mais le débat est houleux.",
  "Si c'est lent, c'est peut‑être que le modèle débat intérieurement sur le sens existentiel du nœud handoff. Ou alors c'est juste du réseau. Les deux se valent sur le plan poétique.",
  "Étape actuelle : prétendre avec conviction que je maîtrise la différence entre un routerNode et un routeur Cisco. (Spoiler : l'un route des intentions, l'autre route des paquets - merci, j'ai révisé sur Wikipédia en 2009.)",
  "Je vérifie que ton JSON n'a pas attrapé le variant « virgule fantôme » ou le classique guillemet mal échappé. C'est comme du lint, mais avec plus de drama et moins de café.",
  "Cold start du cluster… ah non, pardon, c'est un simple appel HTTP. J'ai toujours rêvé de dire « cold start » devant quelqu'un qui paye l'infra.",
  "Barre de progression imaginaire : ████████░░ 82 % - les 18 % restants, c'est la part « on sait pas trop mais ça rassure l'utilisateur ».",
  "J'aligne les handles source/target dans ma tête pour ne pas confondre avec un bug produit. Parce que si je dis « c'est la faute du front », quelqu'un, quelque part, reçoit une notification Slack.",
  "Patience : Gemini ingère un prompt qui fait probablement la taille d'une nouvelle de science‑fiction. La fin est meilleure que celle de Lost, promis (clause de non‑garantie légale).",
  "En attendant, je refactorise mentalement ton parcours en microservices. Non, je ne le ferai pas vraiment - c'est juste un coping mechanism hérité de 2017.",
  "Si tu vois cette phrase trop longtemps, ce n'est pas un bug, c'est du « temps utilisateur perçu ». En vrai si ça dépasse deux éons, vérifie ta connexion ou sacrifie un câble Ethernet au dieu des timeouts.",
  "Je compile le graphe… conceptuellement. Personne ne compile du JSON, arrêtez de me regarder comme ça, je suis déjà assez fragile.",
  "Synchronisation avec le nuage de pensée™ - marque déposée par le marketing. Techniquement c'est une file d'attente et des GPUs qui chauffent un datacenter quelque part en Europe.",
  "Stack overflow imminent… non, je rigole. Enfin, sauf si tu as vraiment mis 400 nœuds. Là je ne garantis ni le JSON ni mon état mental.",
  "Je rédige une réponse qui a l'air intelligente tout en restant compatible avec la politique « pas de hallucination sur ton numéro de TVA ». C'est un équilibre, comme tenir un monoroue sur un câble RJ45.",
];

function makeAutoThreadTitle() {
  return new Intl.DateTimeFormat("fr", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date());
}

/** Titre dérivé du premier message utilisateur (liste déroulante). */
function titleFromFirstUserMessage(text) {
  const line = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!line) return `Discussion · ${makeAutoThreadTitle()}`;
  const max = 52;
  if (line.length <= max) return line;
  return `${line.slice(0, max - 1).trim()}…`;
}

/** Affichage bulle assistant : pas de JSON brut si le modèle a mélangé reply et graphe. */
function assistantBubbleText(raw) {
  const s = String(raw ?? "").trim();
  if (!s) return "";
  if (s.startsWith("{") && s.includes('"reply"')) {
    try {
      const j = JSON.parse(s);
      if (j && typeof j.reply === "string" && j.reply.trim()) return j.reply.trim();
    } catch {
      /* ignore */
    }
  }
  return s;
}

function normalizeThread(row) {
  if (!row?.id) return null;
  return {
    id: row.id,
    title: (row.title || "Nouvelle discussion").trim() || "Nouvelle discussion",
    messages: Array.isArray(row.messages) ? row.messages : [],
  };
}

const TODO_STATUS_ICON = {
  done: <FiCheckCircle className="assist-todo__icon assist-todo__icon--done" />,
  in_progress: <FiLoader className="assist-todo__icon assist-todo__icon--progress" />,
  pending: <FiCircle className="assist-todo__icon assist-todo__icon--pending" />,
};

function AssistTodoList({ items }) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return (
    <ul className="assist-todo">
      {items.map((it, idx) => {
        const row = typeof it === "string" ? { id: `s${idx}`, label: it, status: "pending" } : it;
        const status = row?.status || "pending";
        const label = row?.label != null ? String(row.label) : String(row?.id ?? idx);
        return (
          <li
            key={row?.id || `${label}-${idx}`}
            className={`assist-todo__item assist-todo__item--${status}`}
          >
            {TODO_STATUS_ICON[status] || TODO_STATUS_ICON.pending}
            <span className="assist-todo__label">{label}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Résumé lisible des tool_calls en attente de confirmation (ex. création template Meta). */
function summarizePendingTemplateCalls(calls) {
  if (!Array.isArray(calls) || !calls.length) return "";
  return calls
    .map((tc) => {
      const name = tc.skill || tc.name || "outil";
      const args = tc.args || tc.arguments || {};
      if (name === "create_template") {
        const n = args.name || "?";
        const cat = args.category || "?";
        const lang = args.language ? `, langue ${args.language}` : "";
        return `Créer le template « ${n} » (${cat}${lang})`;
      }
      return String(name);
    })
    .join(" · ");
}

function isTodoDone(status) {
  return status === "done" || status === "completed";
}

function pickNextTodoItem(items) {
  if (!Array.isArray(items) || items.length === 0) return null;
  const inProgress = items.find((it) => !isTodoDone(it?.status) && it?.status === "in_progress");
  if (inProgress) return inProgress;
  return items.find((it) => !isTodoDone(it?.status)) || null;
}

function buildInternalTodoStepPrompt(todoItems) {
  const next = pickNextTodoItem(todoItems);
  if (!next) return null;
  const steps = todoItems
    .map((it, idx) => {
      const label = it?.label != null ? String(it.label).trim() : `Étape ${idx + 1}`;
      const status = it?.status || "pending";
      const id = it?.id != null ? String(it.id) : String(idx + 1);
      return `${idx + 1}. [${status}] (${id}) ${label}`;
    })
    .join("\n");
  const nextLabel = next?.label != null ? String(next.label).trim() : "Étape en cours";
  const nextId = next?.id != null ? String(next.id) : "?";
  return `[Tour interne d'exécution TODO - ne pas mentionner ce préfixe dans la réponse visible]
Exécute MAINTENANT l'étape (${nextId}) "${nextLabel}" sur le graphe.
Contraintes:
- Mets cette étape à done si terminée, puis passe la suivante à in_progress.
- Garde le todo complet.
- Réponds avec un JSON valide (reply, graph, todo, tool_calls).
- Ne traite pas tout le plan d'un coup: priorité à l'étape (${nextId}) pour ce tour.

Plan courant:
${steps}`;
}

const NODE_TYPE_ICON = {
  start: <FiStar className="gi-icon" />,
  sendText: <FiMessageSquare className="gi-icon" />,
  sendTemplate: <FiFileText className="gi-icon" />,
  gemini: <FiCpu className="gi-icon" />,
  interactiveNode: <FiGrid className="gi-icon" />,
  routerNode: <FiGitBranch className="gi-icon" />,
  handoffNode: <FiLogOut className="gi-icon" />,
  delayNode: <FiClock className="gi-icon" />,
  waitUntilNode: <FiCalendar className="gi-icon" />,
  timeWindowNode: <FiCalendar className="gi-icon" />,
  logicNode: <FiShuffle className="gi-icon" />,
};

function nodeLogicLine(node) {
  const d = node.data || {};
  const t = node.type;
  if (t === "start") {
    const trigger = d.triggerType === "audience" ? "Audience" : "Message entrant";
    const match = d.messageMatch === "any" ? "tout message" : `${d.messageMatch}: "${d.messageKeyword || ""}"`;
    return d.triggerType === "audience" ? trigger : `${trigger} (${match})`;
  }
  if (t === "sendText") return `Envoie: "${(d.body || "").slice(0, 60)}${(d.body || "").length > 60 ? "\u2026" : ""}"`;
  if (t === "sendTemplate") {
    const st = d.templateStatus || "unknown";
    const stLabel =
      {
        unknown: "état ?",
        missing: "absent Meta",
        pending_review: "en revue Meta",
        approved: "approuvé",
        rejected: "rejeté",
      }[st] || st;
    const nQr = Array.isArray(d.quickReplyButtons) ? d.quickReplyButtons.length : 0;
    const qrHint = nQr ? ` · ${nQr} rép. rapide` : "";
    return `Template: ${d.templateName || "(non d\u00e9fini)"} · ${stLabel}${qrHint}`;
  }
  if (t === "gemini") {
    const intents = Array.isArray(d.intents) && d.intents.length;
    return intents ? `Gemini (${d.intents.length} intents)` : `Gemini \u2192 {{${d.varKey || "?"}}}`;
  }
  if (t === "interactiveNode") {
    const choices = Array.isArray(d.choices) ? d.choices.map((c) => c.title).join(", ") : "";
    return `${d.uiKind === "list" ? "Liste" : "Boutons"}: ${choices || "(vide)"}`;
  }
  if (t === "routerNode") {
    const routes = Array.isArray(d.routes) ? d.routes.map((r) => r.label).join(", ") : "";
    return `Routes: ${routes || "(vide)"} + \u00e9chappement`;
  }
  if (t === "handoffNode") return `Transfert${d.assignAgent ? ` \u2192 ${d.assignAgent}` : ""}${d.internalMessage ? ` (note: ${d.internalMessage.slice(0, 40)})` : ""}`;
  if (t === "delayNode") return `D\u00e9lai: ${d.duration || "?"}${d.unit || "s"}`;
  if (t === "logicNode") return `Condition (${d.logicMode || "si"})`;
  if (t === "timeWindowNode") return `Fen\u00eatre: ${d.startTime || "?"}-${d.endTime || "?"}`;
  if (t === "waitUntilNode") return `Attendre: ${summarizeWaitUntilCanvas(d)}`;
  return t;
}

function buildFlowDescription(graph) {
  if (!graph?.nodes?.length) return [];
  const nodes = graph.nodes;
  const edges = graph.edges || [];
  const edgeMap = {};
  for (const e of edges) {
    if (!edgeMap[e.source]) edgeMap[e.source] = [];
    edgeMap[e.source].push(e);
  }
  return nodes.map((n) => {
    const outEdges = edgeMap[n.id] || [];
    const targets = outEdges.map((e) => {
      const targetNode = nodes.find((x) => x.id === e.target);
      const handle = e.sourceHandle ? ` [${e.sourceHandle}]` : "";
      return targetNode ? `${targetNode.data?.label || targetNode.type}${handle}` : "?";
    });
    return { id: n.id, type: n.type, logic: nodeLogicLine(n), targets };
  });
}

function GraphInspectorPopup({ graph, onClose }) {
  const [tab, setTab] = useState("logic");
  const [copied, setCopied] = useState(false);
  const popupRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (popupRef.current && !popupRef.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const flowDesc = useMemo(() => buildFlowDescription(graph), [graph]);
  const jsonStr = useMemo(() => JSON.stringify(graph, null, 2), [graph]);

  const copyJson = useCallback(() => {
    navigator.clipboard.writeText(jsonStr).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [jsonStr]);

  return (
    <div className="gi-overlay">
      <div className="gi-popup" ref={popupRef}>
        <div className="gi-header">
          <div className="gi-tabs">
            <button
              type="button"
              className={`gi-tab ${tab === "logic" ? "gi-tab--active" : ""}`}
              onClick={() => setTab("logic")}
            >
              Logique
            </button>
            <button
              type="button"
              className={`gi-tab ${tab === "json" ? "gi-tab--active" : ""}`}
              onClick={() => setTab("json")}
            >
              JSON
            </button>
          </div>
          <button type="button" className="gi-close" onClick={onClose} aria-label="Fermer">
            <FiX />
          </button>
        </div>
        <div className="gi-body">
          {tab === "logic" ? (
            <ul className="gi-logic-list">
              {flowDesc.map((item) => (
                <li key={item.id} className="gi-logic-item">
                  <div className="gi-logic-node">
                    {NODE_TYPE_ICON[item.type] || <FiCircle className="gi-icon" />}
                    <span className="gi-logic-type">{item.type}</span>
                    <span className="gi-logic-desc">{item.logic}</span>
                  </div>
                  {item.targets.length > 0 && (
                    <div className="gi-logic-edges">
                      {item.targets.map((t, j) => (
                        <span key={j} className="gi-logic-edge">
                          <FiArrowRight className="gi-icon gi-icon--sm" /> {t}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <div className="gi-json-wrap">
              <button type="button" className="gi-copy" onClick={copyJson}>
                {copied ? <><FiCheck /> Copié</> : <><FiCopy /> Copier</>}
              </button>
              <pre className="gi-json">{jsonStr}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const SKILL_LABELS = {
  list_templates: "Consulté les templates",
  get_template_status: "Vérifié un statut template",
  create_template: "Créé un template",
  list_broadcast_groups: "Consulté les groupes",
};

function SkillBadges({ skills }) {
  if (!Array.isArray(skills) || skills.length === 0) return null;
  const unique = [...new Set(skills)];
  return (
    <div className="assist-skills">
      {unique.map((sk) => (
        <span key={sk} className="assist-skills__badge">
          {SKILL_LABELS[sk] || sk}
        </span>
      ))}
    </div>
  );
}

export default function PlaygroundAssistantChat({
  accountId,
  flowId,
  flowName,
  disabled,
  getGraphSnapshot,
  onApplyGraph,
}) {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [assistMode, setAssistMode] = useState(readStoredMode);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [loadState, setLoadState] = useState("idle");
  const [waitingThoughtIdx, setWaitingThoughtIdx] = useState(0);
  const [inspectGraph, setInspectGraph] = useState(null);
  const listEndRef = useRef(null);
  /** Mode effectif du tour en cours (bulle « en train d'écrire » + cohérence avec sendMessage). */
  const sendingModeRef = useRef(assistMode);
  /** Longueur du dernier message utilisateur envoyé à l’API (estimation durée barre). */
  const lastAssistPromptLengthRef = useRef(0);
  const [assistProgressPct, setAssistProgressPct] = useState(0);
  /** Annulation du tour assistant en cours (requête HTTP). */
  const assistAbortRef = useRef(null);

  const stopAssistInFlight = useCallback(() => {
    assistAbortRef.current?.abort();
  }, []);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  useEffect(() => {
    try {
      localStorage.setItem(ASSIST_MODE_KEY, assistMode);
    } catch {
      /* ignore */
    }
  }, [assistMode]);

  const loadVisibleThreads = useCallback(async () => {
    if (!accountId || !flowId) return;
    setLoadState("loading");
    setError(null);
    try {
      const res = await listPlaygroundAssistThreads({
        accountId,
        flowId,
        archived: false,
      });
      let list = (res.data || []).map(normalizeThread).filter(Boolean);
      if (!list.length) {
        const cr = await createPlaygroundAssistThread({
          account_id: accountId,
          flow_id: flowId,
          title: `Discussion · ${makeAutoThreadTitle()}`,
          messages: [],
        });
        const t = normalizeThread(cr.data);
        if (t) list = [t];
      }
      setSessions(list);
      setActiveSessionId((prev) => {
        if (prev && list.some((s) => s.id === prev)) return prev;
        return list[0]?.id ?? null;
      });
      setLoadState("idle");
    } catch (err) {
      console.error(err);
      setLoadState("error");
      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Impossible de charger les discussions."
      );
    }
  }, [accountId, flowId]);

  useEffect(() => {
    if (!accountId || !flowId) {
      setSessions([]);
      setActiveSessionId(null);
      setLoadState("idle");
      return;
    }
    void loadVisibleThreads();
  }, [accountId, flowId, loadVisibleThreads]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages, sending, waitingThoughtIdx]);

  useEffect(() => {
    if (!sending) return;
    setWaitingThoughtIdx(
      Math.floor(Math.random() * ASSIST_WAITING_THOUGHTS.length)
    );
    const id = window.setInterval(() => {
      setWaitingThoughtIdx((i) => (i + 1) % ASSIST_WAITING_THOUGHTS.length);
    }, ASSIST_WAIT_ROTATION_MS);
    return () => window.clearInterval(id);
  }, [sending]);

  /** Barre de progression : pourcentage ≈ temps écoulé / durée attendue (plafonné à 99 % jusqu’à la réponse). */
  useEffect(() => {
    if (!sending) {
      setAssistProgressPct(0);
      return;
    }
    let snapshot = { nodes: [], edges: [], v: 2 };
    try {
      snapshot = getGraphSnapshot?.() ?? snapshot;
    } catch {
      /* ignore */
    }
    let graphBytes = 0;
    try {
      graphBytes = new Blob([JSON.stringify(snapshot)]).size;
    } catch {
      graphBytes = 0;
    }
    const mode = sendingModeRef.current === "agent" ? "agent" : "ask";
    const expectedMs = getExpectedAssistDurationMs(mode, {
      userTextLength: Math.max(1, lastAssistPromptLengthRef.current || 1),
      graphJsonBytes: graphBytes,
      nodeCount: (snapshot.nodes || []).length,
    });
    const t0 = performance.now();
    const tick = () => {
      const elapsed = performance.now() - t0;
      const linear = Math.min(1, elapsed / expectedMs);
      const shaped = Math.pow(linear, ASSIST_PROGRESS_SHAPE_EXP);
      const pct = Math.min(99, Math.max(0, Math.floor(shaped * 100)));
      setAssistProgressPct(pct);
    };
    tick();
    const intervalId = window.setInterval(tick, 80);
    return () => {
      window.clearInterval(intervalId);
      setAssistProgressPct(0);
    };
  }, [sending, getGraphSnapshot]);

  const persistMessages = useCallback(async (threadId, messages) => {
    await updatePlaygroundAssistThread(threadId, { messages });
  }, []);

  const startNewChat = useCallback(async () => {
    if (!accountId || !flowId || disabled) return;
    setError(null);
    try {
      const cr = await createPlaygroundAssistThread({
        account_id: accountId,
        flow_id: flowId,
        title: `Discussion · ${makeAutoThreadTitle()}`,
        messages: [],
      });
      const t = normalizeThread(cr.data);
      if (!t) return;
      setSessions((prev) => [t, ...prev]);
      setActiveSessionId(t.id);
    } catch (e) {
      console.error(e);
      setError("Impossible de créer une discussion.");
    }
  }, [accountId, flowId, disabled]);

  const removeThread = useCallback(async () => {
    if (!activeSessionId || disabled) return;
    if (
      !window.confirm(
        "Retirer cette discussion de la liste ? Elle reste en base (récupérable dans Archives)."
      )
    ) {
      return;
    }
    try {
      await deletePlaygroundAssistThread(activeSessionId);
      await loadVisibleThreads();
    } catch (e) {
      console.error(e);
      setError("Impossible de masquer la discussion.");
    }
  }, [activeSessionId, disabled, loadVisibleThreads]);

  const updateSessionMessages = useCallback((sessionId, updater) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sessionId ? { ...s, messages: updater(s.messages) } : s
      )
    );
  }, []);

  const runPlaygroundAssistRound = useCallback(
    async ({
      requestMode,
      threadForState,
      apiMessages,
      approve_tool_calls,
      clearPendingAtIndex,
      execution_phase,
    }) => {
      const sid = activeSessionId;
      if (!sid) return null;

      setError(null);
      sendingModeRef.current = requestMode;
      const lastUser = [...apiMessages].reverse().find((m) => m.role === "user");
      lastAssistPromptLengthRef.current = Math.max(
        1,
        String(lastUser?.content || "").length
      );
      const roundStartMs = Date.now();
      const ac = new AbortController();
      assistAbortRef.current = ac;
      setSending(true);

      let snapshot;
      try {
        snapshot = getGraphSnapshot?.() ?? { nodes: [], edges: [], v: 2 };
      } catch (e) {
        console.error(e);
        snapshot = { nodes: [], edges: [], v: 2 };
      }

      const canvasWasEmpty = (() => {
        try {
          const real = (snapshot.nodes || []).filter((n) => n.type !== "start");
          return real.length === 0;
        } catch {
          return true;
        }
      })();

      try {
        const body = {
          account_id: accountId,
          flow_id: flowId,
          flow_name: flowName || "",
          graph: snapshot,
          messages: apiMessages,
          mode: requestMode,
        };
        if (execution_phase) {
          body.execution_phase = execution_phase;
        }
        if (approve_tool_calls?.length) {
          body.approve_tool_calls = approve_tool_calls;
        }
        const res = await postPlaygroundAssistant(body, { signal: ac.signal });
        const reply = res.data?.reply ?? "";
        let graph = res.data?.graph ?? null;
        let todo = res.data?.todo;
        const priorTodo = [...threadForState]
          .reverse()
          .find(
            (m) => m.role === "assistant" && Array.isArray(m.todo) && m.todo.length > 0
          )?.todo;
        if (todo === undefined || todo === null) {
          todo = priorTodo ?? null;
        } else if (Array.isArray(todo) && todo.length === 0) {
          todo = null;
        }

        const skillsUsed = res.data?.skills_used ?? null;
        const pendingToolCalls =
          Array.isArray(res.data?.pending_tool_calls) && res.data.pending_tool_calls.length > 0
            ? res.data.pending_tool_calls
            : null;

        if (requestMode === "ask") {
          graph = null;
        }

        let autoApplied = false;
        if (graph && canvasWasEmpty && requestMode === "agent") {
          try {
            onApplyGraph?.(graph);
            autoApplied = true;
          } catch (e) {
            console.error(e);
          }
        }

        const baseThread =
          clearPendingAtIndex == null
            ? threadForState
            : threadForState.map((m, i) =>
                i === clearPendingAtIndex ? { ...m, pendingToolCalls: null } : m
              );

        const withAssistant = [
          ...baseThread,
          {
            role: "assistant",
            content: reply,
            sourceMode: requestMode,
            proposedGraph: autoApplied ? null : graph || null,
            appliedGraph: autoApplied ? graph : null,
            todo: todo || null,
            skillsUsed: skillsUsed || null,
            pendingToolCalls,
          },
        ];
        updateSessionMessages(sid, () => withAssistant);
        try {
          await persistMessages(sid, withAssistant);
        } catch (e) {
          console.error(e);
        }
        return {
          messages: withAssistant,
          todo: todo || null,
          pendingToolCalls,
          aborted: false,
        };
      } catch (err) {
        const canceled =
          (typeof axios.isCancel === "function" && axios.isCancel(err)) ||
          err?.code === "ERR_CANCELED" ||
          err?.name === "CanceledError";
        if (canceled) {
          setError(null);
          const abortedThread = [
            ...threadForState,
            {
              role: "assistant",
              content: "Génération interrompue.",
              proposedGraph: null,
              sourceMode: requestMode,
            },
          ];
          updateSessionMessages(sid, () => abortedThread);
          try {
            await persistMessages(sid, abortedThread);
          } catch (e) {
            console.error(e);
          }
          return {
            messages: abortedThread,
            todo: null,
            pendingToolCalls: null,
            aborted: true,
          };
        }
        const detail =
          err?.response?.data?.detail ||
          err?.message ||
          "Erreur réseau ou serveur.";
        setError(typeof detail === "string" ? detail : JSON.stringify(detail));
        const errReply = [
          ...threadForState,
          {
            role: "assistant",
            content: `Désolé, une erreur s'est produite : ${typeof detail === "string" ? detail : "erreur"}.`,
            proposedGraph: null,
            sourceMode: requestMode,
          },
        ];
        updateSessionMessages(sid, () => errReply);
        try {
          await persistMessages(sid, errReply);
        } catch (e) {
          console.error(e);
        }
        return {
          messages: errReply,
          todo: null,
          pendingToolCalls: null,
          aborted: false,
        };
      } finally {
        try {
          recordAssistDuration(requestMode, Date.now() - roundStartMs);
        } catch {
          /* ignore */
        }
        assistAbortRef.current = null;
        setSending(false);
      }
    },
    [
      activeSessionId,
      accountId,
      flowId,
      flowName,
      getGraphSnapshot,
      onApplyGraph,
      updateSessionMessages,
      persistMessages,
    ]
  );

  const autoAdvanceTodoPlan = useCallback(
    async ({ requestMode, startMessages, initialTodo }) => {
      if (requestMode !== "agent") return;
      let currentMessages = Array.isArray(startMessages) ? startMessages : [];
      let currentTodo = Array.isArray(initialTodo) ? initialTodo : null;
      if (!currentTodo || currentTodo.length === 0) return;

      const MAX_INTERNAL_STEPS = 5;
      for (let i = 0; i < MAX_INTERNAL_STEPS; i += 1) {
        const next = pickNextTodoItem(currentTodo);
        if (!next) break;
        const hiddenPrompt = buildInternalTodoStepPrompt(currentTodo);
        if (!hiddenPrompt) break;
        const apiMessages = [
          ...currentMessages.map(({ role, content }) => ({ role, content })),
          { role: "user", content: hiddenPrompt },
        ];
        const res = await runPlaygroundAssistRound({
          requestMode: "agent",
          threadForState: currentMessages,
          apiMessages,
          approve_tool_calls: null,
          clearPendingAtIndex: null,
          execution_phase: "execute_step",
        });
        if (!res?.messages || res.aborted) break;
        currentMessages = res.messages;
        currentTodo = Array.isArray(res.todo) ? res.todo : null;
        if (!currentTodo || currentTodo.length === 0) break;
        if (Array.isArray(res.pendingToolCalls) && res.pendingToolCalls.length > 0) break;
      }
    },
    [runPlaygroundAssistRound]
  );

  const sendMessage = useCallback(
    async (rawText, requestMode) => {
      const text = String(rawText || "").trim();
      if (!text || !accountId || !flowId || disabled || sending || loadState !== "idle") return;
      const sid = activeSessionId;
      if (!sid) return;

      const session = sessions.find((s) => s.id === sid);
      const userMsg = { role: "user", content: text, sourceMode: requestMode };
      const isFirstUserMessage = (session?.messages || []).length === 0;
      const nextAfterUser = [...(session?.messages || []), userMsg];
      updateSessionMessages(sid, () => nextAfterUser);

      try {
        await persistMessages(sid, nextAfterUser);
      } catch (e) {
        console.error(e);
      }

      if (isFirstUserMessage) {
        const autoTitle = titleFromFirstUserMessage(text);
        try {
          await updatePlaygroundAssistThread(sid, { title: autoTitle });
          setSessions((prev) =>
            prev.map((s) => (s.id === sid ? { ...s, title: autoTitle } : s))
          );
        } catch (e) {
          console.error(e);
        }
      }

      const apiMessages = nextAfterUser.map(({ role, content }) => ({
        role,
        content,
      }));

      const firstRound = await runPlaygroundAssistRound({
        requestMode,
        threadForState: nextAfterUser,
        apiMessages,
        approve_tool_calls: null,
        clearPendingAtIndex: null,
        execution_phase: requestMode === "agent" ? "plan" : null,
      });
      if (firstRound?.aborted) return;
      if (firstRound?.messages && Array.isArray(firstRound?.todo)) {
        await autoAdvanceTodoPlan({
          requestMode,
          startMessages: firstRound.messages,
          initialTodo: firstRound.todo,
        });
      }
    },
    [
      accountId,
      flowId,
      disabled,
      sending,
      loadState,
      activeSessionId,
      sessions,
      updateSessionMessages,
      persistMessages,
      runPlaygroundAssistRound,
      autoAdvanceTodoPlan,
    ]
  );

  const confirmPendingTemplateCalls = useCallback(
    async (messageIndex, calls) => {
      if (!activeSessionId || disabled || sending || loadState !== "idle") return;
      const session = sessions.find((s) => s.id === activeSessionId);
      if (!session || !Array.isArray(calls) || !calls.length) return;
      const apiMessages = session.messages.map(({ role, content }) => ({
        role,
        content,
      }));
      const afterApprove = await runPlaygroundAssistRound({
        requestMode: assistMode,
        threadForState: session.messages,
        apiMessages,
        approve_tool_calls: calls,
        clearPendingAtIndex: messageIndex,
        execution_phase: assistMode === "agent" ? "execute_step" : null,
      });
      if (afterApprove?.aborted) return;
      if (afterApprove?.messages && Array.isArray(afterApprove?.todo)) {
        await autoAdvanceTodoPlan({
          requestMode: assistMode,
          startMessages: afterApprove.messages,
          initialTodo: afterApprove.todo,
        });
      }
    },
    [
      activeSessionId,
      assistMode,
      disabled,
      sending,
      loadState,
      sessions,
      updateSessionMessages,
      persistMessages,
      runPlaygroundAssistRound,
      autoAdvanceTodoPlan,
    ]
  );

  const rejectPendingTemplateCalls = useCallback(
    (messageIndex) => {
      if (!activeSessionId) return;
      const session = sessions.find((s) => s.id === activeSessionId);
      if (!session) return;
      const cleared = session.messages.map((m, i) =>
        i === messageIndex ? { ...m, pendingToolCalls: null } : m
      );
      updateSessionMessages(activeSessionId, () => cleared);
      void persistMessages(activeSessionId, cleared);
    },
    [activeSessionId, sessions, updateSessionMessages, persistMessages]
  );

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || !accountId || !flowId || disabled || sending || loadState !== "idle") return;
    setDraft("");
    await sendMessage(text, assistMode);
  }, [draft, accountId, flowId, disabled, sending, loadState, assistMode, sendMessage]);

  const continuePlanInAgent = useCallback(
    async (todoItems) => {
      if (!activeSessionId || !accountId || !flowId || disabled || sending || loadState !== "idle") {
        return;
      }
      const session = sessions.find((s) => s.id === activeSessionId);
      if (!session) return;

      const list = Array.isArray(todoItems) ? todoItems : [];
      const lines = list
        .map((it, i) => {
          if (typeof it === "string") return `${i + 1}. ${it}`;
          const label = it?.label != null ? String(it.label).trim() : "";
          if (label) return `${i + 1}. ${label}`;
          return `${i + 1}. (${it?.id ?? "étape"})`;
        })
        .join("\n");
      /** Invisible dans le fil : seul l’API Gemini voit ce message (continuité UX type Composer). */
      const hiddenUserTurn = lines
        ? `[Passage mode Agent - tour utilisateur interne, ne pas citer ce préfixe dans ta réponse visible]\n`
          + `L’utilisateur a enchaîné en mode Agent sans nouveau message affiché. Implémente le plan sur le graphe (JSON React Flow v=2). `
          + `Conserve et mets à jour la même todo (statuts) dans ton JSON de réponse.\n\nPlan :\n${lines}`
        : `[Passage mode Agent - tour utilisateur interne, ne pas citer ce préfixe dans ta réponse visible]\n`
          + `L’utilisateur a enchaîné en mode Agent sans nouveau message affiché. Implémente sur le graphe ce qui a été convenu dans l’historique (v=2). `
          + `Conserve et mets à jour la todo.`;

      setAssistMode("agent");

      const apiMessages = [
        ...session.messages.map(({ role, content }) => ({ role, content })),
        { role: "user", content: hiddenUserTurn },
      ];

      const firstRound = await runPlaygroundAssistRound({
        requestMode: "agent",
        threadForState: session.messages,
        apiMessages,
        approve_tool_calls: null,
        clearPendingAtIndex: null,
        execution_phase: "plan",
      });
      if (firstRound?.aborted) return;
      if (firstRound?.messages && Array.isArray(firstRound?.todo)) {
        await autoAdvanceTodoPlan({
          requestMode: "agent",
          startMessages: firstRound.messages,
          initialTodo: firstRound.todo,
        });
      }
    },
    [
      activeSessionId,
      accountId,
      flowId,
      disabled,
      sending,
      loadState,
      sessions,
      runPlaygroundAssistRound,
      autoAdvanceTodoPlan,
    ]
  );

  const applyProposed = useCallback(
    async (msgIndex, graph) => {
      if (!graph || !activeSessionId || assistMode === "ask") return;
      try {
        onApplyGraph?.(graph);
        let nextMsgs = null;
        setSessions((prev) => {
          const s = prev.find((x) => x.id === activeSessionId);
          if (!s) return prev;
          nextMsgs = s.messages.map((m, i) =>
            i === msgIndex ? { ...m, proposedGraph: null } : m
          );
          return prev.map((x) =>
            x.id === activeSessionId ? { ...x, messages: nextMsgs } : x
          );
        });
        if (nextMsgs) await persistMessages(activeSessionId, nextMsgs);
      } catch (e) {
        console.error(e);
        setError("Impossible d'appliquer ce graphe.");
      }
    },
    [activeSessionId, assistMode, onApplyGraph, persistMessages]
  );

  const isCanvasEmpty = useMemo(() => {
    try {
      const snap = getGraphSnapshot?.();
      if (!snap) return true;
      const real = (snap.nodes || []).filter((n) => n.type !== "start");
      return real.length === 0;
    } catch {
      return true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getGraphSnapshot, activeSession?.messages]);

  const titleShort = (flowName || "Scénario").trim() || "Scénario";
  const placeholder =
    assistMode === "ask"
      ? "Pose une question sur le parcours, les nœuds ou le moteur…"
      : isCanvasEmpty
        ? "Ex : Quand on reçoit un message, réponds Bonjour"
        : "Décris une modification : ajouter un message, un routeur, un délai…";

  const showStarters =
    assistMode === "agent" &&
    isCanvasEmpty &&
    loadState === "idle" &&
    (activeSession?.messages || []).length === 0 &&
    !sending;

  const fillStarter = useCallback(
    (text) => {
      setDraft(text);
      if (assistMode !== "agent") setAssistMode("agent");
    },
    [assistMode]
  );

  if (!accountId || !flowId) {
    return null;
  }

  return (
    <aside
      className="playground-assist"
      aria-label="Assistant IA pour le scénario Playground"
    >
      <header className="playground-assist__topbar">
        <div className="playground-assist__topbar-main">
          <span className="playground-assist__eyebrow">Assistant</span>
          <h2 className="playground-assist__headline" title={titleShort}>
            {titleShort}
          </h2>
        </div>
        <div className="playground-assist__topbar-actions">
          {sessions.length > 1 ? (
            <select
              className="playground-assist__thread-select"
              value={activeSessionId || ""}
              onChange={(e) => setActiveSessionId(e.target.value)}
              disabled={disabled || loadState === "loading"}
              aria-label="Changer de discussion"
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          ) : null}
          <button
            type="button"
            className="playground-assist__icon-btn"
            onClick={() => void startNewChat()}
            disabled={disabled || loadState === "loading"}
            title="Nouvelle discussion"
            aria-label="Nouvelle discussion"
          >
            <FiPlus aria-hidden />
          </button>
          <button
            type="button"
            className="playground-assist__icon-btn playground-assist__icon-btn--danger"
            onClick={() => void removeThread()}
            disabled={disabled || loadState === "loading" || !activeSessionId}
            title="Retirer de la liste (données conservées en base)"
            aria-label="Masquer la discussion"
          >
            <FiTrash2 aria-hidden />
          </button>
        </div>
      </header>

      {sending ? (
        <div className="playground-assist__progress-row">
          <div
            className="playground-assist__progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={assistProgressPct}
            aria-label="Progression de la réponse de l’assistant"
          >
            <div className="playground-assist__progress-track">
              <div
                className="playground-assist__progress-fill"
                style={{ width: `${assistProgressPct}%` }}
              />
            </div>
            <span className="playground-assist__progress-pct">{assistProgressPct}%</span>
          </div>
          <button
            type="button"
            className="playground-assist__stop-btn"
            onClick={stopAssistInFlight}
            aria-label="Arrêter la génération"
          >
            Arrêter
          </button>
        </div>
      ) : null}

      <div className="playground-assist__thread" role="log" aria-live="polite">
        {loadState === "loading" ? (
          <p className="playground-assist__thread-hint muted">Chargement des discussions…</p>
        ) : null}
        {loadState === "error" ? (
          <div className="playground-assist__empty">
            <p className="playground-assist__empty-title">Erreur</p>
            <p className="playground-assist__empty-text">{String(error || "")}</p>
            <button
              type="button"
              className="playground-assist__retry"
              onClick={() => void loadVisibleThreads()}
            >
              Réessayer
            </button>
          </div>
        ) : null}
        {loadState === "idle" && (activeSession?.messages || []).length === 0 ? (
          <div className="playground-assist__empty">
            {showStarters ? (
              <>
                <p className="playground-assist__empty-title">Commencer un scénario</p>
                <p className="playground-assist__empty-text">
                  Choisis un exemple ou décris ce que tu veux en une phrase.
                  Le graphe sera appliqué automatiquement sur le canevas.
                </p>
                <div className="playground-assist__starters">
                  {QUICK_STARTERS.map((s) => (
                    <button
                      key={s.label}
                      type="button"
                      className="playground-assist__starter-chip"
                      onClick={() => fillStarter(s.text)}
                      disabled={disabled}
                    >
                      {s.icon} {s.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="playground-assist__empty-title">Composer</p>
                <p className="playground-assist__empty-text">
                  <strong>Ask</strong> - comprendre le flux et les limites du moteur.{" "}
                  <strong>Agent</strong> - itérer sur le graphe et appliquer une proposition sur le
                  canevas.
                </p>
              </>
            )}
          </div>
        ) : null}
        {(activeSession?.messages || []).map((m, i) => (
          <div
            key={`${i}-${m.role}`}
            className={`playground-assist__bubble playground-assist__bubble--${m.role}`}
          >
            <span className="playground-assist__bubble-label">
              {m.role === "user"
                ? "Toi"
                : (m.sourceMode ?? assistMode) === "agent"
                  ? "Agent"
                  : "Ask"}
            </span>
            <div className="playground-assist__bubble-body">
              {m.role === "assistant" ? assistantBubbleText(m.content) : m.content}
            </div>
            {m.role === "assistant" && m.skillsUsed ? (
              <SkillBadges skills={m.skillsUsed} />
            ) : null}
            {m.role === "assistant" &&
            Array.isArray(m.pendingToolCalls) &&
            m.pendingToolCalls.length > 0 ? (
              <div
                className="playground-assist__pending-tools"
                role="region"
                aria-label="Action Meta à confirmer"
              >
                <p className="playground-assist__pending-tools-title">
                  Création de template sur Meta
                </p>
                <p className="playground-assist__pending-tools-desc">
                  {summarizePendingTemplateCalls(m.pendingToolCalls)}
                </p>
                <div className="playground-assist__pending-tools-actions">
                  <button
                    type="button"
                    className="playground-assist__pending-confirm"
                    onClick={() => void confirmPendingTemplateCalls(i, m.pendingToolCalls)}
                    disabled={disabled || sending || loadState !== "idle"}
                  >
                    <FiCheck aria-hidden /> Confirmer la création
                  </button>
                  <button
                    type="button"
                    className="playground-assist__pending-reject"
                    onClick={() => rejectPendingTemplateCalls(i)}
                    disabled={disabled || sending}
                  >
                    Annuler
                  </button>
                </div>
              </div>
            ) : null}
            {m.role === "assistant" && m.todo ? (
              <AssistTodoList items={m.todo} />
            ) : null}
            {m.role === "assistant" &&
            assistMode === "ask" &&
            Array.isArray(m.todo) &&
            m.todo.length > 0 ? (
              <div className="playground-assist__bubble-actions playground-assist__bubble-actions--continue">
                <button
                  type="button"
                  className="playground-assist__continue-agent"
                  onClick={() => void continuePlanInAgent(m.todo)}
                  disabled={disabled || sending || loadState !== "idle"}
                  title="Enchaîne en mode Agent sur ce plan (aucun message intermédiaire dans le fil)"
                  aria-label="Continuer : appliquer le plan en mode Agent sans message visible dans le fil"
                >
                  <FiCpu aria-hidden /> Continuer
                </button>
              </div>
            ) : null}
            {m.role === "assistant" && m.appliedGraph ? (
              <button
                type="button"
                className="playground-assist__graph-summary playground-assist__graph-summary--clickable"
                onClick={() => setInspectGraph(m.appliedGraph)}
                title="Voir la logique et le JSON du graphe"
              >
                <FiCheckCircle className="playground-assist__graph-icon playground-assist__graph-icon--applied" />
                Appliqu{"\u00e9"} {"\u2013"} {graphSummary(m.appliedGraph) || "graphe appliqu\u00e9"}
              </button>
            ) : null}
            {m.role === "assistant" &&
            m.proposedGraph &&
            assistMode === "agent" ? (
              <div className="playground-assist__bubble-actions">
                {graphSummary(m.proposedGraph) ? (
                  <button
                    type="button"
                    className="playground-assist__graph-summary playground-assist__graph-summary--clickable"
                    onClick={() => setInspectGraph(m.proposedGraph)}
                    title="Voir la logique et le JSON du graphe"
                  >
                    {graphSummary(m.proposedGraph)}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="playground-assist__apply"
                  onClick={() => void applyProposed(i, m.proposedGraph)}
                  disabled={disabled}
                >
                  Appliquer sur le canevas
                </button>
              </div>
            ) : null}
          </div>
        ))}
        {sending ? (
          <div className="playground-assist__bubble playground-assist__bubble--assistant">
            <span className="playground-assist__bubble-label">
              {sendingModeRef.current === "agent" ? "Agent" : "Ask"}
            </span>
            <div className="playground-assist__bubble-body playground-assist__typing">
              <p
                key={waitingThoughtIdx}
                className="playground-assist__typing-thought"
              >
                {ASSIST_WAITING_THOUGHTS[waitingThoughtIdx]}
              </p>
              <div className="playground-assist__typing-footer" aria-hidden>
                <span className="playground-assist__typing-dot" />
                <span className="playground-assist__typing-dot" />
                <span className="playground-assist__typing-dot" />
              </div>
            </div>
          </div>
        ) : null}
        <div ref={listEndRef} />
      </div>

      {error && loadState === "idle" ? (
        <p className="playground-assist__banner" role="alert">
          {error}
        </p>
      ) : null}

      <footer className="playground-assist__dock">
        <div
          className="playground-assist__mode"
          role="group"
          aria-label="Mode de l'assistant"
        >
          <button
            type="button"
            className={`playground-assist__mode-btn playground-assist__mode-btn--ask ${assistMode === "ask" ? "is-active" : ""}`}
            onClick={() => setAssistMode("ask")}
          >
            Ask
          </button>
          <button
            type="button"
            className={`playground-assist__mode-btn playground-assist__mode-btn--agent ${assistMode === "agent" ? "is-active" : ""}`}
            onClick={() => setAssistMode("agent")}
          >
            Agent
          </button>
        </div>

        <div className="playground-assist__composer-box">
          <textarea
            className="playground-assist__textarea"
            rows={3}
            placeholder={placeholder}
            value={draft}
            disabled={disabled || sending || loadState !== "idle"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <div className="playground-assist__composer-meta">
            <span className="playground-assist__hint">
              Entrée envoie · Maj+Entrée nouvelle ligne
            </span>
            <button
              type="button"
              className="playground-assist__send"
              disabled={disabled || sending || !draft.trim() || loadState !== "idle"}
              onClick={() => void send()}
              title="Envoyer"
              aria-label="Envoyer"
            >
              <FiSend aria-hidden />
            </button>
          </div>
        </div>
      </footer>

      {inspectGraph ? (
        <GraphInspectorPopup
          graph={inspectGraph}
          onClose={() => setInspectGraph(null)}
        />
      ) : null}
    </aside>
  );
}
