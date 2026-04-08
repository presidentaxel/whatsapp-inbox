import { extractVariablesFromComponents } from "../../utils/templateVariables";

export const WEEKDAYS = [
  { v: "1", l: "Lun" },
  { v: "2", l: "Mar" },
  { v: "3", l: "Mer" },
  { v: "4", l: "Jeu" },
  { v: "5", l: "Ven" },
  { v: "6", l: "Sam" },
  { v: "0", l: "Dim" },
];

export function collectVarIdsFromTemplate(template) {
  if (!template?.components) return [];
  const v = extractVariablesFromComponents(template.components);
  const merged = [...v.header, ...v.body, ...v.footer, ...v.buttons];
  return [...new Set(merged.map(String))];
}

export function extractQuickReplyButtons(template) {
  if (!template?.components) return [];
  const out = [];
  for (const comp of template.components) {
    if (String(comp.type || "").toUpperCase() !== "BUTTONS") continue;
    if (!Array.isArray(comp.buttons)) continue;
    for (const btn of comp.buttons) {
      const bt = String(btn.type || "").toUpperCase();
      if (bt === "QUICK_REPLY" && btn.text) {
        out.push({ type: "QUICK_REPLY", text: String(btn.text) });
      }
    }
  }
  return out;
}

export function extractCtaButtons(template) {
  if (!template?.components) return [];
  const out = [];
  for (const comp of template.components) {
    if (String(comp.type || "").toUpperCase() !== "BUTTONS") continue;
    if (!Array.isArray(comp.buttons)) continue;
    for (const btn of comp.buttons) {
      const bt = String(btn.type || "").toUpperCase();
      if (bt === "URL" && btn.text) {
        out.push({ type: "URL", text: String(btn.text) });
      }
      if (bt === "PHONE_NUMBER" && btn.text) {
        out.push({ type: "PHONE_NUMBER", text: String(btn.text) });
      }
    }
  }
  return out;
}

export function replyPredicateForButton(varKey, buttonText) {
  const esc = JSON.stringify(String(buttonText ?? ""));
  return `String(${varKey} ?? '').trim() === ${esc}`;
}

export function buildTemplateReplyPredicate(varKey, op, expected) {
  const esc = JSON.stringify(String(expected ?? ""));
  const v = varKey;
  if (op === "eq") {
    return `String(${v} ?? '').trim() === ${esc}`;
  }
  if (op === "contains") {
    return `String(${v} ?? '').includes(${esc})`;
  }
  if (op === "regex") {
    return `(function(){ try { return new RegExp(${esc}).test(String(${v} ?? '')); } catch (e) { return false; } })()`;
  }
  return "";
}

export function toggleDay(activeDays, day) {
  const set = new Set(activeDays || []);
  if (set.has(day)) set.delete(day);
  else set.add(day);
  return [...set].sort((a, b) => Number(a) - Number(b));
}

export function truncate(str, max) {
  const s = (str || "").trim();
  if (s.length <= max) return s || "—";
  return `${s.slice(0, max)}…`;
}

const TRIGGER_LABELS = {
  message_in: "Message",
  schedule: "Planification",
  webhook: "Webhook",
  manual: "Manuel",
  playground_audience: "Campagne",
};

export function summarizeStart(data) {
  const tt = data.triggerType || "message_in";
  const base = TRIGGER_LABELS[tt] || tt;
  if (tt === "schedule" && data.scheduleAt) {
    return `${base} · ${data.scheduleAt.replace("T", " ")}`;
  }
  if (tt === "message_in" && data.messageMatch && data.messageMatch !== "any") {
    return `${base} · ${data.messageMatch}${data.messageKeyword ? ` «${truncate(data.messageKeyword, 16)}»` : ""}`;
  }
  if (tt === "playground_audience") {
    const when = (data.campaignScheduledFor || "").replace("T", " ");
    return when ? `${base} · ${when}` : `${base} · groupe`;
  }
  return base;
}

export function summarizeTimeWindow(data) {
  const days = (data.activeDays || []).length;
  const d0 = data.startTime || "09:00";
  const d1 = data.endTime || "18:00";
  return `${d0}–${d1} · ${days}j`;
}

export function unitLabel(u) {
  if (u === "m") return "min";
  if (u === "h") return "h";
  if (u === "d") return "j";
  return "s";
}

/** Prompt système prêt à l’emploi (qualification statut VTC → mots-clés machine) */
export const DEFAULT_GEMINI_STATUT_ROUTER_PROMPT = `Tu es un routeur invisible pour un chatbot WhatsApp destiné à des chauffeurs VTC. Ta seule mission est d'analyser le texte libre de l'utilisateur et de le catégoriser parmi des choix stricts.
Contexte : L'utilisateur devait indiquer son statut professionnel actuel.
Texte de l'utilisateur : [INSERER LE TEXTE DU USER ICI]
Instructions :

S'il mentionne être à son compte, auto-entrepreneur, avoir sa boîte, SASU, EURL, indépendant -> Réponds EXACTEMENT par le mot : INDEPENDANT

S'il mentionne être salarié d'un capacitaire, rattaché, locataire, utiliser le compte d'un autre -> Réponds EXACTEMENT par le mot : RATTACHE

S'il mentionne avoir une société avec d'autres chauffeurs, une flotte -> Réponds EXACTEMENT par le mot : SOCIETE

Si sa phrase n'a aucun sens, est une insulte, ou hors sujet -> Réponds EXACTEMENT par le mot : INCONNU
Ne justifie pas, ne dis pas bonjour, renvoie uniquement le mot-clé brut.`;
