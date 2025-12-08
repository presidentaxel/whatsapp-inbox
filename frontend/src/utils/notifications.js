/**
 * Utilitaires pour gérer les notifications dans l'application
 */

import { 
  requestNotificationPermission, 
  showNotification, 
  showMessageNotification 
} from '../registerSW';

/**
 * Demander la permission de notification à l'utilisateur
 * Avec un message personnalisé
 */
export async function askForNotificationPermission() {
  if (!('Notification' in window)) {
    console.warn('⚠️ Les notifications ne sont pas supportées par ce navigateur');
    return false;
  }

  // Si déjà accordé, pas besoin de redemander
  if (Notification.permission === 'granted') {
    return true;
  }

  // Si déjà refusé, ne pas redemander
  if (Notification.permission === 'denied') {
    console.log('⚠️ Les notifications ont été refusées par l\'utilisateur');
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

  await showNotification('Test de notification', {
    body: 'Les notifications fonctionnent correctement ! 🎉',
    tag: 'test-notification',
    requireInteraction: false
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
      console.warn('🔕 Notification skip: permission not granted');
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
    console.debug('🔕 Notification skip: app visible and conversation check active');
    return;
  }

  const contactName = conversation?.contacts?.display_name || 
                     conversation?.contacts?.whatsapp_number || 
                     conversation?.client_number || 
                     'Contact inconnu';

  // Aperçu du message
  let messagePreview = 'Nouveau message';
  const content = message.content_text || message.content || '';
  if (content) {
    messagePreview = content.substring(0, 120);
    if (content.length > 120) {
      messagePreview += '...';
    }
  } else if (message.media_url || message.media_id) {
    // Détecter le type de média
    const mediaType = message.media_type || 'media';
    const emojiMap = {
      'image': '🖼️ Image',
      'video': '🎥 Vidéo',
      'audio': '🎵 Audio',
      'document': '📄 Document',
      'sticker': '😊 Sticker',
      'voice': '🎤 Message vocal'
    };
    messagePreview = emojiMap[mediaType] || '📎 Média';
  } else if (message.type === 'location') {
    messagePreview = '📍 Localisation';
  } else if (message.type === 'contacts') {
    messagePreview = '👤 Contact';
  }

  console.log('🔔 About to show notification', {
    messageId: message.id,
    conversationId: conversation.id,
    contactName,
    preview: messagePreview
  });

  await showMessageNotification(contactName, messagePreview, conversation.id);
  console.log('✅ Notification shown', {
    messageId: message.id,
    conversationId: conversation.id,
    contactName,
    preview: messagePreview
  });
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
      if (event.data && event.data.type === 'OPEN_CONVERSATION') {
        // Émettre un événement personnalisé que l'app peut écouter
        window.dispatchEvent(new CustomEvent('openConversation', {
          detail: { conversationId: event.data.conversationId }
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

