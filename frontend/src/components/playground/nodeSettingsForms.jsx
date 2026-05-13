import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getBroadcastGroups } from "../../api/broadcastApi";
import { getConversations } from "../../api/conversationsApi";
import { schedulePlaygroundFlowLaunch } from "../../api/playgroundFlowsApi";
import { VarListContext, TemplatesContext, FlushSaveContext } from "./flowContext";
import {
  WEEKDAYS,
  collectVarIdsFromTemplate,
  extractQuickReplyButtons,
  toggleDay,
  DEFAULT_GEMINI_STATUT_ROUTER_PROMPT,
  describeWaitUntilConfiguredState,
  untilToDatetimeLocalInputValue,
} from "./nodeShared";

function NodeVarLine({ varKey, nodeId, patch }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(varKey || "");

  useEffect(() => {
    setDraft(varKey || "");
  }, [varKey]);

  if (!varKey) return null;

  const commitRename = () => {
    const cleaned = draft.trim().replace(/\s+/g, "_");
    if (cleaned && cleaned !== varKey && nodeId && patch) {
      patch(nodeId, { varKey: cleaned });
    }
    setEditing(false);
  };

  return (
    <div className="pg-modal__var">
      {editing && nodeId && patch ? (
        <span className="pg-modal__var-edit">
          <code>{"{{ "}</code>
          <input
            className="pg-modal__var-input"
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") {
                setDraft(varKey);
                setEditing(false);
              }
            }}
            autoFocus
          />
          <code>{" }}"}</code>
        </span>
      ) : (
        <code
          className={nodeId && patch ? "pg-modal__var-clickable" : ""}
          onClick={() => {
            if (nodeId && patch) setEditing(true);
          }}
          title={nodeId && patch ? "Cliquer pour renommer la variable" : undefined}
        >
          {`{{${varKey}}}`}
        </code>
      )}
    </div>
  );
}

