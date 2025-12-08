/**
 * Utilitaires de détection de device
 */

// Détecter un device mobile sans forcer les PWA desktop à passer en mode mobile
export function isMobileDevice() {
  const userAgent = (navigator.userAgent || navigator.vendor || window.opera || "").toLowerCase();
  const mobileRegex = /android|webos|iphone|ipod|blackberry|iemobile|opera mini/;
  const isMobileUA = mobileRegex.test(userAgent);

  // UA moderne (Chrome/Edge/Opera) expose cette info
  const isMobileUAData = navigator.userAgentData?.mobile === true;

  const hasTouch = "ontouchstart" in window || navigator.maxTouchPoints > 0;
  const minViewport = Math.min(window.innerWidth, window.innerHeight);
  const isSmallScreen = minViewport <= 820; // inclus phablets

  return isMobileUA || isMobileUAData || (hasTouch && isSmallScreen);
}

export function isTablet() {
  const userAgent = navigator.userAgent.toLowerCase();
  return (
    (userAgent.includes("ipad") ||
      (userAgent.includes("android") && !userAgent.includes("mobile"))) &&
    window.innerWidth >= 768 &&
    window.innerWidth <= 1224
  );
}

export function isPWA() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true ||
    document.referrer.includes("android-app://")
  );
}

export function getDeviceType() {
  if (isMobileDevice()) return "mobile";
  if (isTablet()) return "tablet";
  return "desktop";
}

