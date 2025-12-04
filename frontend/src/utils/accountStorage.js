/**
 * Utilitaires pour la persistance du compte actif dans le localStorage
 */

const STORAGE_KEY = 'whatsapp_inbox_active_account';

/**
 * Sauvegarde le compte actif dans le localStorage
 * @param {string} accountId - ID du compte à sauvegarder
 */
export function saveActiveAccount(accountId) {
  try {
    if (accountId) {
      localStorage.setItem(STORAGE_KEY, accountId);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch (error) {
    console.error('Erreur lors de la sauvegarde du compte actif:', error);
  }
}

/**
 * Récupère le compte actif depuis le localStorage
 * @returns {string|null} - ID du compte sauvegardé ou null
 */
export function getActiveAccount() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    console.error('Erreur lors de la récupération du compte actif:', error);
    return null;
  }
}

/**
 * Supprime le compte actif du localStorage
 */
export function clearActiveAccount() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.error('Erreur lors de la suppression du compte actif:', error);
  }
}

