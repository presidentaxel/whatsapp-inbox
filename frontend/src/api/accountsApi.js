import { api } from "./axiosClient";

export const getAccounts = () => api.get("/accounts");
export const createAccount = (data) => api.post("/accounts", data);
export const deleteAccount = (id) => api.delete(`/accounts/${id}`);
export const updateAccountGoogleDrive = (accountId, data) =>
  api.patch(`/accounts/${accountId}/google-drive`, data);
export const initGoogleDriveAuth = (accountId) =>
  api.get("/auth/google-drive/init", { params: { account_id: accountId } });
export const disconnectGoogleDrive = (accountId) =>
  api.delete(`/accounts/${accountId}/google-drive/disconnect`);
export const listGoogleDriveFolders = (accountId, parentId = "root") =>
  api.get(`/accounts/${accountId}/google-drive/folders`, {
    params: { parent_id: parentId }
  });
export const backfillGoogleDrive = (accountId, limit = 100) =>
  api.post(`/accounts/${accountId}/google-drive/backfill?limit=${limit}`);

