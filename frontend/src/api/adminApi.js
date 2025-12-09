import { api } from "./axiosClient";

export const getCurrentUserProfile = () => api.get("/auth/me");
export const getPermissions = () => api.get("/admin/permissions");
export const getRoles = () => api.get("/admin/roles");
export const createRole = (data) => api.post("/admin/roles", data);
export const updateRole = (roleId, data) => api.put(`/admin/roles/${roleId}`, data);
export const deleteRole = (roleId) => api.delete(`/admin/roles/${roleId}`);

export const getAdminUsers = () => api.get("/admin/users");
export const updateUserStatus = (userId, data) =>
  api.post(`/admin/users/${userId}/status`, data);
export const setUserRoles = (userId, assignments) =>
  api.put(`/admin/users/${userId}/roles`, { assignments });
export const setUserOverrides = (userId, overrides) =>
  api.put(`/admin/users/${userId}/overrides`, { overrides });
export const deleteUser = (userId) => api.delete(`/admin/users/${userId}`);

// Nouveau système de permissions par compte
export const getUsersWithAccess = () => api.get("/admin/users/with-access");
export const getAllAccountsForPermissions = () => api.get("/admin/accounts/all");
export const updateUserAccountAccess = (userId, accountId, accessLevel) =>
  api.put(`/admin/users/${userId}/accounts/${accountId}/access`, { access_level: accessLevel });

