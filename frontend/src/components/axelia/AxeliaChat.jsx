import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  FiPaperclip,
  FiImage,
  FiEdit3,
  FiZap,
  FiHeadphones,
  FiMenu,
  FiEdit2,
  FiThumbsUp,
  FiThumbsDown,
  FiRefreshCw,
  FiCopy,
  FiMoreHorizontal,
  FiCheck,
  FiSliders,
} from "react-icons/fi";
import SparkleGlyph from "./SparkleGlyph";
import "../../styles/axelia.css";
import {
  createAxeliaConversation,
  getAxeliaConversations,
  getAxeliaMessages,
  patchAxeliaConversation,
  patchAxeliaMessageRating,
  postAxeliaChat,
  postAxeliaRegenerate,
} from "../../api/axeliaApi";

export const AXELIA_CONTEXT_ALL = "__all__";

/** Aligné sur `_AXELIA_SECTOR_FOCUS` (backend). */
export const AXELIA_SECTORS = [
  { id: "general", label: "Général" },
  { id: "templates", label: "Templates Meta" },
  { id: "broadcast", label: "Diffusion" },
  { id: "writing", label: "Rédaction WA" },
  { id: "flows", label: "Parcours & auto" },
];

const SKILL_LABELS = {
  list_templates: "Templates consultés",
  get_template_status: "Statut template vérifié",
  create_template: "Création template",
  list_broadcast_groups: "Groupes consultés",
  search_inbox_messages: "Recherche inbox",
  get_conversation_digest: "Fil de discussion lu",
  meta_block_contact: "Blocage Meta (confirmation)",
};

const FOCUS_LABELS = Object.fromEntries(
  AXELIA_SECTORS.map((s) => [s.id, s.label]),
);

const SUGGESTIONS = [
  {
    text: "Créer une image",
    icon: <FiImage aria-hidden />,
    fill: "Imagine une bannière WhatsApp minimaliste pour promotion.",
  },
  {
    text: "Créer de la musique",
    icon: <FiHeadphones aria-hidden />,
    fill: "Donne des idées pour une courte mélodie d’attente téléphonique.",
  },
  {
    text: "Aide-moi à apprendre",
    icon: <FiZap aria-hidden />,
    fill: "Explique-moi pas à pas comment structurer une réponse client difficile.",
  },
  {
    text: "Rédiger",
    icon: <FiEdit3 aria-hidden />,
    fill: "Rédige un message professionnel pour confirmer une réservation.",
  },
  {
    text: "Donne du peps à ma journée",
    icon: <FiZap aria-hidden />,
    fill: "Une petite phrase motivante pour une équipe support client.",
  },
];

/** Résumé UI pour les tool_calls en attente (template Meta, blocage contact…). */
function describePendingToolCalls(calls) {
  if (!Array.isArray(calls) || !calls.length)
    return { title: "Action à confirmer", lines: [] };
  const names = calls.map((tc) => tc.skill || tc.name || "");
  const hasTpl = names.some((n) => n === "create_template");
  const hasBlock = names.some((n) => n === "meta_block_contact");
  let title = "Action à confirmer";
  if (hasTpl && hasBlock) title = "Actions à confirmer";
  else if (hasTpl) title = "Création de template sur Meta";
  else if (hasBlock) title = "Blocage WhatsApp (Meta)";
  const lines = calls.map((tc) => {
    const name = tc.skill || tc.name || "outil";
    const args = tc.args || tc.arguments || {};
    if (name === "create_template") {
      const n = args.name || "?";
      const cat = args.category || "?";
      const lang = args.language ? `, langue ${args.language}` : "";
      return `Créer « ${n} » (${cat}${lang})`;
    }
    if (name === "meta_block_contact") {
      const cid = args.contact_id || "?";
      return `Bloquer le contact (id ${cid}) sur la ligne du compte sélectionné`;
    }
    return String(name);
  });
  return { title, lines };
}

