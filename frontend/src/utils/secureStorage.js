/**
 * Stockage sécurisé pour l'authentification persistante sur mobile
 */

const STORAGE_PREFIX = 'lmdcvtc_';
const AUTH_KEY = `${STORAGE_PREFIX}auth`;
const SESSION_KEY = `${STORAGE_PREFIX}session`;

/**
 * Encode les données pour plus de sécurité (basique)
 */
function encode(data) {
  try {
    return btoa(JSON.stringify(data));
  } catch (e) {
    console.error('Erreur d\'encodage:', e);
    return null;
  }
}

/**
 * Décode les données
 */
function decode(data) {
  try {
    return JSON.parse(atob(data));
  } catch (e) {
    console.error('Erreur de décodage:', e);
    return null;
  }
}

/**
 * Sauvegarde la session d'authentification
 */
export function saveAuthSession(session, rememberMe = true) {
  if (!session) return false;
  
  const authData = {
    session,
    timestamp: Date.now(),
    rememberMe
  };
  
  try {
    const encoded = encode(authData);
    if (rememberMe) {
      localStorage.setItem(AUTH_KEY, encoded);
    } else {
      sessionStorage.setItem(SESSION_KEY, encoded);
    }
    return true;
  } catch (e) {
    console.error('Erreur de sauvegarde:', e);
    return false;
  }
}

/**
 * Récupère la session d'authentification
 */
export function getAuthSession() {
  try {
    // Vérifier localStorage d'abord (remember me)
    const stored = localStorage.getItem(AUTH_KEY);
    if (stored) {
      const decoded = decode(stored);
      if (decoded && decoded.session) {
        // Vérifier l'expiration (30 jours max)
        const thirtyDays = 30 * 24 * 60 * 60 * 1000;
        if (Date.now() - decoded.timestamp < thirtyDays) {
          return decoded.session;
        } else {
          // Session expirée
          clearAuthSession();
        }
      }
    }
    
    // Sinon vérifier sessionStorage
    const sessionStored = sessionStorage.getItem(SESSION_KEY);
    if (sessionStored) {
      const decoded = decode(sessionStored);
      return decoded?.session || null;
    }
    
    return null;
  } catch (e) {
    console.error('Erreur de récupération:', e);
    return null;
  }
}

/**
 * Supprime la session d'authentification
 */
export function clearAuthSession() {
  try {
    localStorage.removeItem(AUTH_KEY);
    sessionStorage.removeItem(SESSION_KEY);
    return true;
  } catch (e) {
    console.error('Erreur de suppression:', e);
    return false;
  }
}

/**
 * Vérifie si une session existe
 */
export function hasAuthSession() {
  return getAuthSession() !== null;
}

/**
 * Met à jour le timestamp de la session (pour keep-alive)
 */
export function refreshAuthSession() {
  const session = getAuthSession();
  if (session) {
    const stored = localStorage.getItem(AUTH_KEY);
    if (stored) {
      const decoded = decode(stored);
      if (decoded) {
        saveAuthSession(session, decoded.rememberMe);
        return true;
      }
    }
  }
  return false;
}

