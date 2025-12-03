import { api } from "./axiosClient";

export const getMessages = (id) => api.get(`/messages/${id}`);
export const sendMessage = (data) => api.post("/messages/send", data);
export const sendMediaMessage = (data) => api.post("/messages/send-media", data);
export const sendInteractiveMessage = (data) => api.post("/messages/send-interactive", data);
export const addReaction = (data) => api.post("/messages/reactions/add", data);
export const removeReaction = (data) => api.post("/messages/reactions/remove", data);