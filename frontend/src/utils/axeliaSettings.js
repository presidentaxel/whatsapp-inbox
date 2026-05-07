const AXELIA_RESPONSE_DEPTH_KEY = "axelia.responseDepth";
const AXELIA_RESPONSE_DEPTH_VALUES = new Set(["brief", "standard", "expert"]);

export function loadAxeliaResponseDepth() {
  if (typeof window === "undefined" || !window.localStorage) {
    return "standard";
  }
  const raw = window.localStorage.getItem(AXELIA_RESPONSE_DEPTH_KEY) || "";
  return AXELIA_RESPONSE_DEPTH_VALUES.has(raw) ? raw : "standard";
}

export function saveAxeliaResponseDepth(value) {
  const next = AXELIA_RESPONSE_DEPTH_VALUES.has(value) ? value : "standard";
  if (typeof window === "undefined" || !window.localStorage) {
    return next;
  }
  window.localStorage.setItem(AXELIA_RESPONSE_DEPTH_KEY, next);
  return next;
}

