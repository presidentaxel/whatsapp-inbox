import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiX, FiSend, FiLoader, FiZap, FiRefreshCw } from "react-icons/fi";
import { getMessages } from "../../api/messagesApi";
import {
  ensurePlaygroundSandboxSession,
  getPlaygroundFlow,
  resetPlaygroundSandboxSession,
  simulatePlaygroundCampaignLaunch,
  simulatePlaygroundInbound,
  simulatePlaygroundInboundBatch,
} from "../../api/playgroundFlowsApi";
import { listTemplates } from "../../api/whatsappApi";
import { supabaseClient } from "../../api/supabaseClient";
import { formatRelativeDateTime } from "../../utils/date";
import { formatPlaygroundApiError } from "./playgroundGraphValidation";

function msgTime(m) {
  const ts = m.timestamp || m.created_at;
  if (!ts) return "";
  try {
    return formatRelativeDateTime(ts);
  } catch {
    return "";
  }
}

function sortMessages(items) {
  return [...items].sort((a, b) => {
    const ta = new Date(a.timestamp || a.created_at || 0).getTime();
    const tb = new Date(b.timestamp || b.created_at || 0).getTime();
    return ta - tb;
  });
}

/** Webhooks Meta (statuts d’envoi) : pas utiles dans le fil de test sandbox. */
function isHiddenSandboxNoiseMessage(msg) {
  if (!msg) return true;
  if (msg.is_system === true) return true;
  const type = (msg.message_type || "").toLowerCase();
  if (["reaction", "status"].includes(type)) return true;
  const ct = String(msg.content_text ?? "").trim();
  const ctLo = ct.toLowerCase();
  if (ctLo === "[status update]") return true;
  if (ctLo.startsWith("[status")) return true;
  return false;
}

function normalizeMessagesResponse(res) {
  const raw = res?.data;
  if (Array.isArray(raw)) return raw;
  if (raw && Array.isArray(raw.data)) return raw.data;
  if (raw && Array.isArray(raw.messages)) return raw.messages;
  return [];
}

function findPlaygroundAudienceEntryId(nodes) {
  if (!Array.isArray(nodes)) return null;
  for (const n of nodes) {
    if (n?.type === "start" && n?.data?.triggerType === "playground_audience") {
      return n.id || null;
    }
  }
  return null;
}

function parseSandboxTemplateContent(contentText) {
  if (!contentText || typeof contentText !== "string") return null;
  const lines = contentText.split(/\r?\n/);
  const first = (lines[0] || "").trim();
  const m = /^\[Template sandbox\]\s+(.+?)\s+\(([^)]+)\)\s*$/.exec(first);
  if (!m) return null;
  const templateName = (m[1] || "").trim();
  const language = (m[2] || "").trim();
  const paramLines = lines
    .slice(1)
    .map((l) => l.trim())
    .filter(Boolean);
  return { templateName, language, paramLines };
}

function findTemplateMatch(templates, name, language) {
  if (!templates?.length || !name) return null;
  const lang = (language || "").toLowerCase();
  let t = templates.find(
    (x) => x.name === name && (x.language || "").toLowerCase() === lang
  );
  if (!t) t = templates.find((x) => x.name === name);
  return t || null;
}

function parseMessageOutboundMeta(message) {
  const om = message?.outbound_meta;
  if (om == null) return null;
  if (typeof om === "object") return om;
  if (typeof om === "string") {
    try {
      return JSON.parse(om);
    } catch {
      return null;
    }
  }
  return null;
}

