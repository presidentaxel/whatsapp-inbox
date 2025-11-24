import { api } from "./axiosClient";

export const fetchBotProfile = (accountId) =>
  api.get(`/bot/profile/${accountId}`);

export const saveBotProfile = (accountId, payload) =>
  api.put(`/bot/profile/${accountId}`, payload);

