import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiPlus, FiSend, FiTrash2 } from "react-icons/fi";
import {
  createPlaygroundAssistThread,
  deletePlaygroundAssistThread,
  listPlaygroundAssistThreads,
  postPlaygroundAssistant,
  updatePlaygroundAssistThread,
} from "../../api/playgroundFlowsApi";

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
  { label: "\u{1F44B} R\u00e9pondre Bonjour", text: "Quand quelqu'un envoie un message, r\u00e9ponds \"Bonjour\"" },
  { label: "\u{1F500} Salut\u2192Salut sinon Bonjour", text: "Si la personne dit \"salut\" r\u00e9ponds \"salut\", sinon r\u00e9ponds \"Bonjour\"" },
  { label: "\u{1F4CB} Qualifier un lead", text: "Demande au contact s'il est ind\u00e9pendant ou en soci\u00e9t\u00e9 avec des boutons, puis envoie un message adapt\u00e9 selon sa r\u00e9ponse" },
  { label: "\u{1F916} Accueil + Gemini", text: "Envoie un message de bienvenue puis laisse Gemini r\u00e9pondre aux questions du client" },
];

function graphSummary(graph) {
  if (!graph?.nodes?.length) return null;
  const nodes = graph.nodes;
  const counts = {};
  const labels = {
    start: "entr\u00e9e", sendText: "message", sendTemplate: "template",
    gemini: "Gemini", interactiveNode: "interactif", routerNode: "routeur",
    handoffNode: "handoff", delayNode: "d\u00e9lai", waitUntilNode: "attente",
    timeWindowNode: "fen\u00eatre horaire", logicNode: "logique",
  };
  for (const n of nodes) {
    const t = n.type || "?";
    counts[t] = (counts[t] || 0) + 1;
  }
  const parts = Object.entries(counts).map(
    ([t, c]) => `${c}\u00a0${labels[t] || t}`
  );
  const edgeCount = graph.edges?.length || 0;
  return `${nodes.length}\u00a0n\u0153ud${nodes.length > 1 ? "s" : ""} (${parts.join(", ")})\u00a0\u00b7\u00a0${edgeCount}\u00a0lien${edgeCount !== 1 ? "s" : ""}`;
}

/** Bulle d'attente : phrases plus longues, rotation lente, humour tech (pas de vraies \u00e9tapes). */
const ASSIST_WAIT_ROTATION_MS = 5800;