function localDatetimeInputToUtcIso(value) {
  if (!value || !String(value).trim()) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function audienceScopeFromData(data) {
  const s = (data.playgroundAudienceScope || "").trim().toLowerCase();
  if (s === "all" || s === "group" || s === "phones") return s;
  return (data.audienceBroadcastGroupId || "").trim() ? "group" : "all";
}

/** Qui peut activer le scénario (message entrant + campagne) : tout le monde, groupe, ou contacts précis. */
function StartAudienceScopeBlock({ id, data, patch, accountId }) {
  const [groups, setGroups] = useState([]);
  const [conversations, setConversations] = useState([]);
  const scope = audienceScopeFromData(data);
  const groupId = data.audienceBroadcastGroupId ?? "";
  const selectedPhones = Array.isArray(data.playgroundAudiencePhones)
    ? data.playgroundAudiencePhones
    : [];

  useEffect(() => {
    if (!accountId) {
      setGroups([]);
      return;
    }
    let cancelled = false;
    getBroadcastGroups(accountId)
      .then((res) => {
        if (!cancelled) setGroups(Array.isArray(res.data) ? res.data : []);
      })
      .catch(() => {
        if (!cancelled) setGroups([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  useEffect(() => {
    if (!accountId || scope !== "phones") {
      setConversations([]);
      return;
    }
    let cancelled = false;
    getConversations(accountId, { limit: 200 })
      .then((res) => {
        const rows = Array.isArray(res.data) ? res.data : [];
        if (!cancelled) setConversations(rows);
      })
      .catch(() => {
        if (!cancelled) setConversations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, scope]);

  const togglePhone = (phone) => {
    if (!phone) return;
    const set = new Set(selectedPhones);
    if (set.has(phone)) set.delete(phone);
    else set.add(phone);
    patch(id, { playgroundAudiencePhones: [...set] });
  };

  return (
    <>
      <h4 className="pg-modal__form-title">Audience</h4>
      <p className="pg-modal__hint muted">
        Définit qui peut déclencher ce scénario (messages entrants et filtre côté moteur).
      </p>
      <label className="pg-modal__label">
        Portée
        <select
          className="pg-modal__input"
          value={scope}
          onChange={(e) =>
            patch(id, { playgroundAudienceScope: e.target.value })
          }
        >
          <option value="all">Tout le monde (toutes les conversations du compte)</option>
          <option value="group">Un groupe de diffusion</option>
          <option value="phones">Contacts précis (sélection)</option>
        </select>
      </label>
      {scope === "group" && (
        <label className="pg-modal__label">
          Groupe
          <select
            className="pg-modal__input"
            value={groupId}
            onChange={(e) =>
              patch(id, { audienceBroadcastGroupId: e.target.value })
            }
            disabled={!accountId}
          >
            <option value="">- Choisir un groupe -</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name || g.id}
              </option>
            ))}
          </select>
        </label>
      )}
      {scope === "phones" && (
        <div className="pg-modal__label">
          <span>Conversations / numéros</span>
          <div
            className="pg-modal__audience-list"
            style={{ maxHeight: 200, overflowY: "auto" }}
          >
            {!accountId ? (
              <p className="pg-modal__hint muted">Compte requis.</p>
            ) : conversations.length === 0 ? (
              <p className="pg-modal__hint muted">Aucune conversation chargée.</p>
            ) : (
              conversations.map((c) => {
                const phone = c.client_number;
                if (!phone) return null;
                const label =
                  c.contacts?.display_name ||
                  c.contacts?.whatsapp_number ||
                  phone;
                return (
                  <label
                    key={c.id}
                    className="pg-modal__audience-row"
                    style={{ display: "flex", gap: 8, alignItems: "center" }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedPhones.includes(phone)}
                      onChange={() => togglePhone(phone)}
                    />
                    <span>{label}</span>
                  </label>
                );
              })
            )}
          </div>
          <p className="pg-modal__hint muted">
            {selectedPhones.length} contact(s) sélectionné(s).
          </p>
        </div>
      )}
    </>
  );
}

function StartAudiencePanel({ id, data, patch, accountId, flowId }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const flushSave = useContext(FlushSaveContext);

  const scope = audienceScopeFromData(data);
  const groupId = data.audienceBroadcastGroupId ?? "";
  const phones = Array.isArray(data.playgroundAudiencePhones)
    ? data.playgroundAudiencePhones
    : [];
  const scheduledLocal = data.campaignScheduledFor ?? "";

  const onScheduleSend = useCallback(async () => {
    if (!flowId) {
      setFeedback({
        ok: false,
        text: "Scénario non chargé - enregistre ou sélectionne un flux.",
      });
      return;
    }
    if (scope === "group" && !groupId) {
      setFeedback({ ok: false, text: "Choisis un groupe de diffusion." });
      return;
    }
    if (scope === "phones" && phones.length === 0) {
      setFeedback({
        ok: false,
        text: "Sélectionne au moins un contact (audience).",
      });
      return;
    }
    if (!scheduledLocal.trim()) {
      setFeedback({
        ok: false,
        text: "Indique la date et l’heure de lancement.",
      });
      return;
    }
    const scheduled_for = localDatetimeInputToUtcIso(scheduledLocal);
    if (!scheduled_for) {
      setFeedback({ ok: false, text: "Date / heure invalides." });
      return;
    }
    setFeedback(null);
    setBusy(true);
    try {
      await flushSave();
      const payload = {
        entry_node_id: id,
        scheduled_for,
      };
      if (scope === "group" && groupId) {
        payload.broadcast_group_id = groupId;
      }
      await schedulePlaygroundFlowLaunch(flowId, payload);
      setFeedback({
        ok: true,
        text:
          "Lancement planifié : à l’heure indiquée, le scénario démarre pour chaque contact cible et enchaîne avec le bloc suivant sur le canevas (aucun message depuis ce déclencheur).",
      });
    } catch (err) {
      setFeedback({
        ok: false,
        text:
          err.response?.data?.detail ||
          err.message ||
          "Échec de la planification",
      });
    } finally {
      setBusy(false);
    }
  }, [flowId, scope, groupId, phones.length, scheduledLocal, id, flushSave]);

  const scheduleDisabled =
    busy ||
    !accountId ||
    !flowId ||
    !scheduledLocal.trim() ||
    (scope === "group" && !groupId) ||
    (scope === "phones" && phones.length === 0);

  return (
    <>
      <h4 className="pg-modal__form-title">Planification campagne</h4>
      <label className="pg-modal__label">
        Date et heure de lancement
        <input
          className="pg-modal__input"
          type="datetime-local"
          value={scheduledLocal}
          onChange={(e) =>
            patch(id, { campaignScheduledFor: e.target.value })
          }
          disabled={busy}
        />
      </label>
      <p className="pg-modal__hint muted">
        Heure locale du navigateur, convertie en UTC côté serveur. Vérification toutes les ~30 s.
      </p>
      <div className="pg-modal__btn-row">
        <button
          type="button"
          className="pg-modal__mini-btn"
          disabled={scheduleDisabled}
          onClick={() => void onScheduleSend()}
        >
          Programmer le lancement
        </button>
      </div>
      {feedback ? (
        <p
          className={`pg-modal__status ${
            feedback.ok ? "pg-modal__status--ok" : "pg-modal__status--err"
          }`}
          role="status"
        >
          {feedback.text}
        </p>
      ) : null}
    </>
  );
}

function VarInsertSelect({ onInsert, excludeId }) {
  const { items } = useContext(VarListContext);
  const filtered = useMemo(
    () => (items || []).filter((it) => it.id !== excludeId),
    [items, excludeId]
  );
  if (!filtered.length) return null;
  return (
    <label className="pg-modal__label">
      Insérer variable
      <select
        className="pg-modal__input"
        value=""
        onChange={(e) => {
          const t = e.target.value;
          if (t) onInsert(t);
          e.target.value = "";
        }}
      >
        <option value="">-</option>
        {filtered.map((it) => (
          <option key={it.id} value={it.varKey}>
            {it.label} - {`{{${it.varKey}}}`}
          </option>
        ))}
      </select>
    </label>
  );
}

export function StartSettingsForm({ id, data, patch, accountId, flowId }) {
  const tt = data.triggerType || "message_in";
  const inboundLike = tt === "message_in" || tt === "playground_audience";
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Déclencheur</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Type
        <select
          className="pg-modal__input"
          value={tt}
          onChange={(e) => patch(id, { triggerType: e.target.value })}
        >
          <option value="message_in">Réception d’un message</option>
          <option value="schedule">Planification</option>
          <option value="webhook">Webhook / API</option>
          <option value="manual">Manuel</option>
          <option value="playground_audience">Campagne planifiée</option>
        </select>
      </label>
      <label className="pg-modal__label">
        Priorité d’entrée
        <input
          className="pg-modal__input"
          type="number"
          step={1}
          value={data.entryPriority ?? 0}
          onChange={(e) =>
            patch(id, {
              entryPriority: Number.parseInt(e.target.value, 10) || 0,
            })
          }
        />
      </label>
      <p className="pg-modal__hint muted">
        Plus la valeur est élevée, plus ce déclencheur est prioritaire. À égalité, « message entrant »
        l’emporte sur « campagne ».
      </p>
      {inboundLike && (
        <>
          <h4 className="pg-modal__form-title">Message entrant</h4>
          <label className="pg-modal__label">
            Correspondance
            <select
              className="pg-modal__input"
              value={data.messageMatch || "any"}
              onChange={(e) => patch(id, { messageMatch: e.target.value })}
            >
              <option value="any">N’importe quel message</option>
              <option value="contains">Contient</option>
              <option value="equals">Égal à</option>
              <option value="regex">Regex</option>
            </select>
          </label>
          {(data.messageMatch === "contains" ||
            data.messageMatch === "equals" ||
            data.messageMatch === "regex") && (
            <label className="pg-modal__label">
              Mot-clé / regex
              <input
                className="pg-modal__input"
                type="text"
                value={data.messageKeyword || ""}
                onChange={(e) => patch(id, { messageKeyword: e.target.value })}
              />
            </label>
          )}
        </>
      )}
      {inboundLike && (
        <StartAudienceScopeBlock
          id={id}
          data={data}
          patch={patch}
          accountId={accountId}
        />
      )}
      {tt === "schedule" && (
        <>
          <label className="pg-modal__label">
            Date et heure
            <input
              className="pg-modal__input"
              type="datetime-local"
              value={data.scheduleAt || ""}
              onChange={(e) => patch(id, { scheduleAt: e.target.value })}
            />
          </label>
          <label className="pg-modal__label">
            Répétition
            <select
              className="pg-modal__input"
              value={data.scheduleRepeat || "none"}
              onChange={(e) => patch(id, { scheduleRepeat: e.target.value })}
            >
              <option value="none">Aucune</option>
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
              <option value="monthly">Mensuelle</option>
            </select>
          </label>
        </>
      )}
      {tt === "webhook" && (
        <label className="pg-modal__label">
          Clé / secret (référence)
          <input
            className="pg-modal__input"
            type="text"
            value={data.webhookSecretRef || ""}
            onChange={(e) => patch(id, { webhookSecretRef: e.target.value })}
          />
        </label>
      )}
      {tt === "manual" && (
        <p className="pg-modal__hint">Déclenché à la demande (UI ou API).</p>
      )}
      {tt === "playground_audience" && (
        <StartAudiencePanel
          id={id}
          data={data}
          patch={patch}
          accountId={accountId}
          flowId={flowId}
        />
      )}
    </div>
  );
}

export function SendTextSettingsForm({ id, data, patch }) {
  const bodyRef = useRef(null);
  const insertVar = useCallback(
    (token) => {
      const tag = `{{${token}}}`;
      const ta = bodyRef.current;
      if (ta) {
        const start = ta.selectionStart ?? (data.body || "").length;
        const before = (data.body || "").slice(0, start);
        const after = (data.body || "").slice(ta.selectionEnd ?? start);
        patch(id, { body: before + tag + after });
        requestAnimationFrame(() => {
          ta.focus();
          const pos = start + tag.length;
          ta.setSelectionRange(pos, pos);
        });
      } else {
        patch(id, { body: (data.body || "") + tag });
      }
    },
    [id, data.body, patch]
  );

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Message texte</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <VarInsertSelect excludeId={id} onInsert={insertVar} />
      <label className="pg-modal__label">
        Contenu
        <textarea
          ref={bodyRef}
          className="pg-modal__input"
          rows={5}
          value={data.body || ""}
          onChange={(e) => patch(id, { body: e.target.value })}
          placeholder="Ex. Bonjour {{prenom_client}} ! Voici notre réponse : {{réponse_…}}"
        />
      </label>
    </div>
  );
}

export function SendTemplateSettingsForm({ id, data, patch }) {
  const { templates, loading } = useContext(TemplatesContext);
  const normalizeMetaStatus = useCallback((raw) => {
    const s = String(raw || "").trim().toLowerCase();
    if (!s) return "unknown";
    if (s === "approved") return "approved";
    if (s === "rejected") return "rejected";
    if (s === "pending" || s === "pending_review" || s === "in_review") {
      return "pending_review";
    }
    return "unknown";
  }, []);
  const statusLabel = useCallback((raw) => {
    const s = normalizeMetaStatus(raw);
    if (s === "approved") return "Approuvé";
    if (s === "pending_review") return "En revue";
    if (s === "rejected") return "Rejeté";
    if (s === "missing") return "Absent";
    return "Inconnu";
  }, [normalizeMetaStatus]);
  const templateOptions = useMemo(() => {
    const list = Array.isArray(templates) ? templates : [];
    const byKey = new Map();
    list.forEach((tpl) => {
      const key = `${tpl?.name || ""}||${tpl?.language || ""}`;
      if (!key || key === "||") return;
      byKey.set(key, tpl);
    });
    const currentKey = String(data.selectedTemplateKey || "").trim();
    if (currentKey && !byKey.has(currentKey)) {
      const [name, language] = currentKey.split("||");
      byKey.set(currentKey, {
        name: data.templateName || name || "",
        language: data.templateLanguage || language || "",
        status: data.templateStatus || "unknown",
        _orphan: true,
      });
    }
    return Array.from(byKey.entries()).map(([key, tpl]) => ({ key, ...tpl }));
  }, [
    templates,
    data.selectedTemplateKey,
    data.templateName,
    data.templateLanguage,
    data.templateStatus,
  ]);
  const selectedTpl = useMemo(() => {
    const key = data.selectedTemplateKey;
    if (!key) return null;
    const hit = templateOptions.find((t) => t.key === key);
    if (hit) return hit;
    const [name, lang] = key.split("||");
    return { name, language: lang };
  }, [data.selectedTemplateKey, templateOptions]);

  const varIds = useMemo(() => {
    const fromTpl = collectVarIdsFromTemplate(selectedTpl);
    const fromData = Object.keys(data.variableValues || {});
    const extra = fromData.filter((k) => !fromTpl.includes(k));
    return [...fromTpl, ...extra];
  }, [selectedTpl, data.variableValues]);
  const quickReplies = useMemo(() => {
    if (data.quickReplyButtons?.length) return data.quickReplyButtons;
    return extractQuickReplyButtons(selectedTpl);
  }, [data.quickReplyButtons, selectedTpl]);
  const setTemplateKey = (key) => {
    const [name, lang] = key.split("||");
    const tpl = templateOptions.find((t) => t.key === key);
    const vars = collectVarIdsFromTemplate(tpl);
    const variableValues = {};
    vars.forEach((v) => {
      variableValues[v] = data.variableValues?.[v] ?? "";
    });
    const status = normalizeMetaStatus(tpl?.status);
    patch(id, {
      selectedTemplateKey: key,
      templateName: name,
      templateLanguage: lang,
      variableValues,
      quickReplyButtons: extractQuickReplyButtons(tpl),
      templateStatus: status,
    });
  };

  const templateStatus = data.templateStatus || "unknown";

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Template WhatsApp (Meta)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Modèle Meta
        <select
          className="pg-modal__input"
          value={data.selectedTemplateKey || ""}
          disabled={loading || !templateOptions.length}
          onChange={(e) => e.target.value && setTemplateKey(e.target.value)}
        >
          <option value="">
            {loading ? "Chargement…" : templateOptions.length ? "Choisir…" : "Aucun"}
          </option>
          {templateOptions.map((t) => {
            const key = t.key;
            const suffix = statusLabel(t.status);
            return (
              <option key={key} value={key}>
                {t.name} ({t.language}) - {suffix}
                {t._orphan ? " (conservé)" : ""}
              </option>
            );
          })}
        </select>
      </label>
      {varIds.length > 0 && (
        <div className="pg-modal__section">
          <span className="pg-modal__section-title">Variables du template Meta</span>
          {varIds.map((vk) => (
            <label key={vk} className="pg-modal__label">
              <code>{`{{${vk}}}`}</code> (corps Meta)
              <input
                className="pg-modal__input"
                type="text"
                value={(data.variableValues && data.variableValues[vk]) || ""}
                onChange={(e) =>
                  patch(id, {
                    variableValues: {
                      ...(data.variableValues || {}),
                      [vk]: e.target.value,
                    },
                  })
                }
                placeholder="Ex. Bonjour {{prenom_client}} !"
              />
            </label>
          ))}
        </div>
      )}
      <details className="pg-modal__section">
        <summary className="pg-modal__section-title">Avancé</summary>
        <label className="pg-modal__label">
          Statut sur Meta (affiché sur le nœud)
          <select
            className="pg-modal__input"
            value={templateStatus}
            onChange={(e) => patch(id, { templateStatus: e.target.value })}
          >
            <option value="unknown">Inconnu / à vérifier</option>
            <option value="missing">N’existe pas encore sur le compte</option>
            <option value="pending_review">Soumis - en cours de vérification</option>
            <option value="approved">Approuvé (envoyable)</option>
            <option value="rejected">Rejeté par Meta</option>
          </select>
        </label>
        {quickReplies.length > 0 && (
          <div className="pg-modal__row2">
            <label className="pg-modal__label">
              Délai timeout
              <input
                className="pg-modal__input"
                type="number"
                min={0}
                step="any"
                value={data.timeoutDuration ?? ""}
                onChange={(e) =>
                  patch(id, {
                    timeoutDuration: e.target.value === "" ? "" : e.target.value,
                  })
                }
              />
            </label>
            <label className="pg-modal__label">
              Unité timeout
              <select
                className="pg-modal__input"
                value={data.timeoutUnit || "h"}
                onChange={(e) => patch(id, { timeoutUnit: e.target.value })}
              >
                <option value="s">Secondes</option>
                <option value="m">Minutes</option>
                <option value="h">Heures</option>
                <option value="d">Jours</option>
              </select>
            </label>
          </div>
        )}
      </details>
    </div>
  );
}

export function GeminiSettingsForm({ id, data, patch }) {
  const intents = Array.isArray(data.intents) ? data.intents : [];
  const setIntents = (next) => patch(id, { intents: next });
  const promptRef = useRef(null);
  const insertVarInPrompt = useCallback(
    (token) => {
      const tag = `{{${token}}}`;
      const ta = promptRef.current;
      if (ta) {
        const start = ta.selectionStart ?? (data.systemPrompt || "").length;
        const before = (data.systemPrompt || "").slice(0, start);
        const after = (data.systemPrompt || "").slice(ta.selectionEnd ?? start);
        patch(id, { systemPrompt: before + tag + after });
        requestAnimationFrame(() => {
          ta.focus();
          const pos = start + tag.length;
          ta.setSelectionRange(pos, pos);
        });
      } else {
        patch(id, { systemPrompt: (data.systemPrompt || "") + tag });
      }
    },
    [id, data.systemPrompt, patch]
  );

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Gemini (IA)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <VarInsertSelect excludeId={id} onInsert={insertVarInPrompt} />
      <label className="pg-modal__label">
        Prompt système
        <textarea
          ref={promptRef}
          className="pg-modal__input pg-modal__code"
          rows={4}
          value={data.systemPrompt || ""}
          onChange={(e) => patch(id, { systemPrompt: e.target.value })}
          placeholder="Ex. Tu es un assistant. Réponds au client en fonction de sa demande."
        />
      </label>
      <div className="pg-modal__btn-row">
        <button
          type="button"
          className="ghost"
          onClick={() => patch(id, { systemPrompt: DEFAULT_GEMINI_STATUT_ROUTER_PROMPT })}
        >
          Charger le prompt qualification statut VTC
        </button>
      </div>
      <details className="pg-modal__section">
        <summary className="pg-modal__section-title">Avancé</summary>
        <label className="pg-modal__label">
          Consigne complémentaire
          <textarea
            className="pg-modal__input"
            rows={3}
            value={data.hint || ""}
            onChange={(e) => patch(id, { hint: e.target.value })}
          />
        </label>
        <label className="pg-modal__label">
          Base de connaissances
          <textarea
            className="pg-modal__input pg-modal__code"
            rows={5}
            value={data.knowledgeBase || ""}
            onChange={(e) => patch(id, { knowledgeBase: e.target.value })}
          />
        </label>
      </details>
      <div className="pg-modal__section">
        <span className="pg-modal__section-title">Mots-clés → branche</span>
        <p className="pg-modal__hint">
          Reliez chaque sortie au suivant. La poignée « inconnu » est utilisée après
          échec du routage (par défaut l’IA pose d’abord une question de précision si
          activé ci‑dessous, puis cette branche - ex. handoff).
        </p>
        <div className="pg-modal__btn-row">
          <button
            type="button"
            className="ghost"
            onClick={() =>
              patch(id, { clarifyOnUnknown: true, maxClarifyAttempts: 3 })
            }
          >
            Préréglage : compréhension (3 précisions)
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              patch(id, { clarifyOnUnknown: true, maxClarifyAttempts: 1 })
            }
          >
            Préréglage : rapide (1 précision)
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              patch(id, { clarifyOnUnknown: false, maxClarifyAttempts: 1 })
            }
          >
            Préréglage : direct « inconnu »
          </button>
        </div>
        <label className="pg-modal__label pg-modal__row2">
          <input
            type="checkbox"
            checked={data.useEmbeddingSimilarity === true}
            onChange={(e) => patch(id, { useEmbeddingSimilarity: e.target.checked })}
          />{" "}
          Routage sémantique (embeddings) si le mot-clé échoue - coût API supplémentaire
        </label>
        <label className="pg-modal__label">
          Seuil de similarité (0,35–0,95)
          <input
            className="pg-modal__input"
            type="number"
            step="0.01"
            min={0.35}
            max={0.95}
            value={data.embeddingSimilarityThreshold ?? 0.62}
            onChange={(e) => {
              const v = parseFloat(e.target.value, 10);
              patch(id, {
                embeddingSimilarityThreshold: Number.isFinite(v)
                  ? Math.min(0.95, Math.max(0.35, v))
                  : 0.62,
              });
            }}
          />
        </label>
        <label className="pg-modal__label pg-modal__row2">
          <input
            type="checkbox"
            checked={data.structuredMemory !== false}
            onChange={(e) => patch(id, { structuredMemory: e.target.checked })}
          />{" "}
          Journal mémoire (lignes dans la variable{" "}
          <code className="pg-modal__code">flow_structured_notes</code>)
        </label>
        <p className="pg-modal__hint">
          Utilisez{" "}
          <code className="pg-modal__code">{"{{flow_structured_notes}}"}</code> et{" "}
          <code className="pg-modal__code">{"{{flow_recent_user_text}}"}</code> dans
          les prompts pour le contexte multi-messages.
        </p>
        <label className="pg-modal__label pg-modal__row2">
          <input
            type="checkbox"
            checked={data.clarifyOnUnknown !== false}
            onChange={(e) => patch(id, { clarifyOnUnknown: e.target.checked })}
          />{" "}
          Demander une précision (IA) avant la branche « inconnu »
        </label>
        <label className="pg-modal__label">
          Nombre max de questions de précision avant « inconnu »
          <input
            className="pg-modal__input"
            type="number"
            min={0}
            max={5}
            value={data.maxClarifyAttempts ?? 3}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10);
              patch(id, {
                maxClarifyAttempts: Number.isFinite(v) ? Math.min(5, Math.max(0, v)) : 3,
              });
            }}
          />
        </label>
        {intents.map((row, i) => (
          <div key={i} className="pg-modal__row2">
            <label className="pg-modal__label">
              Mot-clé sortie
              <input
                className="pg-modal__input"
                type="text"
                value={row.keyword || ""}
                onChange={(e) => {
                  const next = [...intents];
                  next[i] = { ...next[i], keyword: e.target.value };
                  setIntents(next);
                }}
              />
            </label>
            <label className="pg-modal__label">
              Libellé (affichage)
              <input
                className="pg-modal__input"
                type="text"
                value={row.label || ""}
                onChange={(e) => {
                  const next = [...intents];
                  next[i] = { ...next[i], label: e.target.value };
                  setIntents(next);
                }}
              />
            </label>
          </div>
        ))}
        <div className="pg-modal__btn-row">
          <button
            type="button"
            className="ghost"
            onClick={() => setIntents([...intents, { keyword: "", label: "" }])}
          >
            + Intention
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setIntents(intents.slice(0, -1))}
            disabled={!intents.length}
          >
            Retirer la dernière
          </button>
        </div>
      </div>
    </div>
  );
}

