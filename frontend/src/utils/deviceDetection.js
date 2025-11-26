/**
 * Utilitaires de détection de device
 */

export function isMobileDevice() {
  // Vérifier plusieurs critères pour détecter un mobile
  const userAgent = navigator.userAgent || navigator.vendor || window.opera;
  
  // 1. User agent
  const mobileRegex = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i;
  const isMobileUA = mobileRegex.test(userAgent.toLowerCase());
  
  // 2. Touch screen
  const hasTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  
  // 3. Taille d'écran
  const isSmallScreen = window.innerWidth <= 768;
  
  // 4. Mode standalone (PWA installée)
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                       window.navigator.standalone === true;
  
  return isMobileUA || (hasTouch && isSmallScreen) || isStandalone;
}

export function isTablet() {
  const userAgent = navigator.userAgent.toLowerCase();
  return (userAgent.includes('ipad') || 
          (userAgent.includes('android') && !userAgent.includes('mobile'))) &&
         window.innerWidth >= 768 && window.innerWidth <= 1024;
}

export function isPWA() {
  return window.matchMedia('(display-mode: standalone)').matches ||
         window.navigator.standalone === true ||
         document.referrer.includes('android-app://');
}

export function getDeviceType() {
  if (isMobileDevice()) return 'mobile';
  if (isTablet()) return 'tablet';
  return 'desktop';
}

