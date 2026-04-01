import { api } from "./axiosClient";

export const listPlaygroundFlows = (accountId) =>
  api.get(`/accounts/${accountId}/playground-flows`);

export const getPlaygroundFlow = (flowId) =>
  api.get(`/bot/playground-flows/${flowId}`);

export const createPlaygroundFlow = (payload) =>
  api.post("/bot/playground-flows", payload);

export const updatePlaygroundFlow = (flowId, payload) =>
  api.put(`/bot/playground-flows/${flowId}`, payload);

export const deletePlaygroundFlow = (flowId) =>
  api.delete(`/bot/playground-flows/${flowId}`);

export const setPlaygroundFlowDefault = (flowId) =>
  api.post(`/bot/playground-flows/${flowId}/set-default`);

export const duplicatePlaygroundFlow = (payload) =>
  api.post("/bot/playground-flows/duplicate", payload);

export const pastePlaygroundSubgraph = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/paste-subgraph`, payload);