/** Message interactif enregistré côté sandbox (_send_interactive_sandbox_internal). */
function parseSandboxInteractivePayload(message) {
  const raw = message?.interactive_data;
  if (raw == null) return null;
  let d = raw;
  if (typeof raw === "string") {
    try {
      d = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!d || typeof d !== "object") return null;
  const body = typeof d.body === "string" ? d.body : message.content_text || "";
  const header = typeof d.header === "string" ? d.header : null;
  const footer = typeof d.footer === "string" ? d.footer : null;
  const itype = (d.type || "").toLowerCase();
  const action = d.action || {};
  const out = {
    kind: itype === "list" ? "list" : "button",
    header,
    footer,
    body,
    listButtonText: typeof action.button === "string" ? action.button : null,
    rows: [],
    buttons: [],
  };
  if (out.kind === "button" && Array.isArray(action.buttons)) {
    out.buttons = action.buttons
      .filter((b) => b && typeof b === "object")
      .map((b) => {
        const reply = b.reply || {};
        const title = String(reply.title || b.title || "").trim();
        const id = String(reply.id || b.id || title).trim();
        return { id, title };
      })
      .filter((b) => b.title);
  }
  if (out.kind === "list" && Array.isArray(action.sections)) {
    for (const sec of action.sections) {
      const rows = Array.isArray(sec?.rows) ? sec.rows : [];
      for (const row of rows) {
        if (!row || typeof row !== "object") continue;
        const title = String(row.title || "").trim();
        const id = String(row.id || title).trim();
        if (title) out.rows.push({ id, title, description: row.description || "" });
      }
    }
  }
  return out;
}

function substituteTemplateBody(bodyText, paramLines) {
  if (!bodyText || !paramLines?.length) return bodyText;
  let out = bodyText;
  paramLines.forEach((val, i) => {
    const re = new RegExp(`\\{\\{${i + 1}\\}\\}`, "g");
    out = out.replace(re, val);
  });
  return out;
}

/** Message sortant template bac à sable : pas de bandeau « Scénario / compte » au-dessus de la carte. */
function isOutboundSandboxTemplateMessage(m) {
  if (!m) return false;
  const inbound =
    m.direction === "inbound" || (!m.from_me && m.direction !== "outbound");
  if (inbound) return false;
  const raw = m.content_text ?? "";
  const mt = (m.message_type || "").toLowerCase();
  if (mt === "template") return true;
  if (raw.includes("[Template sandbox]")) return true;
  return false;
}

function getMetaTemplateButtonKind(b) {
  const t = String(b?.type || "").toUpperCase();
  if (t.includes("URL")) return "url";
  if (t.includes("PHONE")) return "phone";
  return "quick";
}

function SandboxMessageBody({
  message,
  metaTemplates,
  onTemplateButtonReply,
  templateActionsDisabled,
}) {
  const raw = message.content_text ?? "";
  const mt = (message.message_type || "").toLowerCase();

  const triggerReply = (title, buttonId) => {
    const t = String(title || "").trim();
    if (!t || !onTemplateButtonReply || templateActionsDisabled) return;
    const bid = String(buttonId || t).trim();
    onTemplateButtonReply(t, bid);
  };

  if (mt === "interactive") {
    const ix = parseSandboxInteractivePayload(message);
    const hasIx =
      ix &&
      (ix.body ||
        ix.header ||
        ix.footer ||
        ix.buttons.length > 0 ||
        ix.rows.length > 0);
    if (hasIx) {
      return (
        <div className="playground-waba-tpl">
          <div className="playground-waba-tpl__card">
            {ix.header ? (
              <div className="playground-waba-tpl__header">{ix.header}</div>
            ) : null}
            {ix.body ? <div className="playground-waba-tpl__body">{ix.body}</div> : null}
            {ix.footer ? (
              <div className="playground-waba-tpl__footer">{ix.footer}</div>
            ) : null}
            {ix.kind === "list" && ix.listButtonText ? (
              <div className="playground-waba-tpl__list-pill">
                <span className="playground-waba-tpl__list-pill-text">{ix.listButtonText}</span>
              </div>
            ) : null}
            {ix.buttons.length > 0 ? (
              <div className="playground-waba-tpl__actions" role="list">
                {ix.buttons.map((b, i) => (
                  <button
                    key={`${b.id}-${i}`}
                    type="button"
                    className="playground-waba-tpl__action"
                    role="listitem"
                    disabled={templateActionsDisabled}
                    onClick={() => triggerReply(b.title, b.id)}
                  >
                    <span className="playground-waba-tpl__action-label">{b.title}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {ix.rows.length > 0 ? (
              <div className="playground-waba-tpl__actions playground-waba-tpl__actions--stack" role="list">
                {ix.rows.map((r, i) => (
                  <button
                    key={`${r.id}-${i}`}
                    type="button"
                    className="playground-waba-tpl__action playground-waba-tpl__action--row"
                    role="listitem"
                    disabled={templateActionsDisabled}
                    onClick={() => triggerReply(r.title, r.id)}
                  >
                    <span className="playground-waba-tpl__action-label">{r.title}</span>
                    {r.description ? (
                      <span className="playground-waba-tpl__action-desc">{r.description}</span>
                    ) : null}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      );
    }
  }

  const parsed =
    mt === "template" || raw.includes("[Template sandbox]")
      ? parseSandboxTemplateContent(raw)
      : null;

  if (!parsed) {
    return (
      <div className="playground-sandbox-bubble__text">
        {raw || (mt === "interactive" ? "[Interactif]" : "")}
      </div>
    );
  }

  const om = parseMessageOutboundMeta(message);
  const tpl = findTemplateMatch(metaTemplates, parsed.templateName, parsed.language);
  const bodyComp = tpl?.components?.find((c) => c.type === "BODY");
  const bodyText = bodyComp?.text || "";
  const previewBody = substituteTemplateBody(bodyText, parsed.paramLines);
  const headerComp = tpl?.components?.find((c) => c.type === "HEADER");
  const footerComp = tpl?.components?.find((c) => c.type === "FOOTER");
  const buttonsComp = tpl?.components?.find((c) => c.type === "BUTTONS");
  let buttons = Array.isArray(buttonsComp?.buttons) ? [...buttonsComp.buttons] : [];
  if (!buttons.length && Array.isArray(om?.quick_reply_buttons) && om.quick_reply_buttons.length) {
    buttons = om.quick_reply_buttons;
  }

  const fallbackBody =
    previewBody ||
    (parsed.paramLines.length ? parsed.paramLines.filter(Boolean).join("\n") : "");

  const handleMetaButton = (b) => {
    const label = String(b.text || b.title || "").trim();
    if (!label) return;
    triggerReply(label, b.id || b.payload || label);
  };

  const showWabaCard =
    tpl &&
    (fallbackBody ||
      headerComp?.text ||
      footerComp?.text ||
      buttons.length > 0);
  const showSimulatedCard =
    !tpl &&
    (fallbackBody || (Array.isArray(om?.quick_reply_buttons) && om.quick_reply_buttons.length > 0));

  if (showWabaCard || showSimulatedCard) {
    return (
      <div className="playground-waba-tpl">
        <div className="playground-waba-tpl__card">
          {headerComp?.text ? (
            <div className="playground-waba-tpl__header">{headerComp.text}</div>
          ) : null}
          {fallbackBody ? (
            <div className="playground-waba-tpl__body">{fallbackBody}</div>
          ) : null}
          {footerComp?.text ? (
            <div className="playground-waba-tpl__footer">{footerComp.text}</div>
          ) : null}
          {buttons.length > 0 ? (
            <div className="playground-waba-tpl__actions" role="list">
              {buttons.map((b, i) => {
                const label = b.text || b.title || b.type || "-";
                const kind = getMetaTemplateButtonKind(b);
                const key = `${i}-${label}`;
                if (kind === "url" && b.url) {
                  const href = String(b.url).startsWith("http")
                    ? b.url
                    : `https://${b.url}`;
                  return (
                    <a
                      key={key}
                      className="playground-waba-tpl__action playground-waba-tpl__action--link"
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      role="listitem"
                    >
                      <span className="playground-waba-tpl__action-label">{label}</span>
                      <span className="playground-waba-tpl__action-hint">Lien</span>
                    </a>
                  );
                }
                if (kind === "phone" && (b.phone_number || b.phoneNumber)) {
                  const tel = String(b.phone_number || b.phoneNumber).replace(/\s/g, "");
                  return (
                    <a
                      key={key}
                      className="playground-waba-tpl__action playground-waba-tpl__action--link"
                      href={`tel:${tel}`}
                      role="listitem"
                    >
                      <span className="playground-waba-tpl__action-label">{label}</span>
                    </a>
                  );
                }
                return (
                  <button
                    key={key}
                    type="button"
                    className="playground-waba-tpl__action"
                    role="listitem"
                    disabled={templateActionsDisabled}
                    onClick={() => handleMetaButton(b)}
                  >
                    <span className="playground-waba-tpl__action-label">{label}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="playground-waba-tpl playground-waba-tpl--fallback">
      <div className="playground-waba-tpl__card">
        <div className="playground-waba-tpl__body playground-waba-tpl__body--mono">{raw}</div>
      </div>
    </div>
  );
}

/**
 * Fenêtre de test du scénario : conversation bac à sable (numéro réservé) dans le Playground uniquement.
 * Les messages « contact » passent par simulate-inbound (même pipeline que la prod).
 */
export default function PlaygroundSandboxTestModal({
  open,
  onClose,
  accountId,
  flowId,
  flowName,
  onBeforeOpen,
  /** Nœuds du graphe ouvert dans l’éditeur (prioritaire pour détecter « Campagne planifiée »). */
  graphNodes = null,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [apiCampaignEntryId, setApiCampaignEntryId] = useState(null);
  const [campaignLaunching, setCampaignLaunching] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [metaTemplates, setMetaTemplates] = useState([]);
  const [lastFlowTrace, setLastFlowTrace] = useState(null);
  const [batchPhrases, setBatchPhrases] = useState("");
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchResults, setBatchResults] = useState(null);
  const listEndRef = useRef(null);
  const channelRef = useRef(null);
  /** Toujours l’id courant (évite closures obsolètes après simulate-* qui vident le fil). */
  const conversationIdRef = useRef(null);

  const conversationId = conversation?.id;

  useEffect(() => {
    conversationIdRef.current = conversationId ?? null;
  }, [conversationId]);

  const campaignEntryNodeId = useMemo(() => {
    const fromGraph = findPlaygroundAudienceEntryId(graphNodes);
    if (fromGraph) return fromGraph;
    return apiCampaignEntryId;
  }, [graphNodes, apiCampaignEntryId]);

  const loadMessages = useCallback(async (overrideConversationId) => {
    const cid =
      overrideConversationId ?? conversationIdRef.current ?? undefined;
    if (!cid) {
      setMessages([]);
      return;
    }
    try {
      const res = await getMessages(cid, { limit: 200 });
      const rows = normalizeMessagesResponse(res).filter(
        (msg) => !isHiddenSandboxNoiseMessage(msg)
      );
      setMessages(sortMessages(rows));
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [open, messages.length]);

  useEffect(() => {
    if (!open || !conversationId) return;

    const channel = supabaseClient
      .channel(`pg-sandbox-${conversationId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload) => {
          const incoming = payload.new;
          if (isHiddenSandboxNoiseMessage(incoming)) return;
          setMessages((prev) => {
            const iid = String(incoming.id ?? "");
            if (prev.some((m) => String(m.id ?? "") === iid)) {
              return prev.map((m) =>
                String(m.id ?? "") === iid ? incoming : m
              );
            }
            return sortMessages([...prev, incoming]);
          });
        }
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload) => {
          const updated = payload.new;
          setMessages((prev) => {
            const uid = String(updated.id ?? "");
            if (isHiddenSandboxNoiseMessage(updated)) {
              return prev.filter((m) => String(m.id ?? "") !== uid);
            }
            return prev.map((m) =>
              String(m.id ?? "") === uid ? updated : m
            );
          });
        }
      )
      .subscribe();

    channelRef.current = channel;
    return () => {
      supabaseClient.removeChannel(channel);
      channelRef.current = null;
    };
  }, [open, conversationId]);

  useEffect(() => {
    if (!open) {
      conversationIdRef.current = null;
      setConversation(null);
      setMessages([]);
      setError(null);
      setDraft("");
      setLoading(false);
      setApiCampaignEntryId(null);
      setCampaignLaunching(false);
      setResetting(false);
      setMetaTemplates([]);
      return;
    }

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (typeof onBeforeOpen === "function") {
          await onBeforeOpen();
        }
        const res = await ensurePlaygroundSandboxSession(flowId, {
          account_id: accountId,
        });
        if (cancelled) return;
        const conv = res.data?.conversation;
        if (!conv?.id) {
          setError("Conversation de test indisponible.");
          conversationIdRef.current = null;
          setConversation(null);
          return;
        }
        conversationIdRef.current = conv.id;
        setConversation(conv);
        const mid = conv.id;
        const [mr, flowRes, tplRes] = await Promise.all([
          getMessages(mid, { limit: 200 }),
          getPlaygroundFlow(flowId).catch(() => null),
          listTemplates(accountId, { limit: 500 }).catch(() => null),
        ]);
        if (cancelled) return;
        const rows = normalizeMessagesResponse(mr).filter(
          (msg) => !isHiddenSandboxNoiseMessage(msg)
        );
        setMessages(sortMessages(rows));

        const nodes = flowRes?.data?.graph?.nodes;
        setApiCampaignEntryId(findPlaygroundAudienceEntryId(nodes) || null);
        const rawT = tplRes?.data?.data ?? tplRes?.data ?? [];
        setMetaTemplates(Array.isArray(rawT) ? rawT : []);
      } catch (e) {
        if (!cancelled) {
          setError(formatPlaygroundApiError(e));
          conversationIdRef.current = null;
          setConversation(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, accountId, flowId, onBeforeOpen]);

  const title = useMemo(() => {
    const n = (flowName || "").trim();
    return n ? `Test · ${n}` : "Test du scénario";
  }, [flowName]);

  const sendSimulatedInbound = useCallback(async () => {
    const text = draft.trim();
    const cid = conversationIdRef.current;
    if (!text || !flowId || !accountId || sending || !cid) return;
    setSending(true);
    setError(null);
    try {
      const res = await simulatePlaygroundInbound(flowId, {
        account_id: accountId,
        conversation_id: cid,
        message_text: text,
      });
      setLastFlowTrace(res?.data?.flow_trace ?? null);
      setDraft("");
      await loadMessages(cid);
    } catch (e) {
      setError(formatPlaygroundApiError(e));
    } finally {
      setSending(false);
    }
  }, [draft, flowId, accountId, sending, loadMessages]);

  const sendSimulatedButtonReply = useCallback(
    async (title, buttonId) => {
      const t = (title || "").trim();
      const cid = conversationIdRef.current;
      if (!t || !flowId || !accountId || sending || !cid) return;
      setSending(true);
      setError(null);
      try {
        const res = await simulatePlaygroundInbound(flowId, {
          account_id: accountId,
          conversation_id: cid,
          message_text: t,
          button_reply: {
            id: (buttonId || t).trim(),
            title: t,
          },
        });
        setLastFlowTrace(res?.data?.flow_trace ?? null);
        await loadMessages(cid);
      } catch (e) {
        setError(formatPlaygroundApiError(e));
      } finally {
        setSending(false);
      }
    },
    [flowId, accountId, sending, loadMessages]
  );

  const sendCampaignLaunch = useCallback(async () => {
    const cid = conversationIdRef.current;
    if (!campaignEntryNodeId || !flowId || !accountId || campaignLaunching || !cid) {
      return;
    }
    setCampaignLaunching(true);
    setError(null);
    try {
      const res = await simulatePlaygroundCampaignLaunch(flowId, {
        account_id: accountId,
        conversation_id: cid,
        entry_node_id: campaignEntryNodeId,
      });
      setLastFlowTrace(res?.data?.flow_trace ?? null);
      const resolvedCid = res?.data?.conversation_id || cid;
      await loadMessages(resolvedCid);
      await new Promise((r) => setTimeout(r, 250));
      await loadMessages(resolvedCid);
    } catch (e) {
      setError(formatPlaygroundApiError(e));
    } finally {
      setCampaignLaunching(false);
    }
  }, [
    campaignEntryNodeId,
    flowId,
    accountId,
    campaignLaunching,
    loadMessages,
  ]);

  const runPhraseBatch = useCallback(async () => {
    const cid = conversationIdRef.current;
    if (!cid || !flowId || !accountId || batchRunning) return;
    const lines = batchPhrases
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    if (!lines.length) return;
    setBatchRunning(true);
    setError(null);
    try {
      const res = await simulatePlaygroundInboundBatch(flowId, {
        account_id: accountId,
        conversation_id: cid,
        phrases: lines,
      });
      const results = res?.data?.results ?? [];
      setBatchResults(results);
      const lastWithTrace = [...results].reverse().find((r) => r?.flow_trace?.length);
      if (lastWithTrace?.flow_trace) {
        setLastFlowTrace(lastWithTrace.flow_trace);
      }
      await loadMessages(cid);
    } catch (e) {
      setError(formatPlaygroundApiError(e));
    } finally {
      setBatchRunning(false);
    }
  }, [batchPhrases, flowId, accountId, batchRunning, loadMessages]);

  const resetSession = useCallback(async () => {
    if (!flowId || !accountId || resetting) return;
    setResetting(true);
    setError(null);
    setLastFlowTrace(null);
    setBatchResults(null);
    setBatchPhrases("");
    try {
      const rr = await resetPlaygroundSandboxSession(flowId, {
        account_id: accountId,
      });
      const conv = rr.data?.conversation;
      if (conv?.id) {
        conversationIdRef.current = conv.id;
        setConversation(conv);
        await loadMessages(conv.id);
      } else {
        await loadMessages();
      }
    } catch (e) {
      setError(formatPlaygroundApiError(e));
    } finally {
      setResetting(false);
    }
  }, [flowId, accountId, resetting, loadMessages]);

  if (!open) return null;

  return (
    <div
      className="playground-modal-overlay playground-sandbox-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="playground-sandbox-title"
      onClick={onClose}
    >
      <div
        className="playground-sandbox-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="playground-sandbox-modal__head">
          <div>
            <h2 id="playground-sandbox-title" className="playground-sandbox-modal__title">
              {title}
            </h2>
            <div className="playground-sandbox-modal__head-actions">
              <button
                type="button"
                className="playground-btn playground-btn--compact playground-sandbox-modal__reset-btn"
                disabled={loading || resetting || !conversation}
                onClick={() => void resetSession()}
              >
                {resetting ? (
                  <FiLoader className="playground-sandbox-modal__spin" aria-hidden />
                ) : (
                  <FiRefreshCw aria-hidden />
                )}
                <span>Nouvelle session de test</span>
              </button>
            </div>
          </div>
          <button
            type="button"
            className="playground-sandbox-modal__close"
            aria-label="Fermer"
            onClick={onClose}
          >
            <FiX aria-hidden />
          </button>
        </header>

        <div className="playground-sandbox-modal__body">
          {loading ? (
            <div className="playground-sandbox-modal__loading">
              <FiLoader className="playground-sandbox-modal__spin" aria-hidden />
              <span>Préparation de la session de test…</span>
            </div>
          ) : error && !conversation ? (
            <p className="playground-assist__banner" role="alert">
              {error}
            </p>
          ) : (
            <>
              <div className="playground-sandbox-thread" role="log" aria-live="polite">
                {messages.length === 0 ? (
                  <p className="muted playground-sandbox-thread__empty">
                    {campaignEntryNodeId
                      ? "Pour un déclencheur « Campagne planifiée », utilisez le bouton ci-dessous, ou envoyez un message comme un contact."
                      : "Envoyez un message du type « contact » pour déclencher le scénario (mot-clé, salut, etc.)."}
                  </p>
                ) : (
                  messages.map((m) => {
                    const inbound =
                      m.direction === "inbound" || (!m.from_me && m.direction !== "outbound");
                    const hideBubbleMeta = !inbound && isOutboundSandboxTemplateMessage(m);
                    const actionsBusy =
                      sending || loading || resetting || campaignLaunching;
                    return (
                      <div
                        key={m.id}
                        className={`playground-sandbox-bubble ${
                          inbound
                            ? "playground-sandbox-bubble--in"
                            : "playground-sandbox-bubble--out"
                        }`}
                      >
                        {!hideBubbleMeta ? (
                          <div className="playground-sandbox-bubble__meta">
                            {inbound ? "Contact (simulé)" : "Scénario / compte"}
                            <span className="playground-sandbox-bubble__time">{msgTime(m)}</span>
                          </div>
                        ) : null}
                        <SandboxMessageBody
                          message={m}
                          metaTemplates={metaTemplates}
                          onTemplateButtonReply={sendSimulatedButtonReply}
                          templateActionsDisabled={actionsBusy}
                        />
                      </div>
                    );
                  })
                )}
                <div ref={listEndRef} />
              </div>
              {error ? (
                <p className="playground-assist__banner" role="alert">
                  {error}
                </p>
              ) : null}
            </>
          )}
        </div>

        <footer className="playground-sandbox-modal__footer">
          {conversation && !loading && !campaignEntryNodeId ? (
            <p className="playground-sandbox-modal__campaign-hint muted" role="note">
              Entrée campagne : ajoutez un nœud Entrée dont le type est « Campagne planifiée » dans le graphe
              (le test utilise le canevas actuel, même non enregistré).
            </p>
          ) : null}
          {campaignEntryNodeId && conversation ? (
            <div className="playground-sandbox-modal__campaign">
              <button
                type="button"
                className="playground-btn playground-sandbox-modal__campaign-btn"
                disabled={loading || campaignLaunching || resetting}
                onClick={() => void sendCampaignLaunch()}
              >
                {campaignLaunching ? (
                  <FiLoader className="playground-sandbox-modal__spin" aria-hidden />
                ) : (
                  <FiZap aria-hidden />
                )}
                <span>Simuler l&apos;entrée campagne (sans message contact)</span>
              </button>
            </div>
          ) : null}
          {conversation && !loading ? (
            <div className="playground-sandbox-modal__batch">
              <label
                className="playground-sandbox-modal__label"
                htmlFor="playground-sandbox-batch"
              >
                Phrases de test (une par ligne)
              </label>
              <textarea
                id="playground-sandbox-batch"
                className="playground-sandbox-modal__textarea playground-sandbox-modal__textarea--batch"
                rows={3}
                placeholder={"Bonjour\nJe veux louer une voiture\nJ'ai une panne"}
                value={batchPhrases}
                disabled={loading || resetting || batchRunning}
                onChange={(e) => setBatchPhrases(e.target.value)}
              />
              <button
                type="button"
                className="playground-btn playground-btn--compact playground-sandbox-modal__batch-btn"
                disabled={
                  loading ||
                  !conversation ||
                  batchRunning ||
                  !batchPhrases.trim()
                }
                onClick={() => void runPhraseBatch()}
              >
                {batchRunning ? (
                  <FiLoader className="playground-sandbox-modal__spin" aria-hidden />
                ) : null}
                <span>Enchaîner les simulations</span>
              </button>
              {batchResults && batchResults.length > 0 ? (
                <details className="playground-sandbox-batch-results">
                  <summary className="playground-sandbox-batch-results__summary">
                    Résultats du lot ({batchResults.filter((r) => r.ok).length}/
                    {batchResults.length} OK)
                  </summary>
                  <ul className="playground-sandbox-batch-results__list">
                    {batchResults.map((r, i) => (
                      <li
                        key={i}
                        className={
                          r.ok ? "playground-sandbox-batch-results__li is-ok" : "playground-sandbox-batch-results__li is-err"
                        }
                      >
                        <span className="playground-sandbox-batch-results__phrase">
                          {r.message_text}
                        </span>
                        {r.error ? (
                          <span className="playground-sandbox-batch-results__err">
                            {r.error}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </div>
          ) : null}
          <label className="playground-sandbox-modal__label" htmlFor="playground-sandbox-input">
            Message entrant simulé
          </label>
          <div className="playground-sandbox-modal__composer">
            <textarea
              id="playground-sandbox-input"
              className="playground-sandbox-modal__textarea"
              rows={2}
              placeholder="Ex. Bonjour, ou le mot-clé de votre déclencheur…"
              value={draft}
              disabled={loading || !conversation || sending}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void sendSimulatedInbound();
                }
              }}
            />
            <button
              type="button"
              className="playground-btn playground-btn--primary playground-sandbox-modal__send"
              disabled={loading || !conversation || sending || !draft.trim()}
              onClick={() => void sendSimulatedInbound()}
            >
              {sending ? <FiLoader className="playground-sandbox-modal__spin" aria-hidden /> : <FiSend aria-hidden />}
              <span>Simuler</span>
            </button>
          </div>
          {lastFlowTrace && lastFlowTrace.length > 0 ? (
            <details className="playground-sandbox-trace">
              <summary className="playground-sandbox-trace__summary">
                Trace du moteur ({lastFlowTrace.length} événements)
              </summary>
              <pre className="playground-sandbox-trace__pre">
                {JSON.stringify(lastFlowTrace, null, 2)}
              </pre>
            </details>
          ) : null}
        </footer>
      </div>
    </div>
  );
}
