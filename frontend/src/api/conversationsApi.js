import { api } from "./axiosClient";

export const getConversations = (accountId) =>
  api.get("/conversations", { params: { account_id: accountId } });

export const markConversationRead = (conversationId) =>
  api.post(`/conversations/${conversationId}/read`);

export const toggleConversationFavorite = (conversationId, favorite) =>
  api.post(`/conversations/${conversationId}/favorite`, { favorite });

export const toggleConversationBotMode = (conversationId, enabled) =>
  api.post(`/conversations/${conversationId}/bot`, { enabled });