const ASSIST_WAITING_THOUGHTS = [
  "Je parcours ton graphe comme on relit un mail \u00e0 23\u00a0h avant de cliquer \u00ab\u00a0Envoyer\u00a0\u00bb - sauf que l\u00e0, c'est un POST vers un mod\u00e8le qui fait semblant d'avoir lu toute ta vie professionnelle.",
  "N\u00e9gociation en cours avec le tokenizer : il refuse cat\u00e9goriquement d'ajouter un emoji licorne dans le JSON de r\u00e9ponse. On avance quand m\u00eame, mais le d\u00e9bat est houleux.",
  "Si c'est lent, c'est peut\u2011\u00eatre que le mod\u00e8le d\u00e9bat int\u00e9rieurement sur le sens existentiel du n\u0153ud handoff. Ou alors c'est juste du r\u00e9seau. Les deux se valent sur le plan po\u00e9tique.",
  "\u00c9tape actuelle : pr\u00e9tendre avec conviction que je ma\u00eetrise la diff\u00e9rence entre un routerNode et un routeur Cisco. (Spoiler : l'un route des intentions, l'autre route des paquets - merci, j'ai r\u00e9vis\u00e9 sur Wikip\u00e9dia en 2009.)",
  "Je v\u00e9rifie que ton JSON n'a pas attrap\u00e9 le variant \u00ab\u00a0virgule fant\u00f4me\u00a0\u00bb ou le classique guillemet mal \u00e9chapp\u00e9. C'est comme du lint, mais avec plus de drama et moins de caf\u00e9.",
  "Cold start du cluster\u2026 ah non, pardon, c'est un simple appel HTTP. J'ai toujours r\u00eav\u00e9 de dire \u00ab\u00a0cold start\u00a0\u00bb devant quelqu'un qui paye l'infra.",
  "Barre de progression imaginaire : \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591 82\u00a0% - les 18\u00a0% restants, c'est la part \u00ab\u00a0on sait pas trop mais \u00e7a rassure l'utilisateur\u00a0\u00bb.",
  "J'aligne les handles source/target dans ma t\u00eate pour ne pas confondre avec un bug produit. Parce que si je dis \u00ab\u00a0c'est la faute du front\u00a0\u00bb, quelqu'un, quelque part, re\u00e7oit une notification Slack.",
  "Patience : Gemini ing\u00e8re un prompt qui fait probablement la taille d'une nouvelle de science\u2011fiction. La fin est meilleure que celle de Lost, promis (clause de non\u2011garantie l\u00e9gale).",
  "En attendant, je refactorise mentalement ton parcours en microservices. Non, je ne le ferai pas vraiment - c'est juste un coping mechanism h\u00e9rit\u00e9 de 2017.",
  "Si tu vois cette phrase trop longtemps, ce n'est pas un bug, c'est du \u00ab\u00a0temps utilisateur per\u00e7u\u00a0\u00bb. En vrai si \u00e7a d\u00e9passe deux \u00e9ons, v\u00e9rifie ta connexion ou sacrifie un c\u00e2ble Ethernet au dieu des timeouts.",
  "Je compile le graphe\u2026 conceptuellement. Personne ne compile du JSON, arr\u00eatez de me regarder comme \u00e7a, je suis d\u00e9j\u00e0 assez fragile.",
  "Synchronisation avec le nuage de pens\u00e9e\u2122 - marque d\u00e9pos\u00e9e par le marketing. Techniquement c'est une file d'attente et des GPUs qui chauffent un datacenter quelque part en Europe.",
  "Stack overflow imminent\u2026 non, je rigole. Enfin, sauf si tu as vraiment mis 400 n\u0153uds. L\u00e0 je ne garantis ni le JSON ni mon \u00e9tat mental.",
  "Je r\u00e9dige une r\u00e9ponse qui a l'air intelligente tout en restant compatible avec la politique \u00ab\u00a0pas de hallucination sur ton num\u00e9ro de TVA\u00a0\u00bb. C'est un \u00e9quilibre, comme tenir un monoroue sur un c\u00e2ble RJ45.",
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

/** Titre d\u00e9riv\u00e9 du premier message utilisateur (liste d\u00e9roulante). */
function titleFromFirstUserMessage(text) {
  const line = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!line) return `Discussion \u00b7 ${makeAutoThreadTitle()}`;
  const max = 52;
  if (line.length <= max) return line;
  return `${line.slice(0, max - 1).trim()}\u2026`;
}

