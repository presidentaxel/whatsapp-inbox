import { api } from "./axiosClient";

export const getContacts = (params = {}) => {
  const queryParams = new URLSearchParams();
  if (params.limit) queryParams.append('limit', params.limit);
  if (params.offset) queryParams.append('offset', params.offset);
  const qs = queryParams.toString();
  return api.get(`/contacts${qs ? `?${qs}` : ''}`);
};

export const createContact = (data) => 
  api.post("/contacts", data);

export const updateContact = (contactId, data) => 
  api.put(`/contacts/${contactId}`, data);

export const deleteContact = (contactId) => 
  api.delete(`/contacts/${contactId}`);

export const getContactWhatsAppInfo = (contactId, accountId) =>
  api.get(`/contacts/${contactId}/whatsapp-info`, { params: { account_id: accountId } });
