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

/** Chat assistant Playground (explications + graphe optionnel). */
export const postPlaygroundAssistant = (payload) =>
  api.post("/bot/playground-flows/assistant", payload);

/** Fils de discussion persistés (nom, messages, masquage doux). */
export const listPlaygroundAssistThreads = ({ accountId, flowId, archived = false }) =>
  api.get("/bot/playground-flows/assist-threads", {
    params: {
      account_id: accountId,
      flow_id: flowId,
      archived: archived ? true : undefined,
    },
  });

export const createPlaygroundAssistThread = (payload) =>
  api.post("/bot/playground-flows/assist-threads", payload);

export const updatePlaygroundAssistThread = (threadId, payload) =>
  api.put(`/bot/playground-flows/assist-threads/${threadId}`, payload);

export const deletePlaygroundAssistThread = (threadId) =>
  api.delete(`/bot/playground-flows/assist-threads/${threadId}`);

export const restorePlaygroundAssistThread = (threadId) =>
  api.patch(`/bot/playground-flows/assist-threads/${threadId}/restore`);
