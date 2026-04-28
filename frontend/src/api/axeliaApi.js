import { api } from "./axiosClient";

export const getAxeliaConversations = () => api.get("/axelia/conversations");

export const createAxeliaConversation = (payload) =>
  api.post("/axelia/conversations", payload);

export const patchAxeliaConversation = (conversationId, payload) =>
  api.patch(`/axelia/conversations/${conversationId}`, payload);

export const getAxeliaMessages = (conversationId) =>
  api.get(`/axelia/conversations/${conversationId}/messages`);

export const postAxeliaChat = (payload) => api.post("/axelia/chat", payload);

export const postAxeliaRegenerate = (conversationId) =>
  api.post(`/axelia/conversations/${conversationId}/regenerate`);

export const patchAxeliaMessageRating = (messageId, payload) =>
  api.patch(`/axelia/messages/${messageId}/rating`, payload);
