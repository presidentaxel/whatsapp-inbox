/**
 * Utilitaires pour gérer les notifications dans l'application
 */

import { 
  requestNotificationPermission, 
  showNotification, 
  showMessageNotification 
} from '../registerSW';

/**
 * Clé de stockage pour les préférences de notifications
 */
const NOTIFICATION_PREFS_STORAGE_KEY = 'notif_prefs_v1';

/**
 * Charger les préférences de notifications depuis localStorage
 * @returns {Object} Préférences par compte: { [accountId]: { messages: boolean, previews: boolean, ... } }
 */
export function loadNotificationPrefs() {
  try {
    const raw = localStorage.getItem(NOTIFICATION_PREFS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/**
 * Vérifier si les notifications sont activées pour un compte spécifique
 * @param {string} accountId - ID du compte WhatsApp
 * @param {string} type - Type de notification ('messages', 'reactions', 'status')
 * @returns {boolean} true si activé, false sinon (par défaut: true si aucune préférence)
 */
export function isNotificationEnabledForAccount(accountId, type = 'messages') {
  if (!accountId) {
    // Si pas de compte, ne pas notifier par sécurité
    return false;
  }
  
  const prefs = loadNotificationPrefs();
  const accountPrefs = prefs[accountId];
  
  // Si aucune préférence pour ce compte, retourner true par défaut (comportement actuel)
  // Mais on pourrait aussi retourner false pour être plus strict
  if (!accountPrefs) {
    return true; // Par défaut activé si pas de préférence définie
  }
  
  // Retourner la préférence spécifique, ou true par défaut si non définie
  return accountPrefs[type] !== false; // true si activé ou non défini
}

/**
 * Demander la permission de notification à l'utilisateur
 * Avec un message personnalisé
 */
export async function askForNotificationPermission() {
  if (!('Notification' in window)) {
    return false;
  }

  // Si déjà accordé, pas besoin de redemander
  if (Notification.permission === 'granted') {
    return true;
  }

  // Si déjà refusé, ne pas redemander
  if (Notification.permission === 'denied') {
    return false;
  }

  // Demander la permission
  return await requestNotificationPermission();
}

/**
 * Vérifier si les notifications sont activées
 */
export function areNotificationsEnabled() {
  return 'Notification' in window && Notification.permission === 'granted';
}

/**
 * Afficher une notification de test
 */
export async function showTestNotification() {
  if (!areNotificationsEnabled()) {
    const granted = await askForNotificationPermission();
    if (!granted) return;
  }

  // Notification de test style WhatsApp
  await showNotification('Test WhatsApp', {
    body: 'Les notifications fonctionnent correctement !',
    tag: 'test-notification',
    requireInteraction: false,
    icon: '/192x192.svg',
    badge: '/192x192.svg',
    color: '#25d366'
  });
}

/**
 * Afficher une notification pour un nouveau message WhatsApp
 * @param {Object} message - Le message reçu
 * @param {Object} conversation - La conversation associée
 * @param {Object} options - Options supplémentaires
 */
export async function notifyNewMessage(message, conversation, options = {}) {
  // Ne pas notifier si les notifications ne sont pas activées
  if (!areNotificationsEnabled()) {
    const granted = await askForNotificationPermission();
    if (!granted) {
      return;
    }
  }

  // Options par défaut
  const {
    force = false, // Forcer la notification même si l'app est visible
    checkConversationOpen = true // Vérifier si la conversation est ouverte
  } = options;

  // Ne pas notifier si la fenêtre est active ET la conversation est ouverte (sauf si forcé)
  // Sur mobile, on peut vouloir notifier même si l'app est visible mais en arrière-plan
  if (!force && !document.hidden && checkConversationOpen) {
    // Vérifier si la conversation est actuellement ouverte
    // Cette vérification se fait maintenant dans le hook useGlobalNotifications
    return;
  }

  const contactName = conversation?.contacts?.display_name || 
                     conversation?.contacts?.whatsapp_number || 
                     conversation?.client_number || 
                     'Contact inconnu';

  // Aperçu du message - format exact WhatsApp
  let messagePreview = 'Nouveau message';
  const content = message.content_text || message.content || '';
  
  if (content && content.trim()) {
    // Limiter à 100 caractères comme WhatsApp
    const preview = content.trim().substring(0, 100);
    messagePreview = preview;
    if (content.length > 100) {
      messagePreview += '...';
    }
  } else if (message.media_url || message.media_id || message.media_type) {
    // Détecter le type de média - labels exacts WhatsApp
    const mediaType = (message.media_type || '').toLowerCase();
    const mediaMap = {
      'image': '📷 Photo',
      'video': '🎥 Vidéo',
      'audio': '🎵 Audio',
      'document': '📎 Document',
      'sticker': '😊 Autocollant',
      'voice': '🎤 Message vocal',
      'media': '📎 Média'
    };
    messagePreview = mediaMap[mediaType] || '📎 Média';
  } else if (message.type === 'location' || message.location) {
    messagePreview = '📍 Localisation';
  } else if (message.type === 'contacts' || message.contacts) {
    messagePreview = '👤 Contact';
  } else {
    messagePreview = 'Nouveau message';
  }

  // Récupérer l'image de profil du contact si disponible
  const contactImage = conversation?.contacts?.profile_picture_url || null;
  
  // Récupérer le nombre de messages non lus dans la conversation
  // Si non disponible, on assume qu'il y a au moins 1 message non lu (le message actuel)
  const unreadCount = conversation?.unread_count || 1;
  
  await showMessageNotification(contactName, messagePreview, conversation.id, contactImage, unreadCount);
}

/**
 * Afficher une notification générique
 * @param {string} title - Titre de la notification
 * @param {string} body - Corps de la notification
 * @param {Object} options - Options supplémentaires
 */
export async function notify(title, body, options = {}) {
  if (!areNotificationsEnabled()) {
    return;
  }

  await showNotification(title, {
    body,
    ...options
  });
}

/**
 * Initialiser les notifications au démarrage de l'app
 * (à appeler une fois au chargement)
 */
export async function initNotifications() {
  // Écouter les messages du service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (!event.data) return;
      
      if (event.data.type === 'OPEN_CONVERSATION') {
        // Émettre un événement personnalisé que l'app peut écouter
        window.dispatchEvent(new CustomEvent('openConversation', {
          detail: { conversationId: event.data.conversationId }
        }));
      } else if (event.data.type === 'MARK_AS_READ') {
        // Émettre un événement pour marquer une conversation comme lue
        window.dispatchEvent(new CustomEvent('markConversationRead', {
          detail: { conversationId: event.data.conversationId }
        }));
      } else if (event.data.type === 'MARK_ALL_AS_READ') {
        // Émettre un événement pour marquer toutes les conversations comme lues
        window.dispatchEvent(new CustomEvent('markAllConversationsRead', {
          detail: { conversationIds: event.data.conversationIds || [] }
        }));
      }
    });
  }

  // Demander la permission après un court délai (meilleure UX)
  // Seulement si pas encore demandé
  if (Notification.permission === 'default') {
    setTimeout(() => {
      askForNotificationPermission();
    }, 3000); // Attendre 3 secondes après le chargement
  }
}

