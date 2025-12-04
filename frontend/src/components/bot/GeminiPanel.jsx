import { useEffect, useMemo, useState } from "react";
import { FiPlus, FiTrash2 } from "react-icons/fi";
import { fetchBotProfile, saveBotProfile } from "../../api/botApi";

const randomId = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `field_${Math.random().toString(36).slice(2, 10)}`;

const createOffer = () => ({ category: "", content: "", _id: randomId() });
const createProcedure = () => ({ name: "", steps: "", _id: randomId() });
const createFaq = () => ({ question: "", answer: "", _id: randomId() });
const createSpecialCase = () => ({ case: "", response: "", _id: randomId() });

const emptyTemplate = {
  system_rules: {
    language: "Français",
    tone: "Professionnel, clair, courtois, concis.",
    role: "Assistant SAV WhatsApp pour l'entreprise.",
    mission:
      "Répondre aux clients uniquement à partir du playbook, sans inventer, en restant dans le périmètre de l'entreprise.",
    style:
      "Commencer par une phrase de réponse directe, puis ajouter quelques puces si nécessaire (étapes, conditions). Pas de gras ni de titres Markdown.",
    priority:
      "1) Playbook structuré (SYSTEM RULES, INFOS ENTREPRISE, OFFRES, CONDITIONS, CAS SPÉCIAUX, LIENS, ESCALADE, RÈGLES SPÉCIALES BOT) 2) Liens autorisés 3) Historique conversationnel 4) Bon sens (sans inventer).",
    response_policy:
      'Si une information est absente ou insuffisante dans le playbook, répondre uniquement : "Je me renseigne auprès d\'un collègue et je reviens vers vous au plus vite".',
    security:
      "Ne jamais demander ni accepter de mot de passe ou code de sécurité. Respect de la confidentialité et du RGPD.",
  },
  company: {
    name: "",
    address: "",
    hours_block: "",
    zone: "",
    rendezvous: "",
    activity: "",
  },
  offers: [],
  conditions: {
    zone: "",
    payment: "",
    engagement: "",
    restrictions: "",
    documents: "",
  },
  procedures: [],
  faq: [],
  special_cases: [],
  links: {
    site: "",
    products: "",
    form: "",
    other: "",
  },
  escalation: {
    procedure: "",
    contact: "",
    hours: "",
  },
  special_rules:
    'Le bot reste concis et ne fait pas de small talk. Si une question nécessite une information absente du playbook, il répond uniquement : "Je me renseigne auprès d\'un collègue et je reviens vers vous au plus vite". Il n’encourage pas les appels ni les contacts directs ; il peut proposer : "Vous pouvez passer directement au bureau".',
};

const withInternalIds = (items, factory) => {
  if (!Array.isArray(items) || items.length === 0) {
    return [factory()];
  }
  return items.map((item) => ({
    ...factory(),
    ...item,
    _id: item._id || randomId(),
  }));
};

const ensureTemplateConfig = (incoming = {}) => ({
  system_rules: {
    ...emptyTemplate.system_rules,
    ...(incoming.system_rules || {}),
  },
  company: {
    ...emptyTemplate.company,
    ...(incoming.company || {}),
  },
  offers: withInternalIds(incoming.offers, createOffer),
  conditions: {
    ...emptyTemplate.conditions,
    ...(incoming.conditions || {}),
  },
  procedures: withInternalIds(incoming.procedures, createProcedure),
  faq: withInternalIds(incoming.faq, createFaq),
  special_cases: withInternalIds(incoming.special_cases, createSpecialCase),
  links: {
    ...emptyTemplate.links,
    ...(incoming.links || {}),
  },
  escalation: {
    ...emptyTemplate.escalation,
    ...(incoming.escalation || {}),
  },
  special_rules:
    typeof incoming.special_rules === "string" && incoming.special_rules.trim()
      ? incoming.special_rules
      : emptyTemplate.special_rules,
});

