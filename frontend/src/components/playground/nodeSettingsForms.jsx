import {
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { getBroadcastGroups } from "../../api/broadcastApi";
import { schedulePlaygroundFlowLaunch } from "../../api/playgroundFlowsApi";
import { VarListContext, PlaygroundGraphContext, TemplatesContext } from "./flowContext";
import {
  WEEKDAYS,
  collectVarIdsFromTemplate,
  extractQuickReplyButtons,
  extractCtaButtons,
  replyPredicateForButton,
  buildTemplateReplyPredicate,
  toggleDay,
  DEFAULT_GEMINI_STATUT_ROUTER_PROMPT,
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

function StartAudiencePanel({ id, data, patch, accountId, flowId }) {
  const [groups, setGroups] = useState([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const groupId = data.audienceBroadcastGroupId ?? "";
  const scheduledLocal = data.campaignScheduledFor ?? "";

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

  const onScheduleSend = useCallback(async () => {
    if (!flowId) {
      setFeedback({
        ok: false,
        text: "Scénario non chargé — enregistre ou sélectionne un flux.",
      });
      return;
    }
    if (!groupId) {
      setFeedback({ ok: false, text: "Choisis un groupe de diffusion." });
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
      await schedulePlaygroundFlowLaunch(flowId, {
        broadcast_group_id: groupId,
        entry_node_id: id,
        scheduled_for,
      });
      setFeedback({
        ok: true,
        text:
          "Lancement planifié : à l’heure indiquée, le scénario démarre pour chaque contact du groupe et enchaîne avec le bloc suivant sur le canevas (aucun message depuis ce déclencheur).",
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
  }, [flowId, groupId, scheduledLocal, id]);

  return (
    <>
      <p className="pg-modal__hint">
        Ce déclencheur n’envoie rien lui-même : il sert de <strong>point de lancement programmé</strong>.
        Relie ce bloc à la <strong>deuxième étape</strong> du parcours (texte, template, etc.) : à l’heure
        choisie, le moteur démarre le flux pour chaque membre du groupe et suit les flèches du graphe.
      </p>
      <label className="pg-modal__label">
        Groupe de diffusion
        <select
          className="pg-modal__input"
          value={groupId}
          onChange={(e) =>
            patch(id, { audienceBroadcastGroupId: e.target.value })
          }
          disabled={busy || !accountId}
        >
          <option value="">— Choisir un groupe —</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name || g.id}
            </option>
          ))}
        </select>
      </label>
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
          disabled={busy || !accountId || !flowId || !groupId || !scheduledLocal.trim()}
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
        <option value="">—</option>
        {filtered.map((it) => (
          <option key={it.id} value={it.varKey}>
            {it.label} — {`{{${it.varKey}}}`}
          </option>
        ))}
      </select>
    </label>
  );
}

export function StartSettingsForm({ id, data, patch, accountId, flowId }) {
  const tt = data.triggerType || "message_in";
  const priVal =
    data.entryPriority !== undefined && data.entryPriority !== null
      ? String(data.entryPriority)
      : "0";
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Déclencheur</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Priorité (plusieurs entrées)
        <input
          className="pg-modal__input"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          value={priVal}
          onChange={(e) => {
            const v = e.target.value;
            const n = parseInt(v, 10);
            patch(id, {
              entryPriority: v === "" || Number.isNaN(n) ? 0 : n,
            });
          }}
        />
      </label>
      <p className="pg-modal__hint">
        Plus la valeur est élevée, plus cette entrée est choisie en premier parmi celles
        dont le déclencheur correspond au message.
      </p>
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
      {tt === "message_in" && (
        <>
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
      <p className="pg-modal__hint">
        Utilisez le sélecteur ci-dessus pour insérer la variable d'un autre nœud
        (ex. réponse Gemini, bouton interactif). Le texte <code>{"{{…}}"}</code> sera
        remplacé automatiquement à l'envoi.
      </p>
    </div>
  );
}

export function SendTemplateSettingsForm({ id, data, patch }) {
  const { templates, loading } = useContext(TemplatesContext);
  const selectedTpl = useMemo(() => {
    const key = data.selectedTemplateKey;
    if (!key || !templates?.length) return null;
    const [name, lang] = key.split("||");
    return templates.find(
      (t) => t.name === name && String(t.language) === String(lang)
    );
  }, [data.selectedTemplateKey, templates]);

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
  const ctaButtons = useMemo(
    () => extractCtaButtons(selectedTpl),
    [selectedTpl]
  );

  const setTemplateKey = (key) => {
    const [name, lang] = key.split("||");
    const tpl = templates.find(
      (t) => t.name === name && String(t.language) === String(lang)
    );
    const vars = collectVarIdsFromTemplate(tpl);
    const variableValues = {};
    vars.forEach((v) => {
      variableValues[v] = data.variableValues?.[v] ?? "";
    });
    patch(id, {
      selectedTemplateKey: key,
      templateName: name,
      templateLanguage: lang,
      variableValues,
      quickReplyButtons: extractQuickReplyButtons(tpl),
    });
  };

  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Template WhatsApp (Meta)</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <p className="pg-modal__hint">
        Pour initier ou relancer après 24h : message pré-approuvé Meta (ID du
        template ci-dessous). Mappez les variables ; les quick replies alimentent
        le routeur / SI en aval.
      </p>
      <p className="pg-modal__hint">
        <code>réponse_*</code> = texte reçu (message libre ou libellé exact d’un
        bouton quick reply).
      </p>
      <label className="pg-modal__label">
        Modèle Meta
        <select
          className="pg-modal__input"
          value={data.selectedTemplateKey || ""}
          disabled={loading || !templates?.length}
          onChange={(e) => e.target.value && setTemplateKey(e.target.value)}
        >
          <option value="">
            {loading ? "Chargement…" : templates?.length ? "Choisir…" : "Aucun"}
          </option>
          {templates.map((t) => {
            const key = `${t.name}||${t.language}`;
            return (
              <option key={key} value={key}>
                {t.name} ({t.language})
              </option>
            );
          })}
        </select>
      </label>
      {varIds.length > 0 && (
        <div className="pg-modal__section">
          <span className="pg-modal__section-title">Variables du template Meta</span>
          <p className="pg-modal__hint">
            Texte fixe ou placeholders du <strong>client</strong> (remplis à l’envoi) :{" "}
            <code>{"{{prenom_client}}"}</code>, <code>{"{{nom_client}}"}</code>,{" "}
            <code>{"{{numero_client}}"}</code> — ou en anglais{" "}
            <code>{"{{contact_first_name}}"}</code>, <code>{"{{contact_name}}"}</code>,{" "}
            <code>{"{{contact_phone}}"}</code> — alias courants{" "}
            <code>{"{{contact.firstName}}"}</code>, <code>{"{{contact.name}}"}</code>,{" "}
            <code>{"{{contact.phone}}"}</code>. Civilité (M./Mme) : pas de variable dédiée — préfixe fixe, ex.{" "}
            <code>{"M. {{nom_client}}"}</code>.{" "}
            <strong>Syntaxe :</strong> privilégier <code>{"{{…}}"}</code> ; la forme à une seule paire{" "}
            <code>{"{prenom_client}"}</code> / <code>{"{contact.firstName}"}</code> est aussi remplacée à l’envoi.
          </p>
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
      {quickReplies.length > 0 && (
        <div className="pg-modal__section">
          <span className="pg-modal__section-title">Réponses boutons</span>
          <p className="pg-modal__hint">
            Pour un SI en aval, comparer <code>réponse_*</code> au texte du
            bouton (souvent égal à).
          </p>
          <ul className="pg-modal__qr-list">
            {quickReplies.map((b, i) => {
              const pred = replyPredicateForButton(data.varKey, b.text);
              return (
                <li key={i} className="pg-modal__qr-item">
                  <strong>{b.text}</strong>
                  <code className="pg-modal__snippet">{pred}</code>
                  <button
                    type="button"
                    className="ghost pg-modal__mini-btn"
                    onClick={() =>
                      navigator.clipboard?.writeText(pred).catch(() => {})
                    }
                  >
                    Copier SI
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {ctaButtons.length > 0 && (
        <div className="pg-modal__section">
          <span className="pg-modal__section-title">Liens / appel</span>
          <p className="pg-modal__hint">Pas de texte de réponse pour un SI.</p>
          <ul>
            {ctaButtons.map((b, i) => (
              <li key={i}>
                {b.type === "URL" ? "Lien" : "Appel"} : {b.text}
              </li>
            ))}
          </ul>
        </div>
      )}
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
      <p className="pg-modal__hint">
        La réponse IA est stockée dans <code>{`{{${data.varKey || "…"}}}`}</code>.
        Utilisez cette variable dans le nœud <strong>Texte</strong> ou <strong>Interactif</strong> suivant
        pour envoyer le message au client.
      </p>
      <p className="pg-modal__hint muted">
        Sans intentions + prompt rempli : texte généré (pas d’envoi direct).
        Sans prompt : réponse playbook (envoi direct).
        Avec intentions : routage par mot-clé.
      </p>
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
      <label className="pg-modal__label">
        Consigne complémentaire (optionnel)
        <textarea
          className="pg-modal__input"
          rows={3}
          value={data.hint || ""}
          onChange={(e) => patch(id, { hint: e.target.value })}
        />
      </label>
      <div className="pg-modal__section">
        <span className="pg-modal__section-title">Mots-clés → branche</span>
        <p className="pg-modal__hint">
          Reliez chaque sortie du nœud au suivant. La poignée « inconnu » =
          intention floue (handoff).
        </p>
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
      <p className="pg-modal__hint">
        Si le délai fait dépasser 24h sans message client, le nœud suivant doit
        en principe être un template WhatsApp (hors fenêtre gratuite).
      </p>
    </div>
  );
}

export function WaitUntilSettingsForm({ id, data, patch }) {
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Attendre jusqu’à</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <label className="pg-modal__label">
        Date et heure cible
        <input
          className="pg-modal__input"
          type="datetime-local"
          value={data.until || ""}
          onChange={(e) => patch(id, { until: e.target.value })}
        />
      </label>
      <label className="pg-modal__label">
        Fuseau / note
        <input
          className="pg-modal__input"
          type="text"
          placeholder="Europe/Paris"
          value={data.timezoneNote || ""}
          onChange={(e) => patch(id, { timezoneNote: e.target.value })}
        />
      </label>
    </div>
  );
}

export function TimeWindowSettingsForm({ id, data, patch }) {
  const active = data.activeDays || ["1", "2", "3", "4", "5"];
  return (
    <div className="pg-modal__form">
      <h4 className="pg-modal__form-title">Fenêtre horaire</h4>
      <NodeVarLine varKey={data.varKey} nodeId={id} patch={patch} />
      <p className="pg-modal__hint">0 = dimanche. Sorties : dans / hors plage.</p>
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
  const graphNodes = useContext(PlaygroundGraphContext) || [];
  const { templates } = useContext(TemplatesContext);
  const mode = data.logicMode || "si";

  const templateNodes = useMemo(
    () =>
      (graphNodes || []).filter(
        (n) => n.type === "sendTemplate" && n.data?.varKey
      ),
    [graphNodes]
  );

  const [tplCondNodeId, setTplCondNodeId] = useState("");
  const [tplCondOp, setTplCondOp] = useState("eq");
  const [tplCondVal, setTplCondVal] = useState("");
  const [tplCondBtnIdx, setTplCondBtnIdx] = useState("");

  const tplNodeForCond = useMemo(
    () => templateNodes.find((x) => x.id === tplCondNodeId),
    [templateNodes, tplCondNodeId]
  );

  const tplQuickButtonsForCond = useMemo(() => {
    const n = tplNodeForCond;
    if (!n?.data) return [];
    const d = n.data;
    if (Array.isArray(d.quickReplyButtons) && d.quickReplyButtons.length) {
      return d.quickReplyButtons;
    }
    const key = d.selectedTemplateKey;
    if (!key || !templates?.length) return [];
    const [name, lang] = key.split("||");
    const meta = templates.find(
      (t) => t.name === name && String(t.language) === String(lang)
    );
    return extractQuickReplyButtons(meta);
  }, [tplNodeForCond, templates]);

  useEffect(() => {
    setTplCondBtnIdx("");
  }, [tplCondNodeId]);

  const appendTemplateCondition = useCallback(() => {
    const n = templateNodes.find((x) => x.id === tplCondNodeId);
    if (!n?.data?.varKey) return;
    const pred = buildTemplateReplyPredicate(
      n.data.varKey,
      tplCondOp,
      tplCondVal
    );
    if (!pred) return;
    const cur = (data.condition || "").trim();
    patch(id, { condition: cur ? `${cur} && (${pred})` : pred });
  }, [
    templateNodes,
    tplCondNodeId,
    tplCondOp,
    tplCondVal,
    data.condition,
    id,
    patch,
  ]);

  const replaceWithTemplateCondition = useCallback(() => {
    const n = templateNodes.find((x) => x.id === tplCondNodeId);
    if (!n?.data?.varKey) return;
    const pred = buildTemplateReplyPredicate(
      n.data.varKey,
      tplCondOp,
      tplCondVal
    );
    if (!pred) return;
    patch(id, { condition: pred });
  }, [templateNodes, tplCondNodeId, tplCondOp, tplCondVal, id, patch]);

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
          <p className="pg-modal__hint">
            Variables <code>réponse_*</code> — pour un template, réponse client
            après envoi.
          </p>
          {templateNodes.length > 0 && (
            <div className="pg-modal__section pg-modal__cond">
              <span className="pg-modal__section-title">
                Si réponse au template…
              </span>
              <label className="pg-modal__label">
                Nœud template
                <select
                  className="pg-modal__input"
                  value={tplCondNodeId}
                  onChange={(e) => setTplCondNodeId(e.target.value)}
                >
                  <option value="">—</option>
                  {templateNodes.map((n) => {
                    const name =
                      n.data?.templateName ||
                      (n.data?.selectedTemplateKey || "").split("||")[0] ||
                      "template";
                    const qr = n.data?.quickReplyButtons?.length || 0;
                    return (
                      <option key={n.id} value={n.id}>
                        « {name} »{qr ? ` · ${qr} btn` : ""}
                      </option>
                    );
                  })}
                </select>
              </label>
              {tplQuickButtonsForCond.length > 0 && (
                <label className="pg-modal__label">
                  = bouton quick reply
                  <select
                    className="pg-modal__input"
                    value={tplCondBtnIdx}
                    onChange={(e) => {
                      const idx = e.target.value;
                      setTplCondBtnIdx(idx);
                      if (idx === "") return;
                      const b = tplQuickButtonsForCond[Number(idx)];
                      if (b?.text) {
                        setTplCondVal(b.text);
                        setTplCondOp("eq");
                      }
                    }}
                  >
                    <option value="">Manuel</option>
                    {tplQuickButtonsForCond.map((b, i) => (
                      <option key={i} value={String(i)}>
                        {b.text}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="pg-modal__row2">
                <label className="pg-modal__label">
                  Comparaison
                  <select
                    className="pg-modal__input"
                    value={tplCondOp}
                    onChange={(e) => setTplCondOp(e.target.value)}
                  >
                    <option value="eq">Égal à</option>
                    <option value="contains">Contient</option>
                    <option value="regex">Regex</option>
                  </select>
                </label>
                <label className="pg-modal__label">
                  Valeur
                  <input
                    className="pg-modal__input"
                    type="text"
                    value={tplCondVal}
                    onChange={(e) => setTplCondVal(e.target.value)}
                  />
                </label>
              </div>
              <div className="pg-modal__btn-row">
                <button
                  type="button"
                  className="ghost"
                  onClick={appendTemplateCondition}
                  disabled={!tplCondNodeId}
                >
                  Ajouter (ET)
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={replaceWithTemplateCondition}
                  disabled={!tplCondNodeId}
                >
                  Remplacer tout
                </button>
              </div>
            </div>
          )}
          <VarInsertSelect
            excludeId={id}
            onInsert={(token) =>
              patch(id, { condition: (data.condition || "") + token })
            }
          />
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
      <p className="pg-modal__hint">
        Texte + boutons (max 3) ou liste (&gt; 3 options). La réponse est
        disponible dans <code>{`{{${data.varKey || "…"}}}`}</code> pour le
        routeur en aval.
      </p>
      <div className="pg-modal__section">
        <span className="pg-modal__section-title">Relance sans réponse (optionnel)</span>
        <p className="pg-modal__hint">
          Reliez la sortie <strong>timeout</strong> du nœud à la suite (ex.
          rappel). Définissez la durée ci-dessous ; si le client répond avant,
          la relance est annulée.
        </p>
        <div className="pg-modal__row2">
          <label className="pg-modal__label">
            Délai
            <input
              className="pg-modal__input"
              type="number"
              min={0}
              step="any"
              value={data.timeoutDuration ?? ""}
              onChange={(e) =>
                patch(id, {
                  timeoutDuration:
                    e.target.value === "" ? "" : e.target.value,
                })
              }
              placeholder="ex. 48"
            />
          </label>
          <label className="pg-modal__label">
            Unité
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
      </div>
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
              {kind === "buttons" ? `Bouton ${i + 1}` : `Ligne ${i + 1}`} — titre
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
            <label className="pg-modal__label">
              Id payload Meta
              <input
                className="pg-modal__input"
                type="text"
                value={c.id || ""}
                placeholder={`btn_${i}`}
                onChange={(e) => {
                  const next = [...choices];
                  next[i] = { ...next[i], id: e.target.value };
                  setChoices(next);
                }}
              />
            </label>
            <label className="pg-modal__label">
              Variable session (optionnel)
              <input
                className="pg-modal__input"
                type="text"
                value={c.saveToVariable || ""}
                placeholder="ex. interetCoop"
                onChange={(e) => {
                  const next = [...choices];
                  next[i] = { ...next[i], saveToVariable: e.target.value || undefined };
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
      <p className="pg-modal__hint">
        Compare la valeur dans <code>réponse_*</code> du nœud précédent (bouton,
        texte…). Reliez chaque sortie du nœud à la suite du flux ; la sortie
        d’échappement = texte libre ou non reconnu (ex. branche Gemini).
      </p>
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
      <p className="pg-modal__hint">
        Arrêt bot, notification interne ou suite CRM (à brancher côté serveur).
        Sortie basse optionnelle pour enchaîner après l’action.
      </p>
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
        Assignation agent (référence / id)
        <input
          className="pg-modal__input"
          type="text"
          value={data.assignAgent || ""}
          onChange={(e) => patch(id, { assignAgent: e.target.value })}
          placeholder="user_id ou file d’attente"
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
    </div>
  );
}
