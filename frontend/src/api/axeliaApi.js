import { api } from "./axiosClient";
import { supabaseClient } from "./supabaseClient";

/**
 * @param {{ limit?: number, offset?: number }} [params] Pagination optionnelle (sans params = liste complète côté API).
 */
export const getAxeliaConversations = (params) =>
  api.get("/axelia/conversations", { params: params || {} });

export const createAxeliaConversation = (payload) =>
  api.post("/axelia/conversations", payload);

export const patchAxeliaConversation = (conversationId, payload) =>
  api.patch(`/axelia/conversations/${conversationId}`, payload);

export const getAxeliaMessages = (conversationId) =>
  api.get(`/axelia/conversations/${conversationId}/messages`);

/**
 * Envoi d'un message Axelia.
 * @param {object} payload corps de la requête
 * @param {{ signal?: AbortSignal }} [options] Permet d'annuler via un AbortController côté UI.
 */
export const postAxeliaChat = (payload, options = {}) =>
  api.post("/axelia/chat", payload, options);

export const postAxeliaRegenerate = (conversationId) =>
  api.post(`/axelia/conversations/${conversationId}/regenerate`);

export const patchAxeliaMessageRating = (messageId, payload) =>
  api.patch(`/axelia/messages/${messageId}/rating`, payload);

/**
 * Lecture légère de la progression d'une requête `/axelia/chat` en cours.
 * Retourne `{}` quand la clé n'est plus connue (expirée / requête terminée).
 */
export const getAxeliaChatProgress = (progressKey, options = {}) =>
  api.get(`/axelia/chat/progress/${encodeURIComponent(progressKey)}`, options);

/**
 * Lecture du snapshot des métriques internes Axelia (debug / tableau de bord).
 */
export const getAxeliaMetrics = () => api.get("/axelia/metrics");

/**
 * Streaming SSE du chat Axelia.
 *
 * Pourquoi `fetch` plutôt qu'`axios` : le client axios navigateur n'expose pas
 * de `ReadableStream` (le `responseType: "stream"` est Node-only). On reprend
 * donc la base URL + le token d'auth via Supabase, puis on parse manuellement les
 * lignes au format SSE (`event: …` + `data: …`).
 *
 * Callbacks :
 *  - `onEvent(name, data)` : appelé pour chaque évènement SSE typé (`meta`, `progress`,
 *    `token`, `done`, `error`, `user-saved`, `persisted`).
 *  - `onError(err)` : erreur réseau / abort.
 *
 * Retourne une promesse résolue quand la connexion est terminée.
 */
export const streamAxeliaChat = async (payload, { signal, onEvent, onError } = {}) => {
  const baseURL = api.defaults.baseURL || "";
  const url = `${baseURL.replace(/\/$/, "")}/axelia/chat/stream`;

  let token = null;
  try {
    const { data } = await supabaseClient.auth.getSession();
    token = data?.session?.access_token || null;
  } catch (err) {
    onError && onError(err);
    return;
  }

  let resp;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
      signal,
      credentials: "include",
    });
  } catch (err) {
    onError && onError(err);
    return;
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    let detail = text;
    try {
      const j = JSON.parse(text);
      detail = j?.detail || text;
    } catch {
      /* ignore */
    }
    const err = new Error(`HTTP ${resp.status}: ${detail || "stream_failed"}`);
    err.status = resp.status;
    err.detail = detail;
    onError && onError(err);
    return;
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    onError && onError(new Error("ReadableStream non disponible (navigateur trop ancien)."));
    return;
  }
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  // Parse incrémental d'évènements SSE (séparés par "\n\n").
  const flushEvents = () => {
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!block.trim()) continue;
      let eventName = "message";
      const dataLines = [];
      for (const rawLine of block.split("\n")) {
        const line = rawLine.replace(/\r$/, "");
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).replace(/^\s/, ""));
        }
      }
      const dataStr = dataLines.join("\n");
      let parsed;
      try {
        parsed = dataStr ? JSON.parse(dataStr) : null;
      } catch {
        parsed = { _raw: dataStr };
      }
      try {
        onEvent && onEvent(eventName, parsed);
      } catch (err) {
        // Ne casse pas la boucle si le handler client jette
        // - l'utilisateur garde la main pour signaler l'incident.
        // eslint-disable-next-line no-console
        console.error("axelia stream onEvent threw:", err);
      }
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      flushEvents();
    }
    buffer += decoder.decode();
    flushEvents();
  } catch (err) {
    if (err?.name === "AbortError") {
      // Annulation côté client : on remonte un évènement « cancelled » pour
      // que l'UI puisse différencier d'une erreur réseau.
      onEvent && onEvent("cancelled", { reason: "aborted" });
    } else {
      onError && onError(err);
    }
  }
};
