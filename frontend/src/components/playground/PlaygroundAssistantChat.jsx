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
  return "ask";
}

/** Messages fantaisistes affichés pendant l’attente — rassurent sans être de vraies étapes techniques. */
const ASSIST_WAITING_THOUGHTS = [
  "Je parcours le graphe… tu sais, comme quand on relit un mail avant d’envoyer.",
  "Synchronisation avec les nuages de pensée… (en vrai c’est juste l’API qui réfléchit.)",
  "Je vérifie que les blocs sur le canevas se sont pas disputés entre eux.",
  "Hmm, bonne question. Je mets de l’ordre dans les nœuds et les flèches.",
  "Patience : les gros scénarios, ça mérite un peu d’amour.",
  "J’allume une lampe torche sur ton parcours utilisateur.",
  "Presque là — je traduis le bazar en français clair.",
  "Je fais semblant d’être une IA très sérieuse pendant encore 2 secondes.",
  "Encore un instant : je range mes idées avant de te répondre proprement.",
  "Si tu entends du silence, c’est que je lis… pas que j’ai planté. Enfin, normalement.",
  "Je compte les branches. Spoiler : il y en a peut-être plus qu’on ne croit.",
  "Connexion au cerveau artificiel… barre de progression imaginaire à 87 %.",
  "Je vérifie les limites moteur vs ce que l’UI promet — le classique.",
  "Un dernier coup d’œil sur les handles source/target pour pas dire de bêtises.",
  "Ça arrive. Les modèles aussi ont leurs petits moments de grâce.",
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
    }, 2300);
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
      const withAssistant = [
        ...nextAfterUser,
        {
          role: "assistant",
          content: reply,
          proposedGraph: graph || null,
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
        "Erreur réseau ou serveur.";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
      const errReply = [
        ...nextAfterUser,
        {
          role: "assistant",
          content: `Désolé, une erreur s’est produite : ${typeof detail === "string" ? detail : "erreur"}.`,
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
        setError("Impossible d’appliquer ce graphe.");
      }
    },
    [activeSessionId, assistMode, onApplyGraph, persistMessages]
  );

  const titleShort = (flowName || "Scénario").trim() || "Scénario";
  const placeholder =
    assistMode === "ask"
      ? "Pose une question sur le parcours, les nœuds ou le moteur…"
      : "Décris une modification : l’IA peut proposer un graphe à appliquer…";

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
            <p className="playground-assist__empty-title">Composer</p>
            <p className="playground-assist__empty-text">
              <strong>Ask</strong> — comprendre le flux et les limites du moteur.{" "}
              <strong>Agent</strong> — itérer sur le graphe et appliquer une proposition sur le
              canevas. Le nom de chaque fil se met à jour tout seul après ton premier message.
            </p>
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
            <div className="playground-assist__bubble-body">{m.content}</div>
            {m.role === "assistant" &&
            m.proposedGraph &&
            assistMode === "agent" ? (
              <div className="playground-assist__bubble-actions">
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
          aria-label="Mode de l’assistant"
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
    </aside>
  );
}
