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
  FiSquare,
  FiSearch,
  FiFileText,
} from "react-icons/fi";
import SparkleGlyph from "./SparkleGlyph";
import { renderMarkdown } from "./renderMarkdown";
import "../../styles/axelia.css";
import {
  loadAxeliaResponseDepth,
  saveAxeliaResponseDepth,
} from "../../utils/axeliaSettings";
import { toAxeliaModelLabel } from "../../utils/axeliaModelLabel";
import { toAxeliaDepthLabel } from "../../utils/axeliaDepthLabel";
import {
  createAxeliaConversation,
  getAxeliaChatProgress,
  getAxeliaConversations,
  getAxeliaMessages,
  patchAxeliaConversation,
  patchAxeliaMessageRating,
  postAxeliaRegenerate,
  streamAxeliaChat,
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

export const AXELIA_RESPONSE_DEPTHS = [
  { id: "brief", label: "Bref" },
  { id: "standard", label: "Standard" },
  { id: "expert", label: "Expert" },
];

const SKILL_LABELS = {
  list_templates: "Templates consultés",
  get_template_status: "Statut template vérifié",
  create_template: "Création template",
  prepare_template_image_header: "Image template uploadée",
  list_broadcast_groups: "Groupes consultés",
  search_inbox_messages: "Recherche inbox",
  get_conversation_digest: "Fil de discussion lu",
  summarize_contact_inbox: "Résumé contact (inbox)",
  search_contacts: "Contacts recherchés",
  get_contact: "Fiche contact",
  list_recent_conversations: "Conversations récentes",
  list_broadcast_campaigns: "Campagnes listées",
  get_campaign_summary: "Statistiques campagne",
  get_whatsapp_business_profile: "Profil WhatsApp Business",
  meta_block_contact: "Blocage Meta (confirmation)",
};

/** Libellés affichés pendant la génération (skill courant). */
const SKILL_RUNNING_LABELS = {
  list_templates: "Lecture des templates Meta…",
  get_template_status: "Vérification du template…",
  create_template: "Préparation du template…",
  prepare_template_image_header: "Upload de l’image vers WhatsApp…",
  list_broadcast_groups: "Lecture des groupes de diffusion…",
  search_inbox_messages: "Recherche dans l’inbox…",
  get_conversation_digest: "Lecture du fil de discussion…",
  summarize_contact_inbox: "Résumé du contact en cours…",
  search_contacts: "Recherche du contact…",
  get_contact: "Lecture de la fiche contact…",
  list_recent_conversations: "Lecture des dernières conversations…",
  list_broadcast_campaigns: "Lecture des campagnes…",
  get_campaign_summary: "Analyse de la campagne…",
  get_whatsapp_business_profile: "Lecture du profil WhatsApp Business…",
  meta_block_contact: "Préparation du blocage Meta…",
};

const PHASE_LABELS = {
  classifying: "Analyse de la demande…",
  thinking: "Réflexion…",
  received: "Démarrage…",
};

/** Pagination liste sidebar : charge d’abord N fils légers ; messages au clic / sélection. */
const AXELIA_CONV_PAGE = 10;
/** Hauteur approximative du menu ⋯ (épingler / renommer / supprimer), pour le flip vertical. */
const AXELIA_SIDEBAR_MENU_EST_HEIGHT_PX = 136;

const REGEN_COOLDOWN_MS = 1500;
const PENDING_TOOLS_TTL_MS = 30 * 60_000;
/** Limite côté UI : 16 Mo bruts (le backend accepte ~13 Mo en base64). */
const ATTACHMENT_MAX_BYTES = 16 * 1024 * 1024;
const ATTACHMENT_ACCEPT = "image/*,application/pdf";

/** UUID v4-like (suffit comme clé de progression côté serveur in-memory). */
const generateRequestId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback non-cryptographique mais largement suffisant pour cet usage.
  return "axx-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
};

const isPdfMime = (mime) =>
  typeof mime === "string" && mime.toLowerCase() === "application/pdf";

const isImageMime = (mime) =>
  typeof mime === "string" && mime.toLowerCase().startsWith("image/");

const FOCUS_LABELS = Object.fromEntries(
  AXELIA_SECTORS.map((s) => [s.id, s.label]),
);

