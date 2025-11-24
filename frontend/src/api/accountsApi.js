import { api } from "./axiosClient";

export const getAccounts = () => api.get("/accounts");
export const createAccount = (data) => api.post("/accounts", data);
export const deleteAccount = (id) => api.delete(`/accounts/${id}`);