export function DelaySettingsForm({ id, data, patch }) {
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Attente (délai)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <div className="pg-modal__row2">
        <label className="pg-modal__label">
          Durée
          <input
            className="pg-modal__input"
            type="number"
            min={0}
            value={data.duration ?? ""}
            onChange={(e) => patch(id, { duration: e.target.value })}
          />
        </label>
        <label className="pg-modal__label">
          Unité
          <select
            className="pg-modal__input"
            value={data.unit || "s"}
            onChange={(e) => patch(id, { unit: e.target.value })}
          >
            <option value="s">Secondes</option>
            <option value="m">Minutes</option>
            <option value="h">Heures</option>
            <option value="d">Jours</option>
          </select>
        </label>
      </div>
    </div>
  );
}

export function WaitUntilSettingsForm({ id, data, patch }) {
  const displayUntil = useMemo(
    () => untilToDatetimeLocalInputValue(data.until),
    [data.until]
  );
  const configured = useMemo(
    () => describeWaitUntilConfiguredState(data || {}),
    [data]
  );

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Attendre jusqu’à</h4>
      <p className="pg-modal__hint muted">
        Le sélecteur ci‑dessous attend une <strong>date fixe</strong>. Les valeurs ISO
        (souvent produites par l’IA) sont converties pour l’affichage : si tu voyais un champ
        vide avant, la date peut être là sans être visible.
      </p>
      <p
        className={`pg-modal__status ${
          configured.kind === "empty"
            ? "pg-modal__status--warn"
            : "pg-modal__status--ok"
        }`}
        role="status"
      >
        {configured.text}
      </p>
      <label className="pg-modal__label">
        Date et heure cible (fixe)
        <input
          className="pg-modal__input"
          type="datetime-local"
          value={displayUntil}
          onChange={(e) => patch(id, { until: e.target.value })}
        />
      </label>
      <label className="pg-modal__label">
        Date depuis une variable de flux (optionnel)
        <input
          className="pg-modal__input"
          type="text"
          placeholder="ex. réponse_date_rdv (sans {{ }})"
          value={data.untilFromVarKey || ""}
          onChange={(e) =>
            patch(id, { untilFromVarKey: e.target.value.trim() })
          }
        />
      </label>
      <p className="pg-modal__hint muted">
        Si renseigné, le moteur lit <code>variables[clé]</code> (chaîne ISO type{" "}
        <code>2026-04-20T15:00:00+02:00</code>) et ignore la date fixe ci‑dessus.
      </p>
      <label className="pg-modal__label">
        Fuseau horaire (IANA, pour la date fixe sans offset)
        <input
          className="pg-modal__input"
          type="text"
          placeholder="Europe/Paris ou UTC"
          value={data.timezoneNote || ""}
          onChange={(e) => patch(id, { timezoneNote: e.target.value })}
        />
      </label>
      <h4 className="pg-modal__form-title">Variable du nœud</h4>
      <p className="pg-modal__hint muted">
        Le libellé <code>{`{{${data.varKey || "…"}}}`}</code> est le{" "}
        <strong>nom interne</strong> de ce bloc (aperçu sur le canevas), pas la date cible.
      </p>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
    </div>
  );
}

