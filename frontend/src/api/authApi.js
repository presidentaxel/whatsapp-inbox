import { api } from "./axiosClient";

export const getProfile = () => api.get("/auth/me");

export const updateProfile = (data) => api.put("/auth/me", data);

export const uploadProfilePicture = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post("/auth/me/profile-picture", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
};

