/** Desktop inbox URLs ↔ sidebar nav ids (internal state). */

export const INBOX_PATH_BY_MODE = {
  chat: "/discussions",
  contacts: "/contacts",
  axelia: "/axelia",
  whatsapp: "/whatsapp-business",
  assistant: "/playground",
  settings: "/parametres",
};

const MODE_BY_PATH = Object.fromEntries(
  Object.entries(INBOX_PATH_BY_MODE).map(([mode, path]) => [path, mode])
);

/**
 * @param {string} pathname
 * @returns {string | null} nav mode id or null if unknown
 */
export function inboxPathToMode(pathname) {
  const p = pathname.replace(/\/+$/, "") || "/";
  return MODE_BY_PATH[p] ?? null;
}