export function TimeWindowSettingsForm({ id, data, patch }) {
  const active = data.activeDays || ["1", "2", "3", "4", "5"];
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Fenêtre horaire</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <div className="pg-modal__days">
        {WEEKDAYS.map(({ v, l }) => (
          <label key={v} className="pg-modal__day">
            <input
              type="checkbox"
              checked={active.includes(v)}
              onChange={() => patch(id, { activeDays: toggleDay(active, v) })}
            />
            {l}
          </label>
        ))}
      </div>
      <div className="pg-modal__row2">
        <label className="pg-modal__label">
          Début
          <input
            className="pg-modal__input"
            type="time"
            value={data.startTime || "09:00"}
            onChange={(e) => patch(id, { startTime: e.target.value })}
          />
        </label>
        <label className="pg-modal__label">
          Fin
          <input
            className="pg-modal__input"
            type="time"
            value={data.endTime || "18:00"}
            onChange={(e) => patch(id, { endTime: e.target.value })}
          />
        </label>
      </div>
    </div>
  );
}

export function LogicSettingsForm({ id, data, patch }) {
  const mode = data.logicMode || "si";

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Logique</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Mode
        <select
          className="pg-modal__input"
          value={mode}
          onChange={(e) => patch(id, { logicMode: e.target.value })}
        >
          <option value="si">SI (vrai / faux)</option>
          <option value="ou">OU</option>
          <option value="et">ET (2 entrées)</option>
        </select>
      </label>

      {mode === "si" && (
        <>
          <label className="pg-modal__label">
            Expression
            <textarea
              className="pg-modal__input pg-modal__code"
              rows={5}
              value={data.condition || ""}
              onChange={(e) => patch(id, { condition: e.target.value })}
            />
          </label>
        </>
      )}
      {mode === "ou" && (
        <p className="pg-modal__hint">
          Une entrée, sorties A et B (voir poignées sur le nœud).
        </p>
      )}
      {mode === "et" && (
        <p className="pg-modal__hint">
          Entrées A et B en haut, sortie unique en bas.
        </p>
      )}
    </div>
  );
}

