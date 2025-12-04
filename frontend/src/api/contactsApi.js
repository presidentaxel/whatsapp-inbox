import { api } from "./axiosClient";

export const getContacts = () => api.get("/contacts");

export const createContact = (data) => 
  api.post("/contacts", data);

export const updateContact = (contactId, data) => 
  api.put(`/contacts/${contactId}`, data);

export const deleteContact = (contactId) => 
  api.delete(`/contacts/${contactId}`);

export const getContactWhatsAppInfo = (contactId, accountId) =>
  api.get(`/contacts/${contactId}/whatsapp-info`, { params: { account_id: accountId } });

