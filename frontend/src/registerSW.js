/**
 * Enregistrement du Service Worker pour la PWA
 */

export function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          console.log('✅ Service Worker enregistré:', registration.scope);
          
          // Activer le Background Sync pour recevoir des notifications même quand l'app est fermée
          if ('sync' in registration) {
            // Enregistrer un sync périodique (si supporté par le navigateur)
            setInterval(() => {
              registration.sync?.register('background-sync-messages').catch(() => {
                // Background Sync peut ne pas être supporté, c'est OK
              });
            }, 30000); // Toutes les 30 secondes
          }
          
          // Vérifier les mises à jour toutes les heures
          setInterval(() => {
            registration.update();
          }, 60 * 60 * 1000);
        })
        .catch((error) => {
          console.error('❌ Erreur lors de l\'enregistrement du Service Worker:', error);
        });
    });

    // Écouter les mises à jour du SW
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      console.log('🔄 Service Worker mis à jour');
      // Optionnel : afficher une notification à l'utilisateur
      if (confirm('Une nouvelle version est disponible. Recharger ?')) {
        window.location.reload();
      }
    });
  }
}

/**
 * Demander la permission pour les notifications (optionnel)
 */
export async function requestNotificationPermission() {
  if ('Notification' in window && 'serviceWorker' in navigator) {
    const permission = await Notification.requestPermission();
    
    if (permission === 'granted') {
      console.log('✅ Notifications autorisées');
      return true;
    } else {
      console.log('❌ Notifications refusées');
      return false;
    }
  }
  return false;
}

/**
 * Vérifier si l'app est installée (PWA)
 */
export function isAppInstalled() {
  // Détection PWA standalone mode
  return window.matchMedia('(display-mode: standalone)').matches ||
         window.navigator.standalone === true ||
         document.referrer.includes('android-app://');
}

/**
 * Gérer l'installation de la PWA
 */
let deferredPrompt = null;

export function setupInstallPrompt() {
  window.addEventListener('beforeinstallprompt', (e) => {
    // Empêcher le prompt automatique
    e.preventDefault();
    deferredPrompt = e;
    
    console.log('💾 PWA peut être installée');
    
    // Vous pouvez maintenant afficher votre propre bouton d'installation
    // et appeler showInstallPrompt() quand l'utilisateur clique dessus
  });

  // Détecter quand l'app est installée
  window.addEventListener('appinstalled', () => {
    console.log('✅ PWA installée avec succès');
    deferredPrompt = null;
  });
}

export async function showInstallPrompt() {
  if (!deferredPrompt) {
    console.log('❌ Prompt d\'installation non disponible');
    return false;
  }

  // Afficher le prompt
  deferredPrompt.prompt();
  
  // Attendre le choix de l'utilisateur
  const { outcome } = await deferredPrompt.userChoice;
  
  console.log(`Installation: ${outcome}`);
  deferredPrompt = null;
  
  return outcome === 'accepted';
}

/**
 * Afficher une notification locale (style WhatsApp)
 * @param {string} title - Titre de la notification
 * @param {object} options - Options de la notification
 * @returns {Promise<void>}
 */
export async function showNotification(title, options = {}) {
  // Demander la permission si nécessaire
  if (Notification.permission === 'default') {
    const granted = await requestNotificationPermission();
    if (!granted) {
      console.log('❌ Permission de notification refusée');
      return;
    }
  }
  
  if (Notification.permission !== 'granted') {
    console.log('❌ Permission de notification non accordée');
    return;
  }

  // Options par défaut style WhatsApp
  const defaultOptions = {
    icon: '/192x192.svg',
    badge: '/192x192.svg',
    vibrate: [200, 100, 200], // Vibration WhatsApp
    tag: 'whatsapp-notification',
    requireInteraction: false,
    silent: false,
    color: '#25d366', // Vert WhatsApp
    ...options
  };

  // Vérifier si le service worker est disponible
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    const registration = await navigator.serviceWorker.ready;
    
    // Afficher la notification via le service worker
    await registration.showNotification(title, defaultOptions);
  } else {
    // Fallback : notification simple sans service worker
    new Notification(title, defaultOptions);
  }
}

