import { api } from "./axiosClient";

export const getConversations = (accountId, params = {}) => {
  const queryParams = new URLSearchParams();
  queryParams.append('account_id', accountId);
  if (params.limit) queryParams.append('limit', params.limit);
  if (params.cursor) queryParams.append('cursor', params.cursor);
  return api.get(`/conversations?${queryParams.toString()}`);
};

export const markConversationRead = (conversationId) =>
  api.post(`/conversations/${conversationId}/read`);

export const markConversationUnread = (conversationId) =>
  api.post(`/conversations/${conversationId}/unread`);

export const toggleConversationFavorite = (conversationId, favorite) =>
  api.post(`/conversations/${conversationId}/favorite`, { favorite });

export const toggleConversationBotMode = (conversationId, enabled) =>
  api.post(`/conversations/${conversationId}/bot`, { enabled });

export const findOrCreateConversation = (accountId, phoneNumber) =>
  api.post("/conversations/find-or-create", { account_id: accountId, phone_number: phoneNumber });