export function InteractiveSettingsForm({ id, data, patch }) {
  const kind = data.uiKind === "list" ? "list" : "buttons";
  const choices = Array.isArray(data.choices) ? data.choices : [];
  const setChoices = (next) => patch(id, { choices: next });
  const bodyRef = useRef(null);
  const insertVar = useCallback(
    (token) => {
      const tag = `{{${token}}}`;
      const ta = bodyRef.current;
      if (ta) {
        const start = ta.selectionStart ?? (data.body || "").length;
        const before = (data.body || "").slice(0, start);
        const after = (data.body || "").slice(ta.selectionEnd ?? start);
        patch(id, { body: before + tag + after });
        requestAnimationFrame(() => {
          ta.focus();
          const pos = start + tag.length;
          ta.setSelectionRange(pos, pos);
        });
      } else {
        patch(id, { body: (data.body || "") + tag });
      }
    },
    [id, data.body, patch]
  );

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Message interactif (24h)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <VarInsertSelect excludeId={id} onInsert={insertVar} />
      <label className="pg-modal__label">
        Texte du message
        <textarea
          ref={bodyRef}
          className="pg-modal__input"
          rows={4}
          value={data.body || ""}
          onChange={(e) => patch(id, { body: e.target.value })}
        />
      </label>
      <label className="pg-modal__label">
        Type
        <select
          className="pg-modal__input"
          value={kind}
          onChange={(e) =>
            patch(id, { uiKind: e.target.value === "list" ? "list" : "buttons" })
          }
        >
          <option value="buttons">Boutons (max 3)</option>
          <option value="list">Liste</option>
        </select>
      </label>
      {kind === "list" && (
        <label className="pg-modal__label">
          Libellé bouton liste (Meta)
          <input
            className="pg-modal__input"
            type="text"
            value={data.listButtonText || ""}
            onChange={(e) => patch(id, { listButtonText: e.target.value })}
            placeholder="Voir les options"
            maxLength={20}
          />
        </label>
      )}
      {kind === "buttons" && choices.length > 3 && (
        <p className="pg-modal__hint">
          Seuls les 3 premiers choix sont utilisés en mode boutons.
        </p>
      )}
      <div className="pg-modal__section">
        <span className="pg-modal__section-title">Choix (libellé affiché)</span>
        {choices.map((c, i) => (
          <div key={i} className="pg-modal__row2">
            <label className="pg-modal__label">
              {kind === "buttons" ? `Bouton ${i + 1}` : `Ligne ${i + 1}`} - titre
              <input
                className="pg-modal__input"
                type="text"
                value={c.title || ""}
                onChange={(e) => {
                  const next = [...choices];
                  next[i] = { ...next[i], title: e.target.value };
                  setChoices(next);
                }}
              />
            </label>
          </div>
        ))}
        <div className="pg-modal__btn-row">
          <button
            type="button"
            className="ghost"
            onClick={() => setChoices([...choices, { title: "" }])}
          >
            + Choix
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setChoices(choices.slice(0, -1))}
            disabled={!choices.length}
          >
            Retirer le dernier
          </button>
        </div>
      </div>
      <details className="pg-modal__section">
        <summary className="pg-modal__section-title">Avancé</summary>
        <div className="pg-modal__row2">
          <label className="pg-modal__label">
            Délai timeout
            <input
              className="pg-modal__input"
              type="number"
              min={0}
              step="any"
              value={data.timeoutDuration ?? ""}
              onChange={(e) =>
                patch(id, {
                  timeoutDuration: e.target.value === "" ? "" : e.target.value,
                })
              }
            />
          </label>
          <label className="pg-modal__label">
            Unité timeout
            <select
              className="pg-modal__input"
              value={data.timeoutUnit || "h"}
              onChange={(e) => patch(id, { timeoutUnit: e.target.value })}
            >
              <option value="s">Secondes</option>
              <option value="m">Minutes</option>
              <option value="h">Heures</option>
              <option value="d">Jours</option>
            </select>
          </label>
        </div>
      </details>
    </div>
  );
}

