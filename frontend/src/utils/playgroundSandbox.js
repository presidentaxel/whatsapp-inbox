/**
 * Conversation réservée au bac à sable Playground (aligné backend conversation_service).
 * Ne doit pas apparaître dans la liste inbox principale.
 */
export const PLAYGROUND_SANDBOX_CLIENT_NUMBER = "33999999901";

export function isPlaygroundSandboxConversation(conv) {
  if (!conv || typeof conv !== "object") return false;
  const n = conv.client_number ?? conv.contacts?.whatsapp_number;
  return String(n ?? "").replace(/\s/g, "") === PLAYGROUND_SANDBOX_CLIENT_NUMBER;
}

export function excludePlaygroundSandboxConversations(list) {
  if (!Array.isArray(list)) return [];
  return list.filter((c) => !isPlaygroundSandboxConversation(c));
}
