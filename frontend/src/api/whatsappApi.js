import { api } from "./axiosClient";

// ============================================================================
// MESSAGES
// ============================================================================

export async function sendTextMessage(accountId, data) {
  const res = await api.post(`/api/whatsapp/messages/text/${accountId}`, data);
  return res.data;
}

export async function sendMediaMessage(accountId, data) {
  const res = await api.post(`/api/whatsapp/messages/media/${accountId}`, data);
  return res.data;
}

export async function sendTemplateMessage(accountId, data) {
  const res = await api.post(`/api/whatsapp/messages/template/${accountId}`, data);
  return res.data;
}

export async function sendInteractiveButtons(accountId, data) {
  const res = await api.post(`/api/whatsapp/messages/interactive/buttons/${accountId}`, data);
  return res.data;
}

export async function sendInteractiveList(accountId, data) {
  const res = await api.post(`/api/whatsapp/messages/interactive/list/${accountId}`, data);
  return res.data;
}

// ============================================================================
// MÉDIAS
// ============================================================================

export async function uploadMedia(accountId, file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post(`/api/whatsapp/media/upload/${accountId}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return res.data;
}

export async function getMediaInfo(accountId, mediaId) {
  const res = await api.get(`/api/whatsapp/media/info/${accountId}/${mediaId}`);
  return res.data;
}

export async function downloadMedia(accountId, mediaId) {
  const res = await api.get(`/api/whatsapp/media/download/${accountId}/${mediaId}`, {
    responseType: 'blob'
  });
  return res;
}

export async function deleteMedia(accountId, mediaId) {
  const res = await api.delete(`/api/whatsapp/media/${accountId}/${mediaId}`);
  return res.data;
}

// ============================================================================
// TEMPLATES
// ============================================================================

export async function listTemplates(accountId, params = {}) {
  const res = await api.get(`/api/whatsapp/templates/list/${accountId}`, { params });
  return res.data;
}

export async function createTemplate(accountId, data) {
  const res = await api.post(`/api/whatsapp/templates/create/${accountId}`, data);
  return res.data;
}

export async function deleteTemplate(accountId, data) {
  const res = await api.delete(`/api/whatsapp/templates/delete/${accountId}`, { data });
  return res.data;
}

// ============================================================================
// PROFIL BUSINESS
// ============================================================================

export async function getBusinessProfile(accountId) {
  const res = await api.get(`/api/whatsapp/profile/${accountId}`);
  return res.data;
}

export async function updateBusinessProfile(accountId, data) {
  const res = await api.post(`/api/whatsapp/profile/${accountId}`, data);
  return res.data;
}

// ============================================================================
// NUMÉROS DE TÉLÉPHONE
// ============================================================================

export async function getPhoneDetails(accountId) {
  const res = await api.get(`/api/whatsapp/phone/details/${accountId}`);
  return res.data;
}

export async function listPhoneNumbers(accountId) {
  const res = await api.get(`/api/whatsapp/phone/list/${accountId}`);
  return res.data;
}

// ============================================================================
// WABA MANAGEMENT
// ============================================================================

export async function getWabaDetails(accountId) {
  const res = await api.get(`/api/whatsapp/waba/details/${accountId}`);
  return res.data;
}

export async function getWebhookSubscriptions(accountId) {
  const res = await api.get(`/api/whatsapp/waba/webhooks/subscriptions/${accountId}`);
  return res.data;
}

// ============================================================================
// UTILITAIRES
// ============================================================================

export async function validatePhoneNumber(phone) {
  const res = await api.post(`/api/whatsapp/utils/validate-phone?phone=${encodeURIComponent(phone)}`);
  return res.data;
}

