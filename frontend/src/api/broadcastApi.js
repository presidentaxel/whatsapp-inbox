import { api } from "./axiosClient";

// ==================== GROUPES ====================

export const getBroadcastGroups = (accountId) =>
  api.get(`/broadcast/groups?account_id=${accountId}`);

export const getBroadcastGroup = (groupId) =>
  api.get(`/broadcast/groups/${groupId}`);

export const createBroadcastGroup = (data) =>
  api.post("/broadcast/groups", data);

export const updateBroadcastGroup = (groupId, data) =>
  api.patch(`/broadcast/groups/${groupId}`, data);

export const deleteBroadcastGroup = (groupId) =>
  api.delete(`/broadcast/groups/${groupId}`);

// ==================== DESTINATAIRES ====================

export const getGroupRecipients = (groupId) =>
  api.get(`/broadcast/groups/${groupId}/recipients`);

export const addRecipientToGroup = (groupId, data) =>
  api.post(`/broadcast/groups/${groupId}/recipients`, data);

export const removeRecipientFromGroup = (groupId, recipientId) =>
  api.delete(`/broadcast/groups/${groupId}/recipients/${recipientId}`);

// ==================== CAMPAGNES ====================

export const sendBroadcastCampaign = (groupId, data) =>
  api.post(`/broadcast/groups/${groupId}/send`, data);

export const getBroadcastCampaigns = (params = {}) => {
  const queryParams = new URLSearchParams();
  if (params.groupId) queryParams.append('group_id', params.groupId);
  if (params.accountId) queryParams.append('account_id', params.accountId);
  return api.get(`/broadcast/campaigns?${queryParams.toString()}`);
};

export const getBroadcastCampaign = (campaignId) =>
  api.get(`/broadcast/campaigns/${campaignId}`);

export const getCampaignStats = (campaignId) =>
  api.get(`/broadcast/campaigns/${campaignId}/stats`);

export const getCampaignHeatmap = (campaignId) =>
  api.get(`/broadcast/campaigns/${campaignId}/heatmap`);

export const getCampaignTimeline = (campaignId) =>
  api.get(`/broadcast/campaigns/${campaignId}/timeline`);

