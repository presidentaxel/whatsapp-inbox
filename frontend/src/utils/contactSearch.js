import { formatPhoneNumber } from "./formatPhone";

export function foldString(s) {
  return String(s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "");
}

function digitsOnly(s) {
  return String(s || "").replace(/\D/g, "");
}

function textTokens(s) {
  return foldString(s)
    .split(/[\s,.;+|/'"’._-]+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

/**
 * Indique si un contact correspond à la requête (nom affiché, nom WhatsApp, numéro, prénom/nom par mots).
 * @param {object} contact
 * @param {string} rawQuery
 */
export function contactMatchesSearch(contact, rawQuery) {
  const q = String(rawQuery || "").trim();
  if (!q) return true;

  const display = contact.display_name || "";
  const waName = contact.whatsapp_name || "";
  const waNum = contact.whatsapp_number || "";
  const formattedPhone = formatPhoneNumber(waNum);

  const qFold = foldString(q);
  const qDigitsAll = digitsOnly(q);

  const textBlob = foldString([display, waName, waNum, formattedPhone].filter(Boolean).join(" "));
  if (textBlob.includes(qFold)) return true;

  if (qDigitsAll.length >= 2 && digitsOnly(waNum).includes(qDigitsAll)) return true;

  const nameTokens = [...textTokens(display), ...textTokens(waName)];
  const queryTokens = q
    .trim()
    .split(/\s+/)
    .map((t) => foldString(t))
    .filter(Boolean);

  if (!queryTokens.length) return false;

  const eachMatches = queryTokens.every((qt) => {
    if (/^\d+$/.test(qt)) {
      return digitsOnly(waNum).includes(qt);
    }
    return (
      textBlob.includes(qt) || nameTokens.some((nt) => nt.includes(qt) || nt.startsWith(qt))
    );
  });
  if (eachMatches) return true;

  return false;
}

export function filterContactsBySearch(contacts, rawQuery) {
  if (!rawQuery?.trim()) return contacts;
  return contacts.filter((c) => contactMatchesSearch(c, rawQuery));
}