/**
 * Génère une URL d'avatar avec initiales (fallback si pas d'image)
 * @param {string} name - Nom du contact
 * @returns {string} URL de données pour l'avatar
 */
function generateAvatarFallback(name) {
  // Utiliser l'icône par défaut plutôt que de générer un avatar SVG
  // L'icône sera toujours disponible même sans image de profil
  return '/192x192.svg';
}

/**
 * Stockage des conversations non lues pour la notification globale
 * Utilise localStorage pour persister entre les rechargements de page
 */
const NOTIFICATION_STORAGE_KEY = 'whatsapp_notifications_conversations';

function getStoredConversations() {
  try {
    const stored = localStorage.getItem(NOTIFICATION_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
  } catch (error) {
    console.warn('⚠️ Erreur lecture notifications:', error);
    return {};
  }
}

function storeConversations(conversations) {
  try {
    localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(conversations));
  } catch (error) {
    console.warn('⚠️ Erreur écriture notifications:', error);
  }
}

function updateConversationInStore(conversationId, contactName, messagePreview, contactImage, unreadCount) {
  const conversations = getStoredConversations();
  conversations[conversationId] = {
    conversationId,
    contactName,
    lastMessagePreview: messagePreview,
    contactImage: contactImage || null,
    unreadCount: Math.max(unreadCount, (conversations[conversationId]?.unreadCount || 0) + 1),
    lastUpdate: Date.now()
  };
  storeConversations(conversations);
  return conversations;
}

function removeConversationFromStore(conversationId) {
  const conversations = getStoredConversations();
  delete conversations[conversationId];
  storeConversations(conversations);
  return conversations;
}

function buildNotificationBody(conversations) {
  const convs = Object.values(conversations);
  if (convs.length === 0) return 'Aucun nouveau message';
  
  // Trier par dernière mise à jour (plus récent en premier)
  convs.sort((a, b) => b.lastUpdate - a.lastUpdate);
  
  const totalMessages = convs.reduce((sum, c) => sum + c.unreadCount, 0);
  
  if (convs.length === 1) {
    // Une seule conversation : afficher le message directement
    const conv = convs[0];
    if (conv.unreadCount === 1) {
      return conv.lastMessagePreview;
    } else {
      return `${conv.lastMessagePreview}\n(${conv.unreadCount} messages)`;
    }
  } else {
    // Plusieurs conversations : afficher un résumé
    // Format: "Jean Dupont: Message...\nMarie Martin: Message...\n(5 messages au total)"
    let body = '';
    // Prendre les 3 premières conversations
    const topConvs = convs.slice(0, 3);
    body = topConvs.map(conv => {
      const preview = conv.lastMessagePreview.length > 40 
        ? conv.lastMessagePreview.substring(0, 40) + '...'
        : conv.lastMessagePreview;
      return `${conv.contactName}: ${preview}`;
    }).join('\n');
    
    if (convs.length > 3) {
      body += `\n+${convs.length - 3} autre${convs.length - 3 > 1 ? 's' : ''} conversation${convs.length - 3 > 1 ? 's' : ''}`;
    }
    
    body += `\n(${totalMessages} message${totalMessages > 1 ? 's' : ''} au total)`;
    return body;
  }
}

/**
 * Afficher une notification globale pour tous les messages non lus
 * Met à jour une seule notification qui regroupe toutes les conversations
 * @param {string} contactName - Nom du contact
 * @param {string} messagePreview - Aperçu du message
 * @param {string} conversationId - ID de la conversation
 * @param {string} contactImage - URL de l'image de profil (optionnel)
 * @param {number} unreadCount - Nombre de messages non lus dans cette conversation (optionnel)
 */
