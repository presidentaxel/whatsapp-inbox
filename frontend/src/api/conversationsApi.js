import { api } from "./axiosClient";

export const getConversations = (accountId, params = {}) => {
  const queryParams = new URLSearchParams();
  queryParams.append('account_id', accountId);
  if (params.limit) queryParams.append('limit', params.limit);
  if (params.cursor) queryParams.append('cursor', params.cursor);
  if (params.updated_since) queryParams.append('updated_since', params.updated_since);
  return api.get(`/conversations?${queryParams.toString()}`);
};

export const markConversationRead = (conversationId) =>
  api.post(`/conversations/${conversationId}/read`);

export const markConversationUnread = (conversationId) =>
  api.post(`/conversations/${conversationId}/unread`);

export const toggleConversationFavorite = (conversationId, favorite) =>
  api.post(`/conversations/${conversationId}/favorite`, { favorite });

/**
 * @param {object} opts
 * @param {boolean} opts.enabled
 * @param {'gemini'|'playground'|undefined} [opts.reply_mode] - si omis, le mode en base est conservé
 */
export const toggleConversationBotMode = (conversationId, opts) =>
  api.post(`/conversations/${conversationId}/bot`, opts);

/** null = flux par défaut du compte */
export const setConversationPlaygroundFlow = (conversationId, playgroundFlowId) =>
  api.post(`/conversations/${conversationId}/playground-flow`, {
    playground_flow_id: playgroundFlowId,
  });

export const findOrCreateConversation = (accountId, phoneNumber) =>
  api.post("/conversations/find-or-create", { account_id: accountId, phone_number: phoneNumber });