export function RouterSettingsForm({ id, data, patch }) {
  const routes =
    Array.isArray(data.routes) && data.routes.length
      ? data.routes
      : [{ label: "A", match: "A" }];
  const setRoutes = (next) => patch(id, { routes: next });

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Routeur (réponse précédente)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <div className="pg-modal__section">
        <span className="pg-modal__section-title">Branches</span>
        {routes.map((r, i) => (
          <div key={i} className="pg-modal__row2">
            <label className="pg-modal__label">
              Libellé (affichage)
              <input
                className="pg-modal__input"
                type="text"
                value={r.label || ""}
                onChange={(e) => {
                  const next = [...routes];
                  next[i] = { ...next[i], label: e.target.value };
                  setRoutes(next);
                }}
              />
            </label>
            <label className="pg-modal__label">
              Valeur attendue (= réponse)
              <input
                className="pg-modal__input"
                type="text"
                value={r.match || ""}
                onChange={(e) => {
                  const next = [...routes];
                  next[i] = { ...next[i], match: e.target.value };
                  setRoutes(next);
                }}
              />
            </label>
          </div>
        ))}
        <div className="pg-modal__btn-row">
          <button
            type="button"
            className="ghost"
            onClick={() =>
              setRoutes([
                ...routes,
                { label: `Option ${routes.length + 1}`, match: "" },
              ])
            }
            disabled={routes.length >= 6}
          >
            + Branche
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => setRoutes(routes.slice(0, -1))}
            disabled={routes.length <= 1}
          >
            Retirer la dernière
          </button>
        </div>
      </div>
    </div>
  );
}

export function HandoffSettingsForm({ id, data, patch }) {
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Handoff humain / action</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Tags (séparés par virgule)
        <input
          className="pg-modal__input"
          type="text"
          value={data.tagsText || ""}
          onChange={(e) => patch(id, { tagsText: e.target.value })}
          placeholder="Chaud - Coopérative, VIP…"
        />
      </label>
      <label className="pg-modal__label">
        Message interne
        <textarea
          className="pg-modal__input"
          rows={3}
          value={data.internalMessage || ""}
          onChange={(e) => patch(id, { internalMessage: e.target.value })}
          placeholder="Appeler ce prospect au plus vite…"
        />
      </label>
      <details className="pg-modal__section">
        <summary className="pg-modal__section-title">Avancé</summary>
        <label className="pg-modal__label">
          Assignation agent (référence / id)
          <input
            className="pg-modal__input"
            type="text"
            value={data.assignAgent || ""}
            onChange={(e) => patch(id, { assignAgent: e.target.value })}
            placeholder="user_id ou file d’attente"
          />
        </label>
      </details>
    </div>
  );
}