export async function showMessageNotification(contactName, messagePreview, conversationId, contactImage = null, unreadCount = 1) {
  // Tag unique global pour toutes les notifications
  const globalTag = 'whatsapp-all-messages';
  
  // Mettre à jour le stockage avec cette conversation
  const allConversations = updateConversationInStore(
    conversationId,
    contactName,
    messagePreview,
    contactImage,
    unreadCount
  );
  
  // Vérifier s'il y a déjà une notification globale
  let existingNotification = null;
  if ('serviceWorker' in navigator) {
    try {
      const registration = await navigator.serviceWorker.ready;
      const notifications = await registration.getNotifications({ tag: globalTag });
      if (notifications.length > 0) {
        existingNotification = notifications[0];
      }
    } catch (error) {
      console.warn('⚠️ Impossible de récupérer les notifications existantes:', error);
    }
  }
  
  // Construire le titre et le body de la notification globale
  const convCount = Object.keys(allConversations).length;
  const totalMessages = Object.values(allConversations).reduce((sum, c) => sum + c.unreadCount, 0);
  
  let title;
  if (convCount === 1) {
    // Une seule conversation : titre = nom du contact
    title = contactName;
  } else {
    // Plusieurs conversations : titre avec compteur
    title = `${convCount} conversations • ${totalMessages} message${totalMessages > 1 ? 's' : ''}`;
  }
  
  const body = buildNotificationBody(allConversations);
  
  // Pour l'icône, utiliser la première conversation (la plus récente)
  const sortedConvs = Object.values(allConversations).sort((a, b) => b.lastUpdate - a.lastUpdate);
  const primaryConversation = sortedConvs[0];
  const notificationIcon = primaryConversation?.contactImage || '/192x192.svg';
  
  // Options de notification style WhatsApp Desktop/Mobile
  const options = {
    body: body,
    tag: globalTag, // Tag global unique pour regrouper toutes les notifications
    data: { 
      conversations: allConversations,
      conversationId: conversationId, // Conversation la plus récente
      timestamp: Date.now(),
      totalMessages: totalMessages,
      conversationCount: convCount
    },
    // Icon = image de profil de la conversation la plus récente
    icon: notificationIcon,
    // Badge = icône WhatsApp pour identifier l'app
    badge: '/192x192.svg',
    // Image = image de profil large (notifications riches - si supporté)
    image: primaryConversation?.contactImage || null,
    // Vibration style WhatsApp (court, double) - seulement si nouvelle notification
    vibrate: existingNotification ? [] : [200, 100, 200],
    requireInteraction: false, // Disparaît automatiquement
    silent: existingNotification, // Son seulement pour nouveau message, pas pour mise à jour
    timestamp: Date.now(),
    dir: 'ltr',
    lang: 'fr',
    // Renotifier si plusieurs messages
    renotify: true,
    sticky: false,
    // Couleur de thème WhatsApp (vert)
    color: '#25d366',
    // Actions interactives (si supporté par le navigateur)
    actions: [
      {
        action: 'open',
        title: 'Ouvrir'
      },
      {
        action: 'mark-all-read',
        title: 'Tout marquer comme lu'
      }
    ]
  };

  await showNotification(title, options);
}

/**
 * Nettoyer une conversation du stockage quand elle est marquée comme lue
 */
export function clearConversationNotification(conversationId) {
  const conversations = removeConversationFromStore(conversationId);
  
  // Si plus de conversations non lues, fermer la notification
  if (Object.keys(conversations).length === 0) {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then(registration => {
        registration.getNotifications({ tag: 'whatsapp-all-messages' })
          .then(notifications => {
            notifications.forEach(n => n.close());
          });
      });
    }
  } else {
    // Sinon, mettre à jour la notification avec les conversations restantes
    const convs = Object.values(conversations);
    const convCount = convs.length;
    const totalMessages = convs.reduce((sum, c) => sum + c.unreadCount, 0);
    
    const sortedConvs = convs.sort((a, b) => b.lastUpdate - a.lastUpdate);
    const primaryConversation = sortedConvs[0];
    
    const title = convCount === 1 
      ? primaryConversation.contactName
      : `${convCount} conversations • ${totalMessages} message${totalMessages > 1 ? 's' : ''}`;
    const body = buildNotificationBody(conversations);
    
    showNotification(title, {
      body,
      tag: 'whatsapp-all-messages',
      data: { conversations, timestamp: Date.now() },
      icon: primaryConversation?.contactImage || '/192x192.svg',
      badge: '/192x192.svg',
      color: '#25d366',
      silent: true, // Pas de son pour les mises à jour
      vibrate: [] // Pas de vibration pour les mises à jour
    });
  }
}

