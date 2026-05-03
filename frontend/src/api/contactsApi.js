import { api } from "./axiosClient";

export const getContacts = (params = {}) => {
  const queryParams = new URLSearchParams();
  if (params.limit) queryParams.append("limit", params.limit);
  if (params.offset) queryParams.append("offset", params.offset);
  if (params.q && String(params.q).trim()) queryParams.append("q", String(params.q).trim());
  const qs = queryParams.toString();
  return api.get(`/contacts${qs ? `?${qs}` : ""}`);
};

export const createContact = (data) => 
  api.post("/contacts", data);

export const updateContact = (contactId, data) => 
  api.put(`/contacts/${contactId}`, data);

export const deleteContact = (contactId) => 
  api.delete(`/contacts/${contactId}`);

export const getContactWhatsAppInfo = (contactId, accountId) =>
  api.get(`/contacts/${contactId}/whatsapp-info`, { params: { account_id: accountId } });

/** Liste des WA bloqués par compte dans l’app uniquement ; GET/POST/DELETE /contacts/.../meta-* */
export const getMetaBlockedWaIds = (accountId) =>
  api.get("/contacts/meta-blocked", { params: { account_id: accountId } });

/** Tous les comptes autorisés en un POST (remplace N× GET meta-blocked). */
export const getMetaBlockedWaIdsBatch = (accountIds) =>
  api.post("/contacts/meta-blocked/batch", { account_ids: accountIds });

export const metaBlockContact = (contactId, accountId) =>
  api.post(`/contacts/${contactId}/meta-block`, {}, { params: { account_id: accountId } });

export const metaUnblockContact = (contactId, accountId) =>
  api.delete(`/contacts/${contactId}/meta-block`, { params: { account_id: accountId } });
