import axios from "axios";
import { supabaseClient } from "./supabaseClient";

const prefersDevProxy =
  import.meta.env.DEV && import.meta.env.VITE_DEV_PROXY !== "false";

const normalizeUrl = (url) => (url?.endsWith("/") ? url.slice(0, -1) : url);

const resolveBaseURL = () => {
  if (prefersDevProxy) {
    // Vite proxies /api → local backend so remote devices can reach it.
    return "/api";
  }

  const envUrl = normalizeUrl(import.meta.env.VITE_BACKEND_URL);
  if (envUrl) {
    return envUrl;
  }

  if (typeof window !== "undefined" && window.location?.origin) {
    return `${normalizeUrl(window.location.origin)}/api`;
  }

  return "";
};

export const api = axios.create({
  baseURL: resolveBaseURL(),
});

api.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabaseClient.auth.getSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});