import axios from "axios";
import { supabaseClient } from "./supabaseClient";

const prefersDevProxy =
  import.meta.env.DEV && import.meta.env.VITE_DEV_PROXY !== "false";

const normalizeUrl = (url) => (url?.endsWith("/") ? url.slice(0, -1) : url);

const resolveBaseURL = () => {
  if (prefersDevProxy) {
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

// In-memory token cache to avoid calling getSession() on every request
let _cachedToken = null;
let _tokenExpiresAt = 0;

// Keep token in sync with auth state changes
supabaseClient.auth.onAuthStateChange((_event, session) => {
  if (session?.access_token) {
    _cachedToken = session.access_token;
    _tokenExpiresAt = (session.expires_at || 0) * 1000;
  } else {
    _cachedToken = null;
    _tokenExpiresAt = 0;
  }
});

// Warm the cache on module load
supabaseClient.auth.getSession().then(({ data }) => {
  if (data?.session?.access_token) {
    _cachedToken = data.session.access_token;
    _tokenExpiresAt = (data.session.expires_at || 0) * 1000;
  }
});

api.interceptors.request.use(
  async (config) => {
    try {
      let token = _cachedToken;

      // Refresh only if expired or missing
      if (!token || Date.now() > _tokenExpiresAt - 30000) {
        const { data: { session }, error } = await supabaseClient.auth.getSession();
        if (error || !session?.access_token) {
          return config;
        }
        token = session.access_token;
        _cachedToken = token;
        _tokenExpiresAt = (session.expires_at || 0) * 1000;
      }

      config.headers.Authorization = `Bearer ${token}`;
    } catch {
      // Don't block the request on auth errors
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Évite les re-déclenchements en rafale quand plusieurs requêtes échouent en
// 401 simultanément (ex: au reload). On notifie l'app via un évènement global
// que `AuthContext` écoute pour forcer la déconnexion / redirect login.
let _signalingUnauthorized = false;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status;

    if (status === 401) {
      _cachedToken = null;
      _tokenExpiresAt = 0;

      if (typeof window !== "undefined" && !_signalingUnauthorized) {
        _signalingUnauthorized = true;
        try {
          window.dispatchEvent(
            new CustomEvent("auth:unauthorized", {
              detail: { url: error.config?.url },
            })
          );
        } finally {
          // Reset après un court délai pour autoriser une future notification
          setTimeout(() => {
            _signalingUnauthorized = false;
          }, 1000);
        }
      }
    }

    return Promise.reject(error);
  }
);