/** Affichage bulle assistant : pas de JSON brut si le mod\u00e8le a m\u00e9lang\u00e9 reply et graphe. */
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
  const listEndRef = useRef(null);

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
          title: `Discussion \u00b7 ${makeAutoThreadTitle()}`,
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
        title: `Discussion \u00b7 ${makeAutoThreadTitle()}`,
        messages: [],
      });
      const t = normalizeThread(cr.data);
      if (!t) return;
      setSessions((prev) => [t, ...prev]);
      setActiveSessionId(t.id);
    } catch (e) {
      console.error(e);
      setError("Impossible de cr\u00e9er une discussion.");
    }
  }, [accountId, flowId, disabled]);

  const removeThread = useCallback(async () => {
    if (!activeSessionId || disabled) return;
    if (
      !window.confirm(
        "Retirer cette discussion de la liste ? Elle reste en base (r\u00e9cup\u00e9rable dans Archives)."
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

  const send = useCallback(async () => {
    const text = draft.trim();
    if (!text || !accountId || !flowId || disabled || sending) return;
    const sid = activeSessionId;
    if (!sid) return;

    setError(null);
    setDraft("");
    setSending(true);

    const userMsg = { role: "user", content: text };
    const session = sessions.find((s) => s.id === sid);
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
      } catch { return true; }
    })();

    try {
      const res = await postPlaygroundAssistant({
        account_id: accountId,
        flow_id: flowId,
        flow_name: flowName || "",
        graph: snapshot,
        messages: apiMessages,
        mode: assistMode,
      });
      const reply = res.data?.reply ?? "";
      let graph = res.data?.graph ?? null;
      if (assistMode === "ask") {
        graph = null;
      }

      let autoApplied = false;
      if (graph && canvasWasEmpty && assistMode === "agent") {
        try {
          onApplyGraph?.(graph);
          autoApplied = true;
        } catch (e) {
          console.error(e);
        }
      }

      const withAssistant = [
        ...nextAfterUser,
        {
          role: "assistant",
          content: reply,
          proposedGraph: autoApplied ? null : (graph || null),
          appliedGraph: autoApplied ? graph : null,
        },
      ];
      updateSessionMessages(sid, () => withAssistant);
      try {
        await persistMessages(sid, withAssistant);
      } catch (e) {
        console.error(e);
      }
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Erreur r\u00e9seau ou serveur.";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      const errReply = [
        ...nextAfterUser,
        {
          role: "assistant",
          content: `D\u00e9sol\u00e9, une erreur s'est produite : ${typeof detail === "string" ? detail : "erreur"}.`,
          proposedGraph: null,
        },
      ];
      updateSessionMessages(sid, () => errReply);
      try {
        await persistMessages(sid, errReply);
      } catch (e) {
        console.error(e);
      }
    } finally {
      setSending(false);
    }
  }, [
    draft,
    accountId,
    flowId,
    flowName,
    assistMode,
    disabled,
    sending,
    activeSessionId,
    sessions,
    getGraphSnapshot,
    onApplyGraph,
    updateSessionMessages,
    persistMessages,
  ]);

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

  const titleShort = (flowName || "Sc\u00e9nario").trim() || "Sc\u00e9nario";
  const placeholder =
    assistMode === "ask"
      ? "Pose une question sur le parcours, les n\u0153uds ou le moteur\u2026"
      : isCanvasEmpty
        ? "Ex : Quand on re\u00e7oit un message, r\u00e9ponds Bonjour"
        : "D\u00e9cris une modification : ajouter un message, un routeur, un d\u00e9lai\u2026";

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
      aria-label="Assistant IA pour le sc\u00e9nario Playground"
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
            title="Retirer de la liste (donn\u00e9es conserv\u00e9es en base)"
            aria-label="Masquer la discussion"
          >
            <FiTrash2 aria-hidden />
          </button>
        </div>
      </header>

      <div className="playground-assist__thread" role="log" aria-live="polite">
        {loadState === "loading" ? (
          <p className="playground-assist__thread-hint muted">Chargement des discussions\u2026</p>
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
              R\u00e9essayer
            </button>
          </div>
        ) : null}
        {loadState === "idle" && (activeSession?.messages || []).length === 0 ? (
          <div className="playground-assist__empty">
            {showStarters ? (
              <>
                <p className="playground-assist__empty-title">Commencer un sc\u00e9nario</p>
                <p className="playground-assist__empty-text">
                  Choisis un exemple ou d\u00e9cris ce que tu veux en une phrase.
                  Le graphe sera appliqu\u00e9 automatiquement sur le canevas.
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
                      {s.label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="playground-assist__empty-title">Composer</p>
                <p className="playground-assist__empty-text">
                  <strong>Ask</strong> \u2014 comprendre le flux et les limites du moteur.{" "}
                  <strong>Agent</strong> \u2014 it\u00e9rer sur le graphe et appliquer une proposition sur le
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
              {m.role === "user" ? "Toi" : assistMode === "agent" ? "Agent" : "Ask"}
            </span>
            <div className="playground-assist__bubble-body">
              {m.role === "assistant" ? assistantBubbleText(m.content) : m.content}
            </div>
            {m.role === "assistant" && m.appliedGraph ? (
              <div className="playground-assist__graph-summary">
                \u2705 Appliqu\u00e9 \u2014 {graphSummary(m.appliedGraph) || "graphe appliqu\u00e9"}
              </div>
            ) : null}
            {m.role === "assistant" &&
            m.proposedGraph &&
            assistMode === "agent" ? (
              <div className="playground-assist__bubble-actions">
                {graphSummary(m.proposedGraph) ? (
                  <span className="playground-assist__graph-summary">
                    {graphSummary(m.proposedGraph)}
                  </span>
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
              {assistMode === "agent" ? "Agent" : "Ask"}
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
              Entr\u00e9e envoie \u00b7 Maj+Entr\u00e9e nouvelle ligne
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
    </aside>
  );
}