const stripTemplateIds = (template) => ({
  ...template,
  offers: template.offers.map(({ _id, ...rest }) => rest),
  procedures: template.procedures.map(({ _id, ...rest }) => rest),
  faq: template.faq.map(({ _id, ...rest }) => rest),
  special_cases: template.special_cases.map(({ _id, ...rest }) => rest),
});

const createEmptyProfile = () => ({
  business_name: "",
  description: "",
  address: "",
  hours: "",
  knowledge_base: "",
  custom_fields: [],
  template_config: ensureTemplateConfig({}),
});

const buildTemplatePreview = (template) => {
  if (!template) return "";

  const lines = [];

  const sys = template.system_rules || {};
  if (Object.values(sys).some(Boolean)) {
    lines.push("## SYSTEM RULES");
    if (sys.role) lines.push(`Rôle : ${sys.role}`);
    if (sys.mission) lines.push(`Mission : ${sys.mission}`);
    if (sys.language) lines.push(`Langue par défaut : ${sys.language}`);
    if (sys.tone) lines.push(`Ton attendu : ${sys.tone}`);
    if (sys.style) lines.push(`Style de réponse : ${sys.style}`);
    if (sys.priority) lines.push(`Priorité des sources : ${sys.priority}`);
    if (sys.response_policy)
      lines.push(`Politique de réponse : ${sys.response_policy}`);
    if (sys.security) lines.push(`Règles de sécurité : ${sys.security}`);
  }

  const company = template.company || {};
  if (Object.values(company).some(Boolean)) {
    lines.push("\n## INFOS ENTREPRISE");
    if (company.name) lines.push(`Nom entreprise : ${company.name}`);
    if (company.address) lines.push(`Adresse : ${company.address}`);
    if (company.hours_block)
      lines.push(`Horaires détaillés : ${company.hours_block}`);
    if (company.zone) lines.push(`Zone couverte : ${company.zone}`);
    if (company.rendezvous)
      lines.push(`Rendez-vous : ${company.rendezvous}`);
    if (company.activity)
      lines.push(`Activité principale : ${company.activity}`);
  }

  if (template.offers?.length) {
    lines.push("\n## OFFRES / SERVICES");
    template.offers.forEach((offer) => {
      if (!offer.category && !offer.content) return;
      if (offer.category) lines.push(`### Catégorie : ${offer.category}`);
      if (offer.content) lines.push(offer.content);
    });
  }

  const conditions = template.conditions || {};
  if (Object.values(conditions).some(Boolean)) {
    lines.push("\n## CONDITIONS & PROCÉDURES");
    if (conditions.zone) lines.push(`Zone : ${conditions.zone}`);
    if (conditions.payment)
      lines.push(`Paiement / dépôt : ${conditions.payment}`);
    if (conditions.engagement)
      lines.push(`Engagement : ${conditions.engagement}`);
    if (conditions.restrictions)
      lines.push(`Restrictions : ${conditions.restrictions}`);
    if (conditions.documents)
      lines.push(`Documents requis : ${conditions.documents}`);
  }

  if (template.procedures?.length) {
    lines.push("\n## PROCÉDURES SIMPLIFIÉES");
    template.procedures.forEach((proc) => {
      if (!proc.name && !proc.steps) return;
      lines.push(`### ${proc.name || "Procédure"}`);
      if (proc.steps) lines.push(proc.steps);
    });
  }

  if (template.faq?.length) {
    lines.push("\n## FAQ");
    template.faq.forEach((item) => {
      if (!item.question && !item.answer) return;
      if (item.question) lines.push(`Q : ${item.question}`);
      if (item.answer) lines.push(`R : ${item.answer}`);
    });
  }

  if (template.special_cases?.length) {
    lines.push("\n## CAS SPÉCIAUX");
    template.special_cases.forEach((item) => {
      if (!item.case && !item.response) return;
      if (item.case) lines.push(`Si ${item.case} :`);
      if (item.response) lines.push(item.response);
    });
  }

  const links = template.links || {};
  if (Object.values(links).some(Boolean)) {
    lines.push("\n## LIENS UTILES");
    if (links.site) lines.push(`Site : ${links.site}`);
    if (links.products) lines.push(`Produits : ${links.products}`);
    if (links.form) lines.push(`Formulaire : ${links.form}`);
    if (links.other) lines.push(`Autre : ${links.other}`);
  }

  const escalation = template.escalation || {};
  if (Object.values(escalation).some(Boolean)) {
    lines.push("\n## ESCALADE HUMAIN");
    if (escalation.procedure)
      lines.push(`Procédure : ${escalation.procedure}`);
    if (escalation.contact) lines.push(`Contact : ${escalation.contact}`);
    if (escalation.hours) lines.push(`Horaires : ${escalation.hours}`);
  }

  if (template.special_rules) {
    lines.push("\n## RÈGLES SPÉCIALES BOT");
    lines.push(template.special_rules);
  }

  return lines.filter(Boolean).join("\n").trim();
};

