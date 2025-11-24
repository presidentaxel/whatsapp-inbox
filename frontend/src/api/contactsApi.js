import { api } from "./axiosClient";

export const getContacts = () => api.get("/contacts");