const SUGGESTIONS = [
  {
    text: "Résumé du contact",
    icon: <FiSearch aria-hidden />,
    fill: "Résume les 30 derniers messages de cette conversation et donne 3 points d'action.",
  },
  {
    text: "Réponse pro",
    icon: <FiEdit3 aria-hidden />,
    fill: "Rédige une réponse professionnelle courte pour ce client, ton clair et rassurant.",
  },
  {
    text: "Templates Meta",
    icon: <FiFileText aria-hidden />,
    fill: "Liste les templates Meta disponibles pour ce compte et propose le plus adapté à une relance.",
  },
  {
    text: "Groupes diffusion",
    icon: <FiHeadphones aria-hidden />,
    fill: "Montre les groupes de diffusion existants et propose lequel utiliser pour une campagne de rappel.",
  },
  {
    text: "Message de relance",
    icon: <FiZap aria-hidden />,
    fill: "Rédige un message de relance WhatsApp poli avec 2 variantes (court et détaillé).",
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

function AxeliaComposerPlan({ todos }) {
  if (!Array.isArray(todos) || todos.length === 0) return null;
  return (
    <div className="axelia-composer-plan" aria-label="Plan d’action Axelia">
      <div className="axelia-composer-plan__label">Plan</div>
      <ul className="axelia-composer-plan__list">
        {todos.map((t, idx) => {
          const st = t?.status || "pending";
          const rowKey = `${idx}-${String(t?.id ?? "").slice(0, 64)}`;
          const showThought = st === "in_progress" && t?.thought;
          return (
            <li
              key={rowKey}
              className={`axelia-composer-plan__item axelia-composer-plan__item--${st}`}
            >
              <span className="axelia-composer-plan__mark" aria-hidden />
              <div className="axelia-composer-plan__body">
                <span className="axelia-composer-plan__title">
                  {t?.title || "Étape"}
                </span>
                {showThought ? (
                  <span className="axelia-composer-plan__thought">{t.thought}</span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
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

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((open) => !open);
  }, []);

  const closeSidebarOnMobile = useCallback(() => {
    if (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 720px)").matches
    ) {
      setSidebarOpen(false);
    }
  }, []);

  const [conversations, setConversations] = useState([]);
  const conversationsRef = useRef([]);
  const [convHasMore, setConvHasMore] = useState(false);
  const [convLoadingMore, setConvLoadingMore] = useState(false);
  const [conversationId, setConversationId] = useState(null);

  /** @type {[Array<{ id: string, role: string, content_text?: string, focus_tag?: string|null, rating?: number|null, model_used?: string }>, Function]} */
  const [messages, setMessages] = useState([]);
  const [menuOpenId, setMenuOpenId] = useState(null);
  /** Menu ⋯ au-dessus de la ligne si peu de place en bas dans la zone scroll (évite le chevauchement avec l’en-tête). */
  const [sidebarMenuPopupAbove, setSidebarMenuPopupAbove] = useState(false);

  const [input, setInput] = useState("");
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingPreviewUrl, setPendingPreviewUrl] = useState(null);
  /** @type {[Record<string, string[]>, Function]} résultats d’outils par id message assistant */
  const [skillsByAssistId, setSkillsByAssistId] = useState({});
  /** @type {[Record<string, "brief" | "standard" | "expert">, Function]} mode de réponse utilisé par message assistant */
  const [depthByAssistId, setDepthByAssistId] = useState({});
  /** @type {[Record<string, { calls: unknown[], expiresAt: number }>, Function]} création Meta en attente de confirmation (avec TTL côté UI) */
  const [pendingCreateByAssistId, setPendingCreateByAssistId] = useState({});
  const [messageFocus, setMessageFocus] = useState("general");
  const [responseDepth, setResponseDepth] = useState(() =>
    loadAxeliaResponseDepth(),
  );

  useEffect(() => {
    saveAxeliaResponseDepth(responseDepth);
  }, [responseDepth]);
  const [loading, setLoading] = useState(false);
  /** Affichage immédiat de la bulle utilisateur pendant l’appel au modèle */
  const [optimisticOutgoing, setOptimisticOutgoing] = useState(null);
  const [error, setError] = useState(null);
  /** Toast générique : `{ id, text }` ; `null` = caché. Remplace l'ancien `copyToast` booléen. */
  const [toast, setToast] = useState(null);
  /** Progression côté serveur (skill / phase courante). `null` quand pas en attente. */
  const [progressInfo, setProgressInfo] = useState(null);
  /** Anti-clic accidentel : Régénérer reste désactivé pendant ~1,5 s après une réponse. */
  const [regenLocked, setRegenLocked] = useState(false);
  /** Filtre texte pour la sidebar (titres). */
  const [sidebarFilter, setSidebarFilter] = useState("");
  /** True quand un AbortController est attaché à la requête en cours (UI : bouton Stop). */
  const [aborting, setAborting] = useState(false);
  /** Texte assistant streamé (token-par-token) pendant l'appel SSE en cours.
   *  `null` = pas de stream, sinon string accumulée affichée dans une bulle live. */
  const [streamingText, setStreamingText] = useState(null);
  /** Modèle annoncé par l'évènement `meta` ; affiché à côté de la bulle live. */
  const [streamingModel, setStreamingModel] = useState(null);

  const scrollRef = useRef(null);
  const toastTimerRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const contextMeasureRef = useRef(null);
  const abortRef = useRef(null);
  const progressKeyRef = useRef(null);
  const progressTimerRef = useRef(null);
  const [contextSelectWidthPx, setContextSelectWidthPx] = useState(undefined);

  const initDone = useRef(false);
  const sidebarListScrollRef = useRef(null);

  /** Affichage d'un toast informatif (générique : copie, confirmation, etc.). */
  const showToast = useCallback((text, durationMs = 2200) => {
    if (!text) return;
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast({ id: Date.now(), text });
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, durationMs);
  }, []);

  /** Nettoie l'éventuel timer de polling et l'AbortController. */
  const cleanupInflight = useCallback(() => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    progressKeyRef.current = null;
    abortRef.current = null;
    setAborting(false);
    setProgressInfo(null);
    setStreamingText(null);
    setStreamingModel(null);
  }, []);

  const startProgressPolling = useCallback(() => {
    if (progressTimerRef.current) {
      window.clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    progressTimerRef.current = window.setInterval(async () => {
      const key = progressKeyRef.current;
      if (!key) return;
      const abort = abortRef.current;
      try {
        const res = await getAxeliaChatProgress(key, {
          signal: abort?.signal,
        });
        if (progressKeyRef.current !== key) return;
        const data = res?.data;
        if (data && typeof data === "object" && Object.keys(data).length) {
          setProgressInfo((prev) => ({ ...(prev || {}), ...data }));
        }
      } catch (err) {
        const cancelled =
          err?.code === "ERR_CANCELED" ||
          err?.name === "CanceledError" ||
          err?.name === "AbortError";
        if (cancelled) return;
      }
    }, 400);
  }, []);

  const regenLockTimerRef = useRef(null);
  const armRegenCooldown = useCallback(() => {
    setRegenLocked(true);
    if (regenLockTimerRef.current) {
      window.clearTimeout(regenLockTimerRef.current);
    }
    regenLockTimerRef.current = window.setTimeout(() => {
      setRegenLocked(false);
      regenLockTimerRef.current = null;
    }, REGEN_COOLDOWN_MS);
  }, []);

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  const loadConversations = useCallback(async (opts = {}) => {
    const { append = false, syncSize = null } = opts;
    try {
      let offset = 0;
      let limit = AXELIA_CONV_PAGE;
      if (append) {
        offset = conversationsRef.current.length;
        limit = AXELIA_CONV_PAGE;
      } else if (typeof syncSize === "number" && syncSize > 0) {
        limit = Math.min(Math.max(syncSize, AXELIA_CONV_PAGE), 200);
        offset = 0;
      }
      const res = await getAxeliaConversations({ limit, offset });
      const batch = Array.isArray(res.data) ? res.data : [];
      if (append) {
        setConversations((prev) => [...prev, ...batch]);
      } else {
        setConversations(batch);
      }
      setConvHasMore(batch.length === limit);
      return batch;
    } catch {
      if (!append) {
        setConversations([]);
        setConvHasMore(false);
      }
      return [];
    }
  }, []);

  const handleSidebarScroll = useCallback(
    (e) => {
      const el = e.currentTarget;
      if (!convHasMore || convLoadingMore) return;
      if (el.scrollTop + el.clientHeight < el.scrollHeight - 56) return;
      setConvLoadingMore(true);
      void loadConversations({ append: true }).finally(() => {
        setConvLoadingMore(false);
      });
    },
    [convHasMore, convLoadingMore, loadConversations],
  );

  /** Rafraîchit la liste en conservant la profondeur déjà chargée (titres / ordre). */
  const reloadConversationsSynced = useCallback(
    () =>
      loadConversations({
        syncSize: Math.max(AXELIA_CONV_PAGE, conversationsRef.current.length),
      }),
    [loadConversations],
  );

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
    setDepthByAssistId({});
    setPendingCreateByAssistId({});
  }, [conversationId, loadMessages]);

  useEffect(() => {
    if (menuOpenId == null) return;
    const onDoc = (e) => {
      const t = e.target;
      if (!(t instanceof Element)) return;
      if (t.closest(".axelia-sidebar-popup")) return;
      /* Ne pas fermer avant le clic sur le bouton ⋯ (phase capture sur document) */
      if (t.closest(".axelia-sidebar-row__menu-trigger")) return;
      setMenuOpenId(null);
    };
    document.addEventListener("pointerdown", onDoc, true);
    return () => document.removeEventListener("pointerdown", onDoc, true);
  }, [menuOpenId]);

  useLayoutEffect(() => {
    if (menuOpenId == null) {
      setSidebarMenuPopupAbove(false);
      return;
    }
    const scrollEl = sidebarListScrollRef.current;
    if (!scrollEl) return;
    let row = null;
    try {
      row = scrollEl.querySelector(
        `[data-axelia-conv-row="${CSS.escape(menuOpenId)}"]`,
      );
    } catch {
      row = scrollEl.querySelector(`[data-axelia-conv-row="${menuOpenId}"]`);
    }
    if (!row || !(row instanceof HTMLElement)) return;
    const rowRect = row.getBoundingClientRect();
    const scrollRect = scrollEl.getBoundingClientRect();
    const spaceBelow = scrollRect.bottom - rowRect.bottom;
    const spaceAbove = rowRect.top - scrollRect.top;
    const h = AXELIA_SIDEBAR_MENU_EST_HEIGHT_PX;
    const openAbove =
      spaceBelow < h && spaceAbove >= h && spaceAbove >= spaceBelow;
    setSidebarMenuPopupAbove(openAbove);
  }, [menuOpenId, sidebarFilter, conversations.length]);

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

  /** Aligné sur le sélecteur de périmètre (le serveur garde la vérité sur nom / téléphone). */
  const uiPerimeterHint = useMemo(() => {
    if (selectedContext === AXELIA_CONTEXT_ALL) return "Tous les comptes";
    const a = accessibleAccounts.find((x) => x.id === selectedContext);
    if (!a) return null;
    const name = (a.name || "").trim();
    const ph = (a.phone_number || "").trim();
    if (name && ph) return `${name} - ${ph}`;
    return name || ph || null;
  }, [selectedContext, accessibleAccounts]);

  const topbarConversationTitle = useMemo(() => {
    const t = activeConversation?.title?.trim();
    if (t) return t;
    if (conversationId && !activeConversation) return "…";
    return "Discussion";
  }, [activeConversation, conversationId]);

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
  }, [messages, loading, optimisticOutgoing]);

  const clearAttachment = useCallback(() => {
    if (pendingPreviewUrl) URL.revokeObjectURL(pendingPreviewUrl);
    setPendingFile(null);
    setPendingPreviewUrl(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [pendingPreviewUrl]);

  const clearOptimisticOutgoing = useCallback(() => {
    setOptimisticOutgoing((prev) => {
      if (prev?.imagePreviewUrl) URL.revokeObjectURL(prev.imagePreviewUrl);
      return null;
    });
  }, []);

  /** Tous les 60 s, retire les pending tool_calls expirés (TTL UI 30 min). */
  useEffect(() => {
    const tid = window.setInterval(() => {
      setPendingCreateByAssistId((prev) => {
        const now = Date.now();
        let changed = false;
        const next = {};
        for (const k of Object.keys(prev)) {
          const entry = prev[k];
          if (entry && entry.expiresAt && entry.expiresAt < now) {
            changed = true;
            continue;
          }
          next[k] = entry;
        }
        return changed ? next : prev;
      });
    }, 60_000);
    return () => window.clearInterval(tid);
  }, []);

  /** Démontage : on libère les ressources async (timers, abort). */
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
      if (progressTimerRef.current) {
        window.clearInterval(progressTimerRef.current);
        progressTimerRef.current = null;
      }
      if (regenLockTimerRef.current) {
        window.clearTimeout(regenLockTimerRef.current);
        regenLockTimerRef.current = null;
      }
      if (abortRef.current) {
        try {
          abortRef.current.abort();
        } catch {
          /* noop */
        }
        abortRef.current = null;
      }
    };
  }, []);

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
    const mime = (file.type || "").toLowerCase();
    if (!isImageMime(mime) && !isPdfMime(mime)) {
      setError("Formats acceptés : images (jpg, png, webp…) et PDF.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    if (file.size > ATTACHMENT_MAX_BYTES) {
      setError(
        `Fichier trop lourd (${Math.round(file.size / (1024 * 1024))} Mo) - limite ${Math.round(
          ATTACHMENT_MAX_BYTES / (1024 * 1024),
        )} Mo.`,
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    clearAttachment();
    setPendingFile(file);
    // L'aperçu n'a de sens visuel que pour les images ; les PDF afficheront une miniature texte.
    setPendingPreviewUrl(isImageMime(mime) ? URL.createObjectURL(file) : null);
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

  const buildAxeliaBasePayload = useCallback(
    (accountId, progressKey) => ({
      account_id: accountId,
      conversation_id: conversationId,
      progress_key: progressKey,
      response_depth: responseDepth,
      ...(uiPerimeterHint ? { ui_perimeter_hint: uiPerimeterHint } : {}),
    }),
    [conversationId, responseDepth, uiPerimeterHint],
  );

  const onNewDiscussion = async () => {
    if (!canUseSend) return;
    try {
      setError(null);
      await bootstrapNewConversation(
        selectedContext || AXELIA_CONTEXT_ALL,
      );
      closeSidebarOnMobile();
    } catch {
      setError("Impossible de créer une discussion.");
    }
  };

  const onPickConversation = async (id) => {
    setConversationId(id);
    setMenuOpenId(null);
    closeSidebarOnMobile();
  };

  const onChangeContextDropdown = async (next) => {
    if (!canUseSend || next === selectedContext) return;
    const threadStarted =
      messages.length > 0 || loading || optimisticOutgoing != null;
    if (threadStarted) return;
    try {
      setError(null);
      setSelectedContext(next);
      await bootstrapNewConversation(next);
    } catch {
      setError("Impossible de changer de périmètre.");
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!canUseSend || loading) return;
    if (!conversationId) return;
    if (!text && !pendingFile) return;

    setError(null);

    const fileMime = (pendingFile?.type || "").toLowerCase();
    let optimisticImageUrl = null;
    if (pendingFile && isImageMime(fileMime)) {
      optimisticImageUrl = URL.createObjectURL(pendingFile);
    }

    let attachment = null;
    if (pendingFile) {
      try {
        const dataBase64 = await readFileAsBase64(pendingFile);
        attachment = {
          mime_type: fileMime || "application/octet-stream",
          data_base64: dataBase64,
        };
      } catch {
        if (optimisticImageUrl) URL.revokeObjectURL(optimisticImageUrl);
        setError("Impossible de lire le fichier.");
        return;
      }
    }

    const accountId =
      activeConversation?.account_context || selectedContext;

    // Snapshot pour pouvoir restaurer le textarea si l'envoi échoue.
    const inputSnapshot = input;
    const fileSnapshot = pendingFile;

    clearAttachment();
    setInput("");
    setOptimisticOutgoing({
      text,
      imagePreviewUrl: optimisticImageUrl,
      attachmentName: pendingFile?.name || null,
      attachmentMime: fileMime || null,
    });
    setLoading(true);

    const progressKey = generateRequestId();
    progressKeyRef.current = progressKey;
    setProgressInfo({ phase: "received" });
    setStreamingText("");
    setStreamingModel(null);

    const ctrl =
      typeof AbortController !== "undefined" ? new AbortController() : null;
    abortRef.current = ctrl;
    startProgressPolling();

    // États capturés pendant le stream pour usage post-`done` / `persisted`.
    let finalSkills = null;
    let finalPending = null;
    let finalAssistantId = null;
    let serverError = null;
    let cancelled = false;
    let tokensReceived = false;
    const depthForThisRequest = responseDepth;

    try {
      await streamAxeliaChat(
        {
          ...buildAxeliaBasePayload(accountId, progressKey),
          user_message: text,
          ...(toolsAvailable ? { sector: messageFocus } : {}),
          ...(attachment ? { attachment } : {}),
        },
        {
          signal: ctrl?.signal,
          onEvent: (name, data) => {
            if (name === "user-saved") {
              return;
            }
            if (name === "meta") {
              if (data?.model) setStreamingModel(data.model);
              setProgressInfo((prev) => ({ ...(prev || {}), ...data }));
              return;
            }
            if (name === "progress") {
              setProgressInfo((prev) => ({ ...(prev || {}), ...data }));
              return;
            }
            if (name === "token") {
              const chunk = data?.chunk || "";
              if (chunk) {
                tokensReceived = true;
                setStreamingText((prev) => (prev || "") + chunk);
              }
              return;
            }
            if (name === "done") {
              finalSkills = Array.isArray(data?.skills_used)
                ? data.skills_used
                : null;
              finalPending = Array.isArray(data?.pending_tool_calls)
                ? data.pending_tool_calls
                : null;
              if (data?.model) setStreamingModel(data.model);
              if (typeof data?.text === "string" && !tokensReceived) {
                // Voie skill-loop : pas de tokens streamés en amont, on affiche la
                // réponse complète d'un coup pour ne pas avoir un blanc avant `persisted`.
                setStreamingText(data.text);
              }
              return;
            }
            if (name === "persisted") {
              finalAssistantId = data?.assistant_message_id || null;
              return;
            }
            if (name === "error") {
              serverError = data || { code: "stream_error" };
              return;
            }
            if (name === "cancelled") {
              cancelled = true;
            }
          },
          onError: (err) => {
            if (err?.name === "AbortError") {
              cancelled = true;
              return;
            }
            serverError = {
              code: err?.detail || err?.message || "stream_failed",
              message: err?.message || "Erreur réseau pendant le streaming.",
            };
          },
        },
      );

      if (cancelled) {
        clearOptimisticOutgoing();
        if (inputSnapshot) setInput(inputSnapshot);
        if (fileSnapshot) {
          setPendingFile(fileSnapshot);
          setPendingPreviewUrl(
            isImageMime((fileSnapshot.type || "").toLowerCase())
              ? URL.createObjectURL(fileSnapshot)
              : null,
          );
        }
        setError("Génération annulée.");
        return;
      }
      if (serverError) {
        clearOptimisticOutgoing();
        if (inputSnapshot) setInput(inputSnapshot);
        if (fileSnapshot) {
          setPendingFile(fileSnapshot);
          setPendingPreviewUrl(
            isImageMime((fileSnapshot.type || "").toLowerCase())
              ? URL.createObjectURL(fileSnapshot)
              : null,
          );
        }
        const code = serverError.code;
        const msg =
          code === "gemini_not_configured"
            ? "Clé Gemini absente (GEMINI_API_KEY)."
            : code === "gemini_unavailable"
              ? "Service IA temporairement indisponible."
              : code === "account_context_mismatch"
                ? "Périmètre incohérent - change de conversation."
                : code === "axelia_tools_timeout"
                  ? "L’IA a mis trop longtemps (outils)."
                  : code === "attachment_unsupported_mime"
                    ? "Format de fichier non pris en charge (images et PDF uniquement)."
                    : code === "attachment_invalid_base64"
                      ? "Pièce jointe illisible."
                      : serverError.message || "Erreur lors de l’envoi.";
        setError(msg);
        return;
      }

      if (finalAssistantId) {
        if (Array.isArray(finalSkills) && finalSkills.length) {
          setSkillsByAssistId((prev) => ({
            ...prev,
            [finalAssistantId]: finalSkills,
          }));
        }
        if (Array.isArray(finalPending) && finalPending.length) {
          setPendingCreateByAssistId((prev) => ({
            ...prev,
            [finalAssistantId]: {
              calls: finalPending,
              expiresAt: Date.now() + PENDING_TOOLS_TTL_MS,
            },
          }));
        }
        setDepthByAssistId((prev) => ({
          ...prev,
          [finalAssistantId]: depthForThisRequest,
        }));
      }
      await loadMessages(conversationId);
      await reloadConversationsSynced();
      clearOptimisticOutgoing();
      armRegenCooldown();
    } catch (err) {
      clearOptimisticOutgoing();
      if (inputSnapshot) setInput(inputSnapshot);
      if (fileSnapshot) {
        setPendingFile(fileSnapshot);
        setPendingPreviewUrl(
          isImageMime((fileSnapshot.type || "").toLowerCase())
            ? URL.createObjectURL(fileSnapshot)
            : null,
        );
      }
      setError(err?.message || "Erreur lors de l’envoi.");
    } finally {
      cleanupInflight();
      setLoading(false);
      adjustTextarea();
    }
  };

  /** Annule la génération en cours côté UI ; côté serveur la requête FastAPI continue jusqu'à
   * l'API Gemini, mais on libère immédiatement l'utilisateur (et on restaure son brouillon). */
  const stopGeneration = useCallback(() => {
    const ctrl = abortRef.current;
    if (!ctrl) return;
    setAborting(true);
    try {
      ctrl.abort();
    } catch {
      /* noop */
    }
  }, []);

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
      const skillNames = calls.map(
        (c) => (c?.skill || c?.name || "").trim(),
      );
      const onlyBlocks =
        skillNames.length > 0 &&
        skillNames.every((n) => n === "meta_block_contact");
      setError(
        onlyBlocks
          ? "Choisis un compte WABA pour confirmer le blocage Meta."
          : "Choisis un compte WABA pour confirmer la création sur Meta.",
      );
      return;
    }
    setError(null);
    setLoading(true);
    const progressKey = generateRequestId();
    progressKeyRef.current = progressKey;
    setProgressInfo({ phase: "received" });
    setStreamingText("");
    setStreamingModel(null);

    const ctrl =
      typeof AbortController !== "undefined" ? new AbortController() : null;
    abortRef.current = ctrl;
    startProgressPolling();

    let finalAssistantId = null;
    let finalSkills = null;
    let serverError = null;
    let cancelled = false;
    let tokensReceived = false;
    const depthForThisRequest = responseDepth;

    try {
      await streamAxeliaChat(
        {
          ...buildAxeliaBasePayload(accountId, progressKey),
          user_message: "",
          sector: messageFocus,
          approve_tool_calls: calls,
        },
        {
          signal: ctrl?.signal,
          onEvent: (name, data) => {
            if (name === "meta") {
              if (data?.model) setStreamingModel(data.model);
              setProgressInfo((prev) => ({ ...(prev || {}), ...data }));
            } else if (name === "progress") {
              setProgressInfo((prev) => ({ ...(prev || {}), ...data }));
            } else if (name === "token") {
              const chunk = data?.chunk || "";
              if (chunk) {
                tokensReceived = true;
                setStreamingText((prev) => (prev || "") + chunk);
              }
            } else if (name === "done") {
              finalSkills = Array.isArray(data?.skills_used)
                ? data.skills_used
                : null;
              if (typeof data?.text === "string" && !tokensReceived) {
                setStreamingText(data.text);
              }
            } else if (name === "persisted") {
              finalAssistantId = data?.assistant_message_id || null;
            } else if (name === "error") {
              serverError = data || { code: "stream_error" };
            } else if (name === "cancelled") {
              cancelled = true;
            }
          },
          onError: (err) => {
            if (err?.name === "AbortError") {
              cancelled = true;
              return;
            }
            serverError = {
              code: err?.detail || err?.message || "stream_failed",
              message: err?.message || "Confirmation impossible.",
            };
          },
        },
      );

      if (cancelled) {
        setError("Confirmation annulée.");
        return;
      }
      if (serverError) {
        setError(
          typeof serverError.message === "string"
            ? serverError.message
            : "Confirmation impossible.",
        );
        return;
      }

      if (finalAssistantId && Array.isArray(finalSkills) && finalSkills.length) {
        setSkillsByAssistId((prev) => ({
          ...prev,
          [finalAssistantId]: finalSkills,
        }));
      }
      if (finalAssistantId) {
        setDepthByAssistId((prev) => ({
          ...prev,
          [finalAssistantId]: depthForThisRequest,
        }));
      }
      setPendingCreateByAssistId((prev) => {
        const n = { ...prev };
        delete n[assistMessageId];
        return n;
      });
      await loadMessages(conversationId);
      await reloadConversationsSynced();
      const skillNames = calls.map((c) => (c?.skill || c?.name || "").trim());
      const onlyBlocks =
        skillNames.length > 0 &&
        skillNames.every((n) => n === "meta_block_contact");
      showToast(onlyBlocks ? "Blocage confirmé" : "Action exécutée");
    } catch (err) {
      setError(err?.message || "Confirmation impossible.");
    } finally {
      cleanupInflight();
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
    if (!conversationId || loading || regenLocked) return;
    setLoading(true);
    setError(null);
    setProgressInfo({ phase: "received" });
    try {
      await postAxeliaRegenerate(conversationId);
      await loadMessages(conversationId);
      await reloadConversationsSynced();
      armRegenCooldown();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "string" ? d : "Régénération impossible.");
    } finally {
      setProgressInfo(null);
      setLoading(false);
    }
  };

  const copyText = async (t) => {
    try {
      await navigator.clipboard.writeText(t || "");
      showToast("Copié");
    } catch {
      setError("Copie impossible dans ce navigateur.");
    }
  };

  const togglePin = async (c) => {
    try {
      await patchAxeliaConversation(c.id, { pinned: !c.pinned });
      await reloadConversationsSynced();
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
      await reloadConversationsSynced();
    } catch {
      setError("Renommage impossible.");
    }
    setMenuOpenId(null);
  };

  const hideConv = async (c) => {
    if (!window.confirm("Supprimer cette discussion ?"))
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

  const hasThread =
    messages.length > 0 || loading || optimisticOutgoing != null;
  /** Compte / périmètre figé pour cette discussion une fois le fil démarré */
  const accountContextLocked = hasThread;
  const showSplash = !hasThread && !loading;

  const filteredConversations = useMemo(() => {
    const q = sidebarFilter.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) =>
      String(c?.title || "").toLowerCase().includes(q),
    );
  }, [conversations, sidebarFilter]);

  /** Texte affiché à côté de l'étoile pendant la génération (progression réelle si dispo). */
  const loadingHint = useMemo(() => {
    if (!loading) return null;
    if (aborting) return "Annulation…";
    if (progressInfo) {
      if (progressInfo.phase === "tool") {
        const rs = progressInfo.skills_running;
        if (Array.isArray(rs) && rs.length > 1) {
          return `${rs.length} vérifications en parallèle…`;
        }
        if (progressInfo.skill) {
          return (
            SKILL_RUNNING_LABELS[progressInfo.skill] ||
            `Outil : ${progressInfo.skill}…`
          );
        }
      }
      if (progressInfo.phase && PHASE_LABELS[progressInfo.phase]) {
        return PHASE_LABELS[progressInfo.phase];
      }
    }
    return "Réflexion…";
  }, [loading, aborting, progressInfo]);

  return (
    <div className="axelia-page">
      {toast ? (
        <div className="axelia-copy-toast" role="status">
          {toast.text}
        </div>
      ) : null}
      <header
        className={`axelia-topbar ${sidebarOpen ? "axelia-topbar--sidebar-open" : ""}`}
      >
        <div className="axelia-topbar__sidebar-strip" aria-hidden="true" />
        <div className="axelia-topbar__side">
          <div className="axelia-topbar__lead">
            <button
              type="button"
              className="axelia-topbar__iconbtn"
              id="axelia-discussions-menu-trigger"
              aria-label={
                sidebarOpen ? "Fermer les discussions" : "Ouvrir les discussions"
              }
              aria-expanded={sidebarOpen}
              aria-controls="axelia-discussions-sidebar"
              onClick={toggleSidebar}
            >
              <FiMenu size={22} aria-hidden />
            </button>
            {sidebarOpen ? (
              <span className="axelia-sidebar__title axelia-topbar__discussions-heading">
                Discussions
              </span>
            ) : null}
          </div>
        </div>
        <div className="axelia-topbar__center">
          <h1 className="axelia-topbar__title">{topbarConversationTitle}</h1>
        </div>
        <div className="axelia-topbar__side" aria-hidden="true" />
      </header>

      <div
        className={`axelia-shell ${sidebarOpen ? "axelia-shell--sidebar-open" : ""}`}
      >
        <aside
          id="axelia-discussions-sidebar"
          className={`axelia-sidebar ${sidebarOpen ? "axelia-sidebar--open" : ""}`}
          aria-hidden={!sidebarOpen}
        >
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
              <div className="axelia-sidebar__search">
                <FiSearch
                  className="axelia-sidebar__search-icon"
                  aria-hidden
                  size={16}
                />
                <input
                  type="search"
                  className="axelia-sidebar__search-input"
                  placeholder="Rechercher une discussion"
                  value={sidebarFilter}
                  onChange={(e) => setSidebarFilter(e.target.value)}
                  aria-label="Filtrer les discussions"
                />
              </div>
            </div>
            <div
              ref={sidebarListScrollRef}
              className="axelia-sidebar__list-scroll"
              onScroll={handleSidebarScroll}
            >
              {filteredConversations.map((c) => (
                <div
                  key={c.id}
                  data-axelia-conv-row={c.id}
                  className={`axelia-sidebar-row ${
                    c.id === conversationId ? "axelia-sidebar-row--active" : ""
                  }${
                    menuOpenId === c.id && sidebarMenuPopupAbove
                      ? " axelia-sidebar-row--popup-above"
                      : ""
                  }`}
                >
                  <div className="axelia-sidebar-row__track">
                    <button
                      type="button"
                      className="axelia-sidebar-row__pick"
                      aria-current={c.id === conversationId ? true : undefined}
                      onClick={() => onPickConversation(c.id)}
                    >
                      {c.pinned ? (
                        <span className="axelia-sidebar-row__pin" title="Épinglé">
                          📌{" "}
                        </span>
                      ) : null}
                      <span className="axelia-sidebar-row__title">
                        {c.title || "Sans titre"}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="axelia-sidebar-row__menu-trigger"
                      aria-label={`Options - ${c.title || "Sans titre"}`}
                      aria-haspopup="menu"
                      aria-expanded={menuOpenId === c.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId((prev) =>
                          prev === c.id ? null : c.id,
                        );
                      }}
                    >
                      <FiMoreHorizontal size={20} aria-hidden />
                    </button>
                  </div>
                  {menuOpenId === c.id ? (
                    <div className="axelia-sidebar-popup" role="menu">
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
                  ) : null}
                </div>
              ))}
              {!filteredConversations.length && (
                <p className="axelia-sidebar__empty">
                  {conversations.length === 0
                    ? "Aucune discussion"
                    : "Aucun résultat"}
                </p>
              )}
            </div>
          </div>
        </aside>

        <div className="axelia-chat-main">
          <div
            className="axelia-sidebar-overlay"
            aria-hidden="true"
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
              const msgDepth = depthByAssistId[m.id];
              const pendingEntry = pendingCreateByAssistId[m.id];
              const pendingCreates = pendingEntry?.calls || null;
              const pendingDesc = describePendingToolCalls(
                Array.isArray(pendingCreates) ? pendingCreates : [],
              );
              return (
                <div key={m.id} className="axelia-model-block">
                  <div className="axelia-model-line">
                    <SparkleGlyph animate={false} />
                    <div className="axelia-model-text">
                      {renderMarkdown(text)}
                    </div>
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
                      disabled={loading || regenLocked}
                      title={
                        regenLocked && !loading
                          ? "Patiente une seconde…"
                          : "Régénérer la réponse"
                      }
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
                    {m.model_used || msgDepth ? (
                      <div className="axelia-model-badges">
                        {m.model_used ? (
                          <span
                            className="axelia-model-badge"
                            title={`Modèle : ${m.model_used}`}
                          >
                            {toAxeliaModelLabel(m.model_used)}
                          </span>
                        ) : null}
                        {msgDepth ? (
                          <span
                            className="axelia-model-badge"
                            title={`Profondeur utilisée : ${msgDepth}`}
                          >
                            {toAxeliaDepthLabel(msgDepth)}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
            {optimisticOutgoing && (
              <div className="axelia-user-row" aria-live="polite">
                <div className="axelia-user-stack">
                  <div className="axelia-bubble axelia-bubble--user axelia-bubble--pending">
                    {optimisticOutgoing.imagePreviewUrl ? (
                      <img
                        src={optimisticOutgoing.imagePreviewUrl}
                        alt=""
                        className="axelia-bubble__pending-img"
                      />
                    ) : null}
                    {!optimisticOutgoing.imagePreviewUrl &&
                    optimisticOutgoing.attachmentName ? (
                      <span className="axelia-bubble__pending-file">
                        <FiFileText aria-hidden size={16} />
                        {optimisticOutgoing.attachmentName}
                      </span>
                    ) : null}
                    {optimisticOutgoing.text ? (
                      <span>{optimisticOutgoing.text}</span>
                    ) : null}
                  </div>
                </div>
              </div>
            )}
            {loading && Array.isArray(progressInfo?.todos) && progressInfo.todos.length ? (
              <AxeliaComposerPlan todos={progressInfo.todos} />
            ) : null}
            {loading && streamingText ? (
              <div
                className="axelia-model-block axelia-model-block--streaming"
                aria-live="polite"
              >
                <div className="axelia-model-line">
                  <SparkleGlyph animate />
                  <div className="axelia-model-text">
                    {renderMarkdown(streamingText)}
                    <span
                      className="axelia-stream-caret"
                      aria-hidden="true"
                    />
                  </div>
                </div>
                {streamingModel ? (
                  <div className="axelia-model-actions axelia-model-actions--streaming">
                    <div className="axelia-model-badges">
                      <span
                        className="axelia-model-badge"
                        title={`Modèle : ${streamingModel}`}
                      >
                        {toAxeliaModelLabel(streamingModel)}
                      </span>
                      <span
                        className="axelia-model-badge"
                        title={`Profondeur active : ${responseDepth}`}
                      >
                        {toAxeliaDepthLabel(responseDepth)}
                      </span>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
            {loading && !streamingText && (
              <div className="axelia-model-block">
                <div className="axelia-model-line">
                  <SparkleGlyph animate />
                  <div className="axelia-model-text axelia-model-text--muted">
                    {loadingHint || "Réflexion…"}
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
              accept={ATTACHMENT_ACCEPT}
              className="axelia-file-input"
              onChange={handleFileChange}
            />

            {!canUseSend && accessibleAccounts.length === 0 && accounts.length > 0 && (
              <p className="axelia-error axelia-error--dock">
                Aucun compte accessible pour les conversations.
              </p>
            )}

            <div className="axelia-input-card">
              {pendingFile && (
                <div className="axelia-attach-preview">
                  {pendingPreviewUrl ? (
                    <img src={pendingPreviewUrl} alt="" />
                  ) : (
                    <span
                      className="axelia-attach-preview__icon"
                      aria-hidden
                    >
                      <FiFileText size={20} />
                    </span>
                  )}
                  <span className="axelia-attach-preview__name">
                    {pendingFile.name}
                  </span>
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
                  {accountContextLocked ? (
                    <span
                      className="axelia-context-select axelia-context-select--readonly"
                      title="Le compte est fixé pour cette discussion."
                      aria-label={`Compte pour cette discussion : ${contextSelectLabel}`}
                      style={{
                        ...(contextSelectWidthPx != null && {
                          width: contextSelectWidthPx,
                        }),
                      }}
                    >
                      {contextSelectLabel}
                    </span>
                  ) : (
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
                      onChange={(e) =>
                        onChangeContextDropdown(e.target.value)
                      }
                      disabled={
                        loading || accessibleAccounts.length === 0
                      }
                    >
                      <option value={AXELIA_CONTEXT_ALL}>
                        Tous les comptes
                      </option>
                      {accessibleAccounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name || a.phone_number || a.id}
                        </option>
                      ))}
                    </select>
                  )}
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
                    aria-label="Profondeur de réponse"
                    value={responseDepth}
                    onChange={(e) => setResponseDepth(e.target.value)}
                    disabled={loading}
                    title="Niveau de détail de la réponse"
                  >
                    {AXELIA_RESPONSE_DEPTHS.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                  {loading ? (
                    <button
                      type="button"
                      className="axelia-send-btn axelia-send-btn--stop"
                      onClick={stopGeneration}
                      disabled={aborting || !abortRef.current}
                      title="Arrêter la génération"
                      aria-label="Arrêter la génération"
                    >
                      <FiSquare
                        aria-hidden
                        size={18}
                        className="axelia-send-btn__svg"
                      />
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="axelia-send-btn"
                      disabled={
                        (!input.trim() && !pendingFile) || !canUseSend
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
                  )}
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
