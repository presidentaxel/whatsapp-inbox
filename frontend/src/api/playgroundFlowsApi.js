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

/** Planifie le lancement du graphe pour le groupe (entry_node_id = id React du nœud Entrée campagne). */
export const schedulePlaygroundFlowLaunch = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/schedule-flow-launch`, payload);

/** Liste → conversations liées à ce scénario + bot mode playground ; broadcast_group_id optionnel. */
export const importPlaygroundAudience = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/import-audience`, payload);

export const importPlaygroundAudienceCsv = (flowId, file, broadcastGroupId = "") => {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("broadcast_group_id", broadcastGroupId || "");
  return api.post(`/bot/playground-flows/${flowId}/import-audience-csv`, fd);
};

/** Lie le numéro de test réservé à ce scénario et retourne la conversation (bot playground). */
export const ensurePlaygroundSandboxSession = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/sandbox-session`, payload);

/** Efface les messages du bac à sable et réinitialise l’état du flux pour ce scénario. */
export const resetPlaygroundSandboxSession = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/sandbox-reset`, payload);

/** Simule un message entrant « contact » (déclenche le scénario comme en prod, bac à sable WhatsApp). */
export const simulatePlaygroundInbound = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/simulate-inbound`, payload);

/** Enchaîne plusieurs messages simulés sur la même conversation bac à sable (phrases de test). */
export const simulatePlaygroundInboundBatch = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/simulate-inbound-batch`, payload);

/** Simule un lancement campagne (nœud start playground_audience), sans message contact. */
export const simulatePlaygroundCampaignLaunch = (flowId, payload) =>
  api.post(`/bot/playground-flows/${flowId}/simulate-campaign-launch`, payload);

/** Chat assistant Playground (explications + graphe optionnel). `config` peut inclure `signal` (AbortController). */
export const postPlaygroundAssistant = (payload, config = {}) =>
  api.post("/bot/playground-flows/assistant", payload, config);

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
