import { api } from "./axiosClient";

export const getMessages = (id) => api.get(`/messages/${id}`);
export const sendMessage = (data) => api.post("/messages/send", data);