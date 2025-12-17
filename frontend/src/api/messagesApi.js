import { api } from "./axiosClient";

export const getMessages = (id, params = {}) => {
  const queryParams = new URLSearchParams();
  if (params.limit) queryParams.append('limit', params.limit);
  if (params.before) queryParams.append('before', params.before);
  const queryString = queryParams.toString();
  return api.get(`/messages/${id}${queryString ? `?${queryString}` : ''}`);
};
export const sendMessage = (data) => api.post("/messages/send", data);
export const sendMediaMessage = (data) => api.post("/messages/send-media", data);
export const sendInteractiveMessage = (data) => api.post("/messages/send-interactive", data);
export const addReaction = (data) => api.post("/messages/reactions/add", data);
export const removeReaction = (data) => api.post("/messages/reactions/remove", data);
export const editMessage = (id, data) => api.patch(`/messages/${id}`, data);
export const deleteMessageApi = (id, data) => api.post(`/messages/${id}/delete`, data);
export const permanentlyDeleteMessage = (id) => api.delete(`/messages/${id}`);
export const getMessagePrice = (conversationId) => api.get(`/messages/price/${conversationId}`);
export const checkFreeWindow = (conversationId) => api.get(`/messages/free-window/${conversationId}`);