/** @param {{ accounts: object[], profile: object | null, hasPermission?: (code: string, accountId?: string|null) => boolean, initialAccountId?: string | null }} props */
export default function AxeliaChat({
  accounts = [],
  profile,
  hasPermission,
  initialAccountId = null,
}) {
  const firstName = useMemo(() => {
    const dn = profile?.display_name?.trim();
    if (dn) return dn.split(/\s+/)[0];
    const em = profile?.email?.split("@")[0];
    return em || "toi";
  }, [profile]);

  const accessibleAccounts = useMemo(
    () =>
      (Array.isArray(accounts) ? accounts : []).filter((a) =>
        hasPermission?.("conversations.view", a?.id),
      ),
    [accounts, hasPermission],
  );

  const [selectedContext, setSelectedContext] = useState(AXELIA_CONTEXT_ALL);
  const contextSeededRef = useRef(false);
  useEffect(() => {
    if (accessibleAccounts.length === 0) return;
    if (contextSeededRef.current) return;
    contextSeededRef.current = true;
    const pick =
      initialAccountId &&
      accessibleAccounts.some((a) => a.id === initialAccountId)
        ? initialAccountId
        : AXELIA_CONTEXT_ALL;
    setSelectedContext(pick);
  }, [accessibleAccounts, initialAccountId]);

  const canUseSend =
    !!accessibleAccounts.length &&
    (selectedContext === AXELIA_CONTEXT_ALL
      ? accessibleAccounts.length > 0
      : !!hasPermission?.("conversations.view", selectedContext));

  const toolsAvailable =
    canUseSend &&
    selectedContext !== AXELIA_CONTEXT_ALL &&
    accessibleAccounts.some((a) => a.id === selectedContext);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);

  /** @type {[Array<{ id: string, role: string, content_text?: string, focus_tag?: string|null, rating?: number|null, model_used?: string }>, Function]} */
  const [messages, setMessages] = useState([]);
  const [menuOpenId, setMenuOpenId] = useState(null);

  const [input, setInput] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingPreviewUrl, setPendingPreviewUrl] = useState(null);
  /** @type {[Record<string, string[]>, Function]} résultats d’outils par id message assistant */
  const [skillsByAssistId, setSkillsByAssistId] = useState({});
  /** @type {[Record<string, unknown[]>, Function]} création Meta en attente de confirmation */
  const [pendingCreateByAssistId, setPendingCreateByAssistId] = useState({});
  const [messageFocus, setMessageFocus] = useState("general");
  const [toolsOpen, setToolsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copyToast, setCopyToast] = useState(false);

  const scrollRef = useRef(null);
  const copyToastTimer = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const contextMeasureRef = useRef(null);
  const toolsWrapRef = useRef(null);
  const [contextSelectWidthPx, setContextSelectWidthPx] = useState(undefined);

  const initDone = useRef(false);

  const loadConversations = useCallback(async () => {
    try {
      const res = await getAxeliaConversations();
      setConversations(res.data || []);
      return res.data || [];
    } catch {
      return [];
    }
  }, []);

  const loadMessages = useCallback(async (cid) => {
    if (!cid) {
      setMessages([]);
      return;
    }
    try {
      const res = await getAxeliaMessages(cid);
      setMessages(Array.isArray(res.data) ? res.data : []);
    } catch {
      setMessages([]);
    }
  }, []);

  useEffect(() => {
    loadMessages(conversationId);
    setSkillsByAssistId({});
    setPendingCreateByAssistId({});
    setToolsOpen(false);
  }, [conversationId, loadMessages]);

  useEffect(() => {
    if (!toolsOpen) return;
    let removeDoc = () => {};
    const tid = window.setTimeout(() => {
      const onDoc = (e) => {
        const el = toolsWrapRef.current;
        if (el && !el.contains(e.target)) setToolsOpen(false);
      };
      document.addEventListener("mousedown", onDoc);
      removeDoc = () => document.removeEventListener("mousedown", onDoc);
    }, 0);
    const onKey = (e) => {
      if (e.key === "Escape") setToolsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(tid);
      removeDoc();
      window.removeEventListener("keydown", onKey);
    };
  }, [toolsOpen]);

  /** Bootstrap : premier fil ou création automatique */
  useEffect(() => {
    if (!canUseSend || initDone.current) return;
    (async () => {
      initDone.current = true;
      const rows = await loadConversations();
      if (rows?.length) {
        setConversationId(rows[0].id);
      } else {
        try {
          const cr = await createAxeliaConversation({
            account_context: selectedContext || AXELIA_CONTEXT_ALL,
          });
          if (cr.data?.id) {
            setConversationId(cr.data.id);
            setConversations([cr.data]);
          }
        } catch {
          initDone.current = false;
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- bootstrap once when canUseSend turns true
  }, [canUseSend]);

  const activeConversation = useMemo(
    () => conversations.find((c) => c.id === conversationId),
    [conversations, conversationId],
  );

  useEffect(() => {
    if (activeConversation?.account_context != null)
      setSelectedContext(activeConversation.account_context);
  }, [activeConversation?.account_context]);

  const contextSelectLabel = useMemo(() => {
    if (
      selectedContext === AXELIA_CONTEXT_ALL ||
      !accessibleAccounts.some((a) => a.id === selectedContext)
    ) {
      return "Tous les comptes";
    }
    const a = accessibleAccounts.find((ac) => ac.id === selectedContext);
    return String(a?.name || a?.phone_number || a?.id || "Tous les comptes");
  }, [accessibleAccounts, selectedContext]);

  const measureContextSelectWidth = useCallback(() => {
    const span = contextMeasureRef.current;
    if (!span) return;
    const EXTRA = 40;
    const vwCap =
      typeof window !== "undefined"
        ? Math.min(window.innerWidth * 0.5, 480)
        : 480;
    const w = span.offsetWidth + EXTRA;
    setContextSelectWidthPx(Math.min(Math.max(w, 88), vwCap));
  }, []);

  useLayoutEffect(() => {
    measureContextSelectWidth();
  }, [contextSelectLabel, measureContextSelectWidth]);

  useEffect(() => {
    window.addEventListener("resize", measureContextSelectWidth);
    return () => window.removeEventListener("resize", measureContextSelectWidth);
  }, [measureContextSelectWidth]);

  useEffect(() => {
    setMessageFocus("general");
  }, [selectedContext]);


  const adjustTextarea = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 240)}px`;
  };

  useEffect(() => {
    adjustTextarea();
  }, [input]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const clearAttachment = useCallback(() => {
    if (pendingPreviewUrl) URL.revokeObjectURL(pendingPreviewUrl);
    setPendingFile(null);
    setPendingPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [pendingPreviewUrl]);

  const readFileAsBase64 = (file) =>
    new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        const dataUrl = r.result;
        if (typeof dataUrl !== "string") {
          reject(new Error("read_failed"));
          return;
        }
        const comma = dataUrl.indexOf(",");
        resolve(comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl);
      };
      r.onerror = () => reject(new Error("read_failed"));
      r.readAsDataURL(file);
    });

  const handlePickFile = () => fileInputRef.current?.click();

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError(
        "Pour l’instant, seules les images sont prises en charge pour l’analyse IA.",
      );
      return;
    }
    clearAttachment();
    setPendingFile(file);
    setPendingPreviewUrl(URL.createObjectURL(file));
    setError(null);
  };

  const bootstrapNewConversation = async (ctx) => {
    const cr = await createAxeliaConversation({
      account_context: ctx,
    });
    if (!cr.data?.id) throw new Error("create_failed");
    await loadConversations();
    setConversationId(cr.data.id);
    setMessages([]);
    return cr.data.id;
  };

  const onNewDiscussion = async () => {
    if (!canUseSend) return;
    try {
      setError(null);
      await bootstrapNewConversation(
        selectedContext || AXELIA_CONTEXT_ALL,
      );
      setSidebarOpen(false);
    } catch {
      setError("Impossible de créer une discussion.");
    }
  };

  const onPickConversation = async (id) => {
    setConversationId(id);
    setSidebarOpen(false);
    setMenuOpenId(null);
  };

  const onChangeContextDropdown = async (next) => {
    if (!canUseSend || next === selectedContext) return;
    try {
      setError(null);
      setSelectedContext(next);
      await bootstrapNewConversation(next);
    } catch {
      setError("Impossible de changer de périmètre.");
    }
  };

  /** Ouvre/ferme le panneau d’orientation (ne dépend pas d’un compte WABA précis — le panneau l’explique). */
  const toggleToolsPanel = useCallback(() => {
    if (!canUseSend || loading) return;
    setToolsOpen((open) => !open);
  }, [canUseSend, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!canUseSend || loading) return;
    if (!conversationId) return;
    if (!text && !pendingFile) return;

    setError(null);
    let attachment = null;
    if (pendingFile) {
      try {
        const dataBase64 = await readFileAsBase64(pendingFile);
        attachment = {
          mime_type: pendingFile.type || "image/jpeg",
          data_base64: dataBase64,
        };
      } catch {
        setError("Impossible de lire le fichier.");
        return;
      }
    }

    const accountId =
      activeConversation?.account_context || selectedContext;

    clearAttachment();
    setInput("");
    setLoading(true);

    try {
      const res = await postAxeliaChat({
        account_id: accountId,
        conversation_id: conversationId,
        user_message: text,
        ...(toolsAvailable ? { sector: messageFocus } : {}),
        ...(attachment ? { attachment } : {}),
      });
      const amid = res.data?.assistant_message_id;
      const skills = res.data?.skills_used;
      const pend = res.data?.pending_tool_calls;
      if (amid && Array.isArray(skills) && skills.length) {
        setSkillsByAssistId((prev) => ({ ...prev, [amid]: skills }));
      }
      if (amid && Array.isArray(pend) && pend.length) {
        setPendingCreateByAssistId((prev) => ({ ...prev, [amid]: pend }));
      }
      await loadMessages(conversationId);
      await loadConversations();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg =
        detail === "gemini_not_configured"
          ? "Clé Gemini absente (GEMINI_API_KEY)."
          : detail === "gemini_unavailable"
            ? "Service IA temporairement indisponible."
            : detail === "account_context_mismatch"
              ? "Périmètre incohérent — change de conversation."
              : detail === "axelia_tools_timeout"
                ? "L’IA a mis trop longtemps (outils)."
                : typeof detail === "string"
                  ? detail
                  : "Erreur lors de l’envoi.";
      setError(msg);
    } finally {
      setLoading(false);
      adjustTextarea();
    }
  };

  const onChip = (fill) => {
    setInput(fill);
    textareaRef.current?.focus();
    adjustTextarea();
  };

  const confirmPendingCreates = async (assistMessageId, calls) => {
    if (!conversationId || !calls?.length || loading) return;
    const accountId =
      activeConversation?.account_context || selectedContext || AXELIA_CONTEXT_ALL;
    if (accountId === AXELIA_CONTEXT_ALL) {
      setError("Choisis un compte WABA pour confirmer la création sur Meta.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await postAxeliaChat({
        account_id: accountId,
        conversation_id: conversationId,
        user_message: "",
        sector: messageFocus,
        approve_tool_calls: calls,
      });
      const amid = res.data?.assistant_message_id;
      const skills = res.data?.skills_used;
      if (amid && Array.isArray(skills) && skills.length) {
        setSkillsByAssistId((prev) => ({ ...prev, [amid]: skills }));
      }
      setPendingCreateByAssistId((prev) => {
        const n = { ...prev };
        delete n[assistMessageId];
        return n;
      });
      await loadMessages(conversationId);
      await loadConversations();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        typeof detail === "string" ? detail : "Confirmation impossible.",
      );
    } finally {
      setLoading(false);
    }
  };

  const cancelPendingCreates = (assistMessageId) => {
    setPendingCreateByAssistId((prev) => {
      const n = { ...prev };
      delete n[assistMessageId];
      return n;
    });
  };

  const setRating = async (messageId, rating) => {
    try {
      await patchAxeliaMessageRating(messageId, { rating });
      await loadMessages(conversationId);
    } catch {
      setError("Enregistrement du vote impossible.");
    }
  };

  const regenerate = async () => {
    if (!conversationId || loading) return;
    setLoading(true);
    setError(null);
    try {
      await postAxeliaRegenerate(conversationId);
      await loadMessages(conversationId);
      await loadConversations();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Régénération impossible.");
    } finally {
      setLoading(false);
    }
  };

  const copyText = async (t) => {
    try {
      await navigator.clipboard.writeText(t || "");
      setCopyToast(true);
      if (copyToastTimer.current) window.clearTimeout(copyToastTimer.current);
      copyToastTimer.current = window.setTimeout(() => setCopyToast(false), 2200);
    } catch {
      setError("Copie impossible dans ce navigateur.");
    }
  };

  const togglePin = async (c) => {
    try {
      await patchAxeliaConversation(c.id, { pinned: !c.pinned });
      await loadConversations();
    } catch {
      setError("Action impossible.");
    }
    setMenuOpenId(null);
  };

  const renameConv = async (c) => {
    const t = window.prompt("Nouveau titre", c.title || "");
    if (t == null) return;
    const title = t.trim();
    if (!title) return;
    try {
      await patchAxeliaConversation(c.id, { title });
      await loadConversations();
    } catch {
      setError("Renommage impossible.");
    }
    setMenuOpenId(null);
  };

  const hideConv = async (c) => {
    if (!window.confirm("Supprimer cette discussion ? (contenu conservé côté serveur.)"))
      return;
    try {
      await patchAxeliaConversation(c.id, { hidden: true });
      const rows = await loadConversations();
      if (c.id === conversationId) {
        if (rows?.length) setConversationId(rows[0].id);
        else {
          setConversationId(null);
          await bootstrapNewConversation(selectedContext || AXELIA_CONTEXT_ALL);
        }
      }
    } catch {
      setError("Suppression impossible.");
    }
    setMenuOpenId(null);
  };

  const hasThread = messages.length > 0 || loading;
  const showSplash = !hasThread && !loading;

  return (
    <div className="axelia-page">
      {copyToast ? (
        <div className="axelia-copy-toast" role="status">
          Copié
        </div>
      ) : null}
      <header className="axelia-topbar">
        <button
          type="button"
          className="axelia-topbar__iconbtn"
          aria-label="Menu des discussions"
          onClick={() => setSidebarOpen(true)}
        >
          <FiMenu size={22} />
        </button>
      </header>

      <div
        className={`axelia-shell ${sidebarOpen ? "axelia-shell--sidebar-open" : ""}`}
      >
        <aside
          className={`axelia-sidebar ${sidebarOpen ? "axelia-sidebar--open" : ""}`}
        >
          <div className="axelia-sidebar__head">
            <span className="axelia-sidebar__title">Discussions</span>
            <button
              type="button"
              className="axelia-sidebar__close"
              onClick={() => setSidebarOpen(false)}
            >
              ×
            </button>
          </div>
          <div className="axelia-sidebar__list">
            <div className="axelia-sidebar__list-head">
              <button
                type="button"
                className="axelia-sidebar__new-discussion"
                onClick={onNewDiscussion}
                disabled={!canUseSend}
              >
                <FiEdit2 size={20} aria-hidden />
                <span>Nouvelle discussion</span>
              </button>
            </div>
            <div className="axelia-sidebar__list-scroll">
              {conversations.map((c) => (
                <div
                  key={c.id}
                  className={`axelia-sidebar-row ${
                    c.id === conversationId ? "axelia-sidebar-row--active" : ""
                  }`}
                >
                  <button
                    type="button"
                    className="axelia-sidebar-row__main"
                    onClick={() => onPickConversation(c.id)}
                  >
                    {c.pinned && <span title="Épinglé">📌 </span>}
                    <span className="axelia-sidebar-row__title">
                      {c.title || "Sans titre"}
                    </span>
                  </button>
                  <div className="axelia-sidebar-row__menu">
                    <button
                      type="button"
                      aria-label="Options"
                      onClick={() =>
                        setMenuOpenId(menuOpenId === c.id ? null : c.id)
                      }
                    >
                      <FiMoreHorizontal />
                    </button>
                    {menuOpenId === c.id && (
                      <div className="axelia-sidebar-popup">
                        <button type="button" onClick={() => togglePin(c)}>
                          Épingler
                        </button>
                        <button type="button" onClick={() => renameConv(c)}>
                          Renommer
                        </button>
                        <button type="button" onClick={() => hideConv(c)}>
                          Supprimer
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {!conversations.length && (
                <p className="axelia-sidebar__empty">Aucune discussion</p>
              )}
            </div>
          </div>
        </aside>

        <div className="axelia-chat-main">
          <button
            type="button"
            className="axelia-sidebar-overlay"
            aria-label="Fermer le menu"
            tabIndex={sidebarOpen ? 0 : -1}
            onClick={() => setSidebarOpen(false)}
          />

          <div
            className={`axelia-page__body ${
              showSplash ? "axelia-page__body--splash" : ""
            }`}
          >
            {!showSplash && (
              <div ref={scrollRef} className="axelia-messages axelia-messages--thread">
            {messages.map((m) => {
              if (m.role === "user") {
                const tag =
                  m.focus_tag && String(m.focus_tag).trim()
                    ? FOCUS_LABELS[m.focus_tag] || m.focus_tag
                    : null;
                return (
                  <div key={m.id} className="axelia-user-row">
                    <div className="axelia-user-stack">
                      {tag ? (
                        <span className="axelia-focus-tag" title="Orientation">
                          {tag}
                        </span>
                      ) : null}
                      <div className="axelia-bubble axelia-bubble--user">
                        {m.content_text}
                      </div>
                    </div>
                  </div>
                );
              }
              const text = (m.content_text || "").trim();
              const skillsUsed = skillsByAssistId[m.id];
              const pendingCreates = pendingCreateByAssistId[m.id];
              const pendingDesc = describePendingToolCalls(
                Array.isArray(pendingCreates) ? pendingCreates : [],
              );
              return (
                <div key={m.id} className="axelia-model-block">
                  <div className="axelia-model-line">
                    <SparkleGlyph animate={false} />
                    <div className="axelia-model-text">{text}</div>
                  </div>
                  {Array.isArray(skillsUsed) && skillsUsed.length > 0 ? (
                    <div className="axelia-assist-skills" aria-label="Outils utilisés">
                      {[...new Set(skillsUsed)].map((sk) => (
                        <span key={sk} className="axelia-assist-skills__badge">
                          {SKILL_LABELS[sk] || sk}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {Array.isArray(pendingCreates) && pendingCreates.length > 0 ? (
                    <div
                      className="axelia-pending-tools"
                      role="region"
                      aria-label={pendingDesc.title}
                    >
                      <p className="axelia-pending-tools__title">
                        {pendingDesc.title}
                      </p>
                      <p className="axelia-pending-tools__desc">
                        {pendingDesc.lines.join(" · ")}
                      </p>
                      <div className="axelia-pending-tools__actions">
                        <button
                          type="button"
                          className="axelia-pending-tools__confirm"
                          onClick={() =>
                            confirmPendingCreates(m.id, pendingCreates)
                          }
                          disabled={
                            loading || !toolsAvailable || !conversationId
                          }
                        >
                          <FiCheck aria-hidden /> Confirmer
                        </button>
                        <button
                          type="button"
                          className="axelia-pending-tools__cancel"
                          onClick={() => cancelPendingCreates(m.id)}
                          disabled={loading}
                        >
                          Annuler
                        </button>
                      </div>
                    </div>
                  ) : null}
                  <div className="axelia-model-actions">
                    <button
                      type="button"
                      aria-label="Utile"
                      className={
                        m.rating === 1 ? "axelia-ma--on" : ""
                      }
                      onClick={() =>
                        setRating(m.id, m.rating === 1 ? null : 1)
                      }
                    >
                      <FiThumbsUp />
                    </button>
                    <button
                      type="button"
                      aria-label="Pas utile"
                      className={
                        m.rating === -1 ? "axelia-ma--on" : ""
                      }
                      onClick={() =>
                        setRating(m.id, m.rating === -1 ? null : -1)
                      }
                    >
                      <FiThumbsDown />
                    </button>
                    <button
                      type="button"
                      aria-label="Régénérer"
                      onClick={regenerate}
                      disabled={loading}
                    >
                      <FiRefreshCw />
                    </button>
                    <button
                      type="button"
                      aria-label="Copier"
                      onClick={() => copyText(text)}
                    >
                      <FiCopy />
                    </button>
                  </div>
                </div>
              );
            })}
            {loading && (
              <div className="axelia-model-block">
                <div className="axelia-model-line">
                  <SparkleGlyph animate />
                  <div className="axelia-model-text axelia-model-text--muted">
                    Réponse…
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        <div
          className={`axelia-dock ${
            showSplash ? "axelia-dock--splash" : "axelia-dock--floating"
          }`}
        >
          {showSplash && (
            <div className="axelia-greet">
              <p className="axelia-greet__hi">Bonjour {firstName},</p>
              <p className="axelia-greet__sub">Par où commencer&nbsp;?</p>
            </div>
          )}

          <div className="axelia-dock-inner">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="axelia-file-input"
              onChange={handleFileChange}
            />

            {!canUseSend && accessibleAccounts.length === 0 && accounts.length > 0 && (
              <p className="axelia-error axelia-error--dock">
                Aucun compte accessible pour les conversations.
              </p>
            )}

            <div className="axelia-input-card">
              {pendingPreviewUrl && (
                <div className="axelia-attach-preview">
                  <img src={pendingPreviewUrl} alt="" />
                  <span>{pendingFile?.name}</span>
                  <button
                    type="button"
                    className="axelia-icon-btn"
                    onClick={clearAttachment}
                    aria-label="Retirer"
                  >
                    ×
                  </button>
                </div>
              )}
              {toolsAvailable && messageFocus !== "general" ? (
                <div className="axelia-sector-strip">
                  <span className="axelia-sector-strip__badge" title="Orientation active">
                    {FOCUS_LABELS[messageFocus] || messageFocus}
                  </span>
                  <button
                    type="button"
                    className="axelia-sector-strip__clear"
                    onClick={() => setMessageFocus("general")}
                    aria-label="Revenir à Général"
                  >
                    Réinitialiser
                  </button>
                </div>
              ) : null}
              <textarea
                ref={textareaRef}
                placeholder="Pose une question ou décris ce dont tu as besoin…"
                rows={2}
                value={input}
                disabled={loading}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
              />
              <div className="axelia-input-toolbar">
                <div className="axelia-input-toolbar__left">
                  <button
                    type="button"
                    className="axelia-icon-btn axelia-icon-btn--solo"
                    onClick={handlePickFile}
                    disabled={!canUseSend || loading}
                    title="Joindre une image"
                    aria-label="Joindre une image"
                  >
                    <FiPaperclip aria-hidden size={22} />
                  </button>
                  <div className="axelia-tools-wrap" ref={toolsWrapRef}>
                    <button
                      type="button"
                      className={`axelia-tools-btn ${
                        messageFocus !== "general" ? "axelia-tools-btn--active" : ""
                      }`}
                      onClick={toggleToolsPanel}
                      disabled={!canUseSend || loading}
                      title={
                        toolsAvailable
                          ? "Orientation (templates, diffusion…) — comme /skills, sans afficher dans le texte"
                          : "Ouvre les orientations · pour les outils Meta, choisis un compte dans le menu à droite"
                      }
                      aria-expanded={toolsOpen}
                      aria-haspopup="menu"
                    >
                      <FiSliders
                        aria-hidden
                        className="axelia-tools-btn__icon"
                        size={22}
                        strokeWidth={2}
                      />
                      <span className="axelia-tools-btn__label">Outils</span>
                      {toolsAvailable && messageFocus !== "general" ? (
                        <span className="axelia-tools-btn__pulse" aria-hidden />
                      ) : null}
                    </button>
                    {toolsOpen ? (
                      <div
                        className="axelia-tools-panel"
                        role="menu"
                        aria-label="Orientation du message"
                      >
                        <p className="axelia-tools-panel__hint">
                          Appliquée aux messages suivants (invisible dans le champ
                          texte — affichée en tag sur l’envoi hors « Général »).
                        </p>
                        {!toolsAvailable ? (
                          <p className="axelia-tools-panel__notice">
                            Pour activer templates Meta et groupes de diffusion dans
                            l’IA, sélectionne un compte WhatsApp dans le menu à droite (
                            hors « Tous les comptes »).
                          </p>
                        ) : null}
                        <div className="axelia-tools-panel__list">
                          {AXELIA_SECTORS.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              role="menuitemradio"
                              aria-checked={messageFocus === s.id}
                              className={`axelia-tools-option ${
                                messageFocus === s.id ? "is-active" : ""
                              }`}
                              onClick={() => {
                                setMessageFocus(s.id);
                                setToolsOpen(false);
                              }}
                            >
                              {s.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
                <div className="axelia-input-toolbar__right">
                  <span
                    ref={contextMeasureRef}
                    className="axelia-context-measure"
                    aria-hidden
                  >
                    {contextSelectLabel}
                  </span>
                  <select
                    className="axelia-context-select"
                    aria-label="Périmètre du contexte"
                    style={{
                      ...(contextSelectWidthPx != null && {
                        width: contextSelectWidthPx,
                      }),
                    }}
                    value={
                      accessibleAccounts.some((a) => a.id === selectedContext)
                        ? selectedContext
                        : AXELIA_CONTEXT_ALL
                    }
                    onChange={(e) => onChangeContextDropdown(e.target.value)}
                    disabled={loading || accessibleAccounts.length === 0}
                  >
                    <option value={AXELIA_CONTEXT_ALL}>Tous les comptes</option>
                    {accessibleAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name || a.phone_number || a.id}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="axelia-send-btn"
                    disabled={
                      (!input.trim() && !pendingFile) || !canUseSend || loading
                    }
                    onClick={sendMessage}
                    title="Envoyer"
                    aria-label="Envoyer"
                  >
                    <svg
                      className="axelia-send-btn__svg"
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      aria-hidden
                    >
                      <path
                        fill="currentColor"
                        d="M2.01 21L23 12 2.01 3v7l15 2-15 2v7z"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <p className="axelia-disclaimer">
              Axelia est une IA et peut se tromper, y compris sur des personnes. Vérifiez les
              informations sensibles.
            </p>

            {showSplash && (
              <div className="axelia-chips">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s.text}
                    type="button"
                    className="axelia-chip"
                    disabled={!canUseSend || loading}
                    onClick={() => onChip(s.fill)}
                  >
                    {s.icon}
                    {s.text}
                  </button>
                ))}
              </div>
            )}

            {error && <div className="axelia-error">{error}</div>}
          </div>
        </div>
        </div>
        </div>
      </div>
    </div>
  );
}