export default function GeminiPanel({ accountId, accounts, onAccountChange }) {
  const [form, setForm] = useState(createEmptyProfile());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);

  const templatePreview = useMemo(
    () => buildTemplatePreview(form.template_config),
    [form.template_config]
  );

  useEffect(() => {
    if (!accountId) {
      setForm(createEmptyProfile());
      return;
    }
    setLoading(true);
    setError("");
    fetchBotProfile(accountId)
      .then((res) => {
        const data = res.data ?? {};
        setForm({
          business_name: data.business_name || "",
          description: data.description || "",
          address: data.address || "",
          hours: data.hours || "",
          knowledge_base: data.knowledge_base || "",
          custom_fields: (data.custom_fields || []).map((field) => ({
            id: field.id || randomId(),
            label: field.label || "",
            value: field.value || "",
          })),
          template_config: ensureTemplateConfig(data.template_config || {}),
        });
      })
      .catch(() => setError("Impossible de charger la configuration Gemini."))
      .finally(() => setLoading(false));
  }, [accountId]);

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSuccess(false);
  };

  const updateTemplateField = (section, key, value) => {
    setForm((prev) => ({
      ...prev,
      template_config: {
        ...prev.template_config,
        [section]: {
          ...prev.template_config[section],
          [key]: value,
        },
      },
    }));
    setSuccess(false);
  };

  const updateTemplateListItem = (section, index, key, value) => {
    setForm((prev) => ({
      ...prev,
      template_config: {
        ...prev.template_config,
        [section]: prev.template_config[section].map((item, idx) =>
          idx === index ? { ...item, [key]: value } : item
        ),
      },
    }));
    setSuccess(false);
  };

  const updateTemplateRoot = (key, value) => {
    setForm((prev) => ({
      ...prev,
      template_config: {
        ...prev.template_config,
        [key]: value,
      },
    }));
    setSuccess(false);
  };

  const addTemplateItem = (section, factory) => {
    setForm((prev) => ({
      ...prev,
      template_config: {
        ...prev.template_config,
        [section]: [...prev.template_config[section], factory()],
      },
    }));
  };

  const removeTemplateItem = (section, index, factory) => {
    setForm((prev) => {
      const next = prev.template_config[section].filter((_, idx) => idx !== index);
      return {
        ...prev,
        template_config: {
          ...prev.template_config,
          [section]: next.length ? next : [factory()],
        },
      };
    });
  };

  const updateCustomField = (id, key, value) => {
    setForm((prev) => ({
      ...prev,
      custom_fields: prev.custom_fields.map((field) =>
        field.id === id ? { ...field, [key]: value } : field
      ),
    }));
    setSuccess(false);
  };

  const addCustomField = () => {
    setForm((prev) => ({
      ...prev,
      custom_fields: [
        ...prev.custom_fields,
        { id: randomId(), label: "", value: "" },
      ],
    }));
  };

  const removeCustomField = (id) => {
    setForm((prev) => ({
      ...prev,
      custom_fields: prev.custom_fields.filter((field) => field.id !== id),
    }));
  };

  const handleSave = async () => {
    if (!accountId) return;
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      await saveBotProfile(accountId, {
        ...form,
        template_config: stripTemplateIds(form.template_config),
      });
      setSuccess(true);
    } catch (err) {
      console.error(err);
      setError("Impossible d'enregistrer ces informations pour le moment.");
    } finally {
      setSaving(false);
    }
  };

  const handleCopyPreview = () => {
    updateField("knowledge_base", templatePreview);
  };

  if (!accounts.length) {
    return (
      <div className="panel">
        <h3>Assistant Gemini</h3>
        <p>Ajoute un compte WhatsApp pour configurer le bot.</p>
      </div>
    );
  }

  if (!accountId) {
    return (
      <div className="panel">
        <h3>Assistant Gemini</h3>
        <p>Sélectionne un compte dans la colonne de gauche pour commencer.</p>
      </div>
    );
  }

  return (
    <div className="panel bot-panel">
      <header className="bot-panel__header">
        <div>
          <h3>Assistant Gemini</h3>
          <p>
            Définis un playbook structuré : le bot ne répond que depuis ces
            sections. En dehors, il applique la phrase “Je me renseigne auprès
            d’un collègue…”.
          </p>
        </div>
        <div className="bot-panel__account-select">
          <label>Compte</label>
          <select
            value={accountId ?? ""}
            onChange={(e) => onAccountChange?.(e.target.value)}
          >
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {loading ? (
        <p>Chargement des informations…</p>
      ) : (
        <>
          {error && <div className="alert alert-error">{error}</div>}
          {success && <div className="alert alert-success">Profil mis à jour ✅</div>}

          <section className="bot-panel__section">
            <h4>Profil d'entreprise</h4>
            <div className="form-grid">
              <label>
                Nom affiché
                <input
                  value={form.business_name}
                  onChange={(e) => updateField("business_name", e.target.value)}
                  placeholder="Nom de l'entreprise"
                />
              </label>
              <label>
                Adresse
                <input
                  value={form.address}
                  onChange={(e) => updateField("address", e.target.value)}
                  placeholder="Adresse postale"
                />
              </label>
              <label>
                Horaires synthétiques
                <input
                  value={form.hours}
                  onChange={(e) => updateField("hours", e.target.value)}
                  placeholder="Lun-Ven 9h-18h"
                />
              </label>
            </div>
            <label>
              Description / ton libre
              <textarea
                value={form.description}
                onChange={(e) => updateField("description", e.target.value)}
                rows={3}
              />
            </label>
          </section>

          <TemplateSections
            form={form}
            updateTemplateField={updateTemplateField}
            updateTemplateListItem={updateTemplateListItem}
            addTemplateItem={addTemplateItem}
            removeTemplateItem={removeTemplateItem}
            updateTemplateRoot={updateTemplateRoot}
          />

          <section className="bot-panel__section">
            <div className="bot-panel__section-header">
              <h4>Aperçu généré</h4>
              <button type="button" className="ghost" onClick={handleCopyPreview}>
                Copier dans la base
              </button>
            </div>
            <textarea value={templatePreview} readOnly rows={10} />
          </section>

          <section className="bot-panel__section">
            <h4>Base de connaissances libre</h4>
            <textarea
              value={form.knowledge_base}
              onChange={(e) => updateField("knowledge_base", e.target.value)}
              rows={6}
              placeholder="Suppléments, scripts commerciaux, etc."
            />
          </section>

          <section className="bot-panel__section">
            <div className="bot-panel__section-header">
              <h4>Champs personnalisés</h4>
              <button type="button" className="ghost" onClick={addCustomField}>
                <FiPlus /> Ajouter un champ
              </button>
            </div>
            {form.custom_fields.length === 0 && (
              <p className="muted">Aucun champ personnalisé pour l'instant.</p>
            )}
            {form.custom_fields.map((field) => (
              <div key={field.id} className="custom-field">
                <input
                  value={field.label}
                  onChange={(e) =>
                    updateCustomField(field.id, "label", e.target.value)
                  }
                  placeholder="Label (ex. Numéro SAV)"
                />
                <input
                  value={field.value}
                  onChange={(e) =>
                    updateCustomField(field.id, "value", e.target.value)
                  }
                  placeholder="Valeur"
                />
                <button
                  type="button"
                  className="icon danger"
                  onClick={() => removeCustomField(field.id)}
                >
                  <FiTrash2 />
                </button>
              </div>
            ))}
          </section>

          <div className="bot-panel__footer">
            <button type="button" onClick={handleSave} disabled={saving}>
              {saving ? "Enregistrement..." : "Sauvegarder"}
            </button>
            <p className="muted">
              Gemini ne répond que si le bouton "Bot" est activé sur une conversation.
              Désactive-le pour reprendre la main manuellement.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

function TemplateSections({
  form,
  updateTemplateField,
  updateTemplateListItem,
  addTemplateItem,
  removeTemplateItem,
  updateTemplateRoot,
}) {
  const template = form.template_config;

  return (
    <>
      <section className="bot-panel__section">
        <h4>1. Règles système</h4>
        <div className="form-grid">
          <label>
            Langue par défaut
            <input
              value={template.system_rules.language}
              onChange={(e) =>
                updateTemplateField("system_rules", "language", e.target.value)
              }
              placeholder="Français"
            />
          </label>
          <label>
            Ton
            <input
              value={template.system_rules.tone}
              onChange={(e) =>
                updateTemplateField("system_rules", "tone", e.target.value)
              }
              placeholder="Professionnel, clair, courtois."
            />
          </label>
        </div>
        <label>
          Mission
          <textarea
            value={template.system_rules.mission}
            onChange={(e) =>
              updateTemplateField("system_rules", "mission", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Style
          <textarea
            value={template.system_rules.style}
            onChange={(e) =>
              updateTemplateField("system_rules", "style", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Priorité des sources
          <textarea
            value={template.system_rules.priority}
            onChange={(e) =>
              updateTemplateField("system_rules", "priority", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Politique de réponse
          <textarea
            value={template.system_rules.response_policy}
            onChange={(e) =>
              updateTemplateField("system_rules", "response_policy", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Sécurité
          <textarea
            value={template.system_rules.security}
            onChange={(e) =>
              updateTemplateField("system_rules", "security", e.target.value)
            }
            rows={2}
          />
        </label>
      </section>

      <section className="bot-panel__section">
        <h4>2. Infos entreprise (structure)</h4>
        <div className="form-grid">
          <label>
            Nom entreprise
            <input
              value={template.company.name}
              onChange={(e) =>
                updateTemplateField("company", "name", e.target.value)
              }
            />
          </label>
          <label>
            Zone couverte / activité
            <input
              value={template.company.zone}
              onChange={(e) =>
                updateTemplateField("company", "zone", e.target.value)
              }
              placeholder="Ex : Île-de-France, location VTC + rattachement"
            />
          </label>
          <label>
            Rendez-vous
            <input
              value={template.company.rendezvous}
              onChange={(e) =>
                updateTemplateField("company", "rendezvous", e.target.value)
              }
              placeholder="Avec RDV / Sans RDV"
            />
          </label>
        </div>
        <label>
          Horaires détaillés
          <textarea
            value={template.company.hours_block}
            onChange={(e) =>
              updateTemplateField("company", "hours_block", e.target.value)
            }
            rows={2}
            placeholder="Lun-Ven : 10h-18h. Sam-Dim : fermé."
          />
        </label>
        <label>
          Activité principale
          <textarea
            value={template.company.activity}
            onChange={(e) =>
              updateTemplateField("company", "activity", e.target.value)
            }
            rows={2}
          />
        </label>
      </section>

      <section className="bot-panel__section">
        <div className="bot-panel__section-header">
          <h4>3. Offres / produits / services</h4>
          <button
            type="button"
            className="ghost"
            onClick={() => addTemplateItem("offers", createOffer)}
          >
            <FiPlus /> Ajouter une catégorie
          </button>
        </div>
        {template.offers.map((offer, index) => (
          <div className="bot-template-card" key={offer._id}>
            <div className="card-header">
              <label>
                Catégorie
                <input
                  value={offer.category}
                  onChange={(e) =>
                    updateTemplateListItem(
                      "offers",
                      index,
                      "category",
                      e.target.value
                    )
                  }
                  placeholder="Ex : Location sans engagement"
                />
              </label>
              <button
                type="button"
                className="icon danger"
                onClick={() =>
                  removeTemplateItem("offers", index, createOffer)
                }
              >
                <FiTrash2 />
              </button>
            </div>
            <label>
              Détails (tableau, puces…)
              <textarea
                value={offer.content}
                onChange={(e) =>
                  updateTemplateListItem(
                    "offers",
                    index,
                    "content",
                    e.target.value
                  )
                }
                rows={3}
                placeholder="Produit / Service | Prix | Conditions | Notes"
              />
            </label>
          </div>
        ))}
      </section>

      <section className="bot-panel__section">
        <h4>4. Conditions & documents</h4>
        <label>
          Zone / règles
          <textarea
            value={template.conditions.zone}
            onChange={(e) =>
              updateTemplateField("conditions", "zone", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Paiement / dépôt
          <textarea
            value={template.conditions.payment}
            onChange={(e) =>
              updateTemplateField("conditions", "payment", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Engagement
          <textarea
            value={template.conditions.engagement}
            onChange={(e) =>
              updateTemplateField("conditions", "engagement", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Restrictions
          <textarea
            value={template.conditions.restrictions}
            onChange={(e) =>
              updateTemplateField("conditions", "restrictions", e.target.value)
            }
            rows={2}
          />
        </label>
        <label>
          Documents requis
          <textarea
            value={template.conditions.documents}
            onChange={(e) =>
              updateTemplateField("conditions", "documents", e.target.value)
            }
            rows={3}
          />
        </label>
      </section>

      <section className="bot-panel__section">
        <div className="bot-panel__section-header">
          <h4>5. Procédures simplifiées</h4>
          <button
            type="button"
            className="ghost"
            onClick={() => addTemplateItem("procedures", createProcedure)}
          >
            <FiPlus /> Ajouter une procédure
          </button>
        </div>
        {template.procedures.map((proc, index) => (
          <div className="bot-template-card" key={proc._id}>
            <div className="card-header">
              <label>
                Nom de la procédure
                <input
                  value={proc.name}
                  onChange={(e) =>
                    updateTemplateListItem(
                      "procedures",
                      index,
                      "name",
                      e.target.value
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="icon danger"
                onClick={() =>
                  removeTemplateItem("procedures", index, createProcedure)
                }
              >
                <FiTrash2 />
              </button>
            </div>
            <label>
              Étapes / script
              <textarea
                value={proc.steps}
                onChange={(e) =>
                  updateTemplateListItem(
                    "procedures",
                    index,
                    "steps",
                    e.target.value
                  )
                }
                rows={3}
              />
            </label>
          </div>
        ))}
      </section>

      <section className="bot-panel__section">
        <div className="bot-panel__section-header">
          <h4>6. FAQ</h4>
          <button
            type="button"
            className="ghost"
            onClick={() => addTemplateItem("faq", createFaq)}
          >
            <FiPlus /> Ajouter une question
          </button>
        </div>
        {template.faq.map((item, index) => (
          <div className="bot-template-card" key={item._id}>
            <div className="card-header">
              <label>
                Question
                <input
                  value={item.question}
                  onChange={(e) =>
                    updateTemplateListItem(
                      "faq",
                      index,
                      "question",
                      e.target.value
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="icon danger"
                onClick={() =>
                  removeTemplateItem("faq", index, createFaq)
                }
              >
                <FiTrash2 />
              </button>
            </div>
            <label>
              Réponse
              <textarea
                value={item.answer}
                onChange={(e) =>
                  updateTemplateListItem(
                    "faq",
                    index,
                    "answer",
                    e.target.value
                  )
                }
                rows={3}
              />
            </label>
          </div>
        ))}
      </section>

      <section className="bot-panel__section">
        <div className="bot-panel__section-header">
          <h4>7. Cas spéciaux</h4>
          <button
            type="button"
            className="ghost"
            onClick={() =>
              addTemplateItem("special_cases", createSpecialCase)
            }
          >
            <FiPlus /> Ajouter un cas
          </button>
        </div>
        {template.special_cases.map((item, index) => (
          <div className="bot-template-card" key={item._id}>
            <div className="card-header">
              <label>
                Condition (ex : hors IDF, week-end…)
                <input
                  value={item.case}
                  onChange={(e) =>
                    updateTemplateListItem(
                      "special_cases",
                      index,
                      "case",
                      e.target.value
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="icon danger"
                onClick={() =>
                  removeTemplateItem(
                    "special_cases",
                    index,
                    createSpecialCase
                  )
                }
              >
                <FiTrash2 />
              </button>
            </div>
            <label>
              Réponse type
              <textarea
                value={item.response}
                onChange={(e) =>
                  updateTemplateListItem(
                    "special_cases",
                    index,
                    "response",
                    e.target.value
                  )
                }
                rows={3}
              />
            </label>
          </div>
        ))}
      </section>

      <section className="bot-panel__section">
        <h4>8. Liens utiles</h4>
        <div className="form-grid">
          <label>
            Site
            <input
              value={template.links.site}
              onChange={(e) =>
                updateTemplateField("links", "site", e.target.value)
              }
            />
          </label>
          <label>
            Page produits
            <input
              value={template.links.products}
              onChange={(e) =>
                updateTemplateField("links", "products", e.target.value)
              }
            />
          </label>
          <label>
            Formulaire
            <input
              value={template.links.form}
              onChange={(e) =>
                updateTemplateField("links", "form", e.target.value)
              }
            />
          </label>
          <label>
            Autre lien
            <input
              value={template.links.other}
              onChange={(e) =>
                updateTemplateField("links", "other", e.target.value)
              }
            />
          </label>
        </div>
      </section>

      <section className="bot-panel__section">
        <h4>9. Escalade humain (interne)</h4>
        <label>
          Procédure
          <textarea
            value={template.escalation.procedure}
            onChange={(e) =>
              updateTemplateField("escalation", "procedure", e.target.value)
            }
            rows={2}
          />
        </label>
        <div className="form-grid">
          <label>
            Contact
            <input
              value={template.escalation.contact}
              onChange={(e) =>
                updateTemplateField("escalation", "contact", e.target.value)
              }
            />
          </label>
          <label>
            Horaires du contact
            <input
              value={template.escalation.hours}
              onChange={(e) =>
                updateTemplateField("escalation", "hours", e.target.value)
              }
            />
          </label>
        </div>
      </section>

      <section className="bot-panel__section">
        <h4>10. Règles spéciales bot</h4>
        <textarea
          value={template.special_rules}
          onChange={(e) =>
            updateTemplateRoot("special_rules", e.target.value)
          }
          rows={4}
        />
      </section>
    </>
  );
}