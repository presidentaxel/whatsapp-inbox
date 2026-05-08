import { api } from "./axiosClient";

export const listAgentStudioConfigs = (accountId) =>
  api.get("/agent-studio/configs", { params: { account_id: accountId } });

export const getAgentStudioConfig = (configId) =>
  api.get(`/agent-studio/configs/${configId}`);

export const createAgentStudioConfig = (payload) =>
  api.post("/agent-studio/configs", payload);

export const updateAgentStudioConfig = (configId, payload) =>
  api.put(`/agent-studio/configs/${configId}`, payload);

export const deleteAgentStudioConfig = (configId) =>
  api.delete(`/agent-studio/configs/${configId}`);

export const validateAgentStudioConfig = (configId) =>
  api.post(`/agent-studio/configs/${configId}/validate`);

export const getAgentStudioRuntimeGraph = (configId) =>
  api.get(`/agent-studio/configs/${configId}/runtime-graph`);

export const simulateAgentStudioConfig = (configId, payload) =>
  api.post(`/agent-studio/configs/${configId}/simulate`, payload);

export const setAgentStudioDefault = (configId) =>
  api.post(`/agent-studio/configs/${configId}/set-default`);

export const deployAgentStudioCanary = (configId, canaryPercent) =>
  api.post(`/agent-studio/configs/${configId}/deploy/canary`, null, {
    params: { canary_percent: canaryPercent },
  });

export const activateAgentStudio = (configId) =>
  api.post(`/agent-studio/configs/${configId}/deploy/activate`);

export const pauseAgentStudio = (configId) =>
  api.post(`/agent-studio/configs/${configId}/deploy/pause`);

export const rollbackAgentStudioRelease = (configId, releaseId) =>
  api.post(`/agent-studio/configs/${configId}/deploy/rollback/${releaseId}`);

