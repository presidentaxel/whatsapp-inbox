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

api.interceptors.request.use(
  async (config) => {
    // Log pour les requêtes de template
    if (config.url?.includes("send-template")) {
      console.log("🌐 [AXIOS] Requête send-template interceptée:", {
        url: config.url,
        method: config.method,
        baseURL: config.baseURL,
        data: config.data
      });
    }
    
    try {
      const {
        data: { session },
        error,
      } = await supabaseClient.auth.getSession();
      
      if (error) {
        console.warn("⚠️ Error getting session in axios interceptor:", error);
        console.warn("   Request URL:", config.url);
        return config; // Continuer sans token
      }
      
      if (!session) {
        console.warn("⚠️ No session found in axios interceptor for request:", config.url);
        return config; // Continuer sans token
      }
      
      if (!session.access_token) {
        console.warn("⚠️ Session exists but no access_token for request:", config.url);
        console.warn("   Session data:", { 
          user: session.user?.id, 
          expires_at: session.expires_at,
          expires_in: session.expires_in 
        });
        return config; // Continuer sans token
      }
      
      // Token trouvé, l'ajouter
      config.headers.Authorization = `Bearer ${session.access_token}`;
      if (config.url?.includes("send-template")) {
        console.log("✅ [AXIOS] Token ajouté à la requête send-template");
      }
      
    } catch (err) {
      console.error("❌ Error in axios request interceptor:", err);
      // Ne pas bloquer la requête même en cas d'erreur
    }
    return config;
  },
  (error) => {
    console.error("❌ [AXIOS] Erreur dans l'intercepteur de requête:", error);
    return Promise.reject(error);
  }
);

// Intercepteur de réponse pour gérer les erreurs 401
api.interceptors.response.use(
  (response) => {
    // Log pour les réponses de template
    if (response.config?.url?.includes("send-template")) {
      console.log("✅ [AXIOS] Réponse reçue pour send-template:", {
        status: response.status,
        data: response.data
      });
    }
    return response;
  },
  async (error) => {
    // Log pour les erreurs de template
    if (error.config?.url?.includes("send-template")) {
      console.error("❌ [AXIOS] Erreur pour send-template:", {
        status: error.response?.status,
        statusText: error.response?.statusText,
        data: error.response?.data,
        message: error.message,
        url: error.config?.url,
        baseURL: error.config?.baseURL
      });
    }
    
    if (error.response?.status === 401) {
      console.warn("⚠️ 401 Unauthorized - Session may have expired");
      // Optionnel : rediriger vers la page de login
      // window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);