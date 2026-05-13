export const MOBILE_PATH_BY_MODE = {
  conversations: "/discussions",
  contacts: "/contacts",
  whatsapp: "/whatsapp-business",
  axelia: "/axelia",
  team: "/equipe",
  settings: "/parametres",
  connectedDevices: "/appareils-connectes",
};

const MOBILE_MODE_BY_PATH = Object.fromEntries(
  Object.entries(MOBILE_PATH_BY_MODE).map(([mode, path]) => [path, mode])
);

export function mobilePathToMode(pathname) {
  const p = pathname.replace(/\/+$/, "") || "/";
  return MOBILE_MODE_BY_PATH[p] ?? null;
}
