/**
 * Enregistrement du Service Worker pour la PWA
 */

export function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    // Sur macOS, il est crucial que le Service Worker soit enregistré et actif
    // avant toute tentative de notification
    const registerSW = () => {
      navigator.serviceWorker
        .register('/sw.js', { scope: '/' })
        .then((registration) => {
          // Sur macOS, s'assurer que le Service Worker est actif
          if (registration.active) {
            // Service Worker actif
          } else if (registration.installing) {
            registration.installing.addEventListener('statechange', () => {
              if (registration.installing.state === 'activated') {
                // Service Worker activé
              }
            });
          } else if (registration.waiting) {
            // Si un Service Worker est en attente, l'activer
            registration.waiting.postMessage({ type: 'SKIP_WAITING' });
          }
          
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
        .catch(() => {});
    };

    // Enregistrer immédiatement si la page est déjà chargée
    // Sur macOS, c'est important pour que les notifications fonctionnent
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
      registerSW();
    } else {
      // Sinon, attendre le chargement
      window.addEventListener('load', registerSW);
    }

    // Écouter les mises à jour du SW
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      // Recharger automatiquement pour forcer la mise à jour
      window.location.reload();
    });

    // Écouter les messages du Service Worker
    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'SW_UPDATED') {
        // Recharger automatiquement pour forcer la mise à jour
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
    return permission === 'granted';
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
  });

  // Détecter quand l'app est installée
  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
  });
}

export async function showInstallPrompt() {
  if (!deferredPrompt) {
    return false;
  }

  // Afficher le prompt
  deferredPrompt.prompt();
  
  // Attendre le choix de l'utilisateur
  const { outcome } = await deferredPrompt.userChoice;
  
  deferredPrompt = null;
  
  return outcome === 'accepted';
}

/**
 * Détecter si on est sur macOS
 */
function isMacOS() {
  return navigator.platform.toUpperCase().indexOf('MAC') >= 0 || 
         navigator.userAgent.toUpperCase().indexOf('MAC') >= 0;
}

/**
 * Afficher une notification locale (style WhatsApp)
 * Adapté pour macOS et autres plateformes
 * @param {string} title - Titre de la notification
 * @param {object} options - Options de la notification
 * @returns {Promise<void>}
 */
export async function showNotification(title, options = {}) {
  // Demander la permission si nécessaire
  if (Notification.permission === 'default') {
    const granted = await requestNotificationPermission();
    if (!granted) {
      return;
    }
  }
  
  if (Notification.permission !== 'granted') {
    return;
  }

  const isMac = isMacOS();
  
  // Options par défaut style WhatsApp
  const defaultOptions = {
    icon: '/192x192.svg',
    badge: '/192x192.svg',
    tag: 'whatsapp-notification',
    requireInteraction: false,
    silent: false,
    color: '#25d366', // Vert WhatsApp
    ...options
  };

  // Sur macOS, vibrate n'est pas supporté, on le retire
  if (isMac && defaultOptions.vibrate) {
    delete defaultOptions.vibrate;
  } else if (!isMac && !defaultOptions.vibrate) {
    // Sur les autres plateformes, ajouter la vibration par défaut si non spécifiée
    defaultOptions.vibrate = [200, 100, 200];
  }

  // Sur macOS, certaines options peuvent ne pas être supportées
  // On nettoie les options pour éviter les erreurs
  const cleanOptions = { ...defaultOptions };
  
  // Sur macOS, retirer les options potentiellement problématiques si elles sont null/undefined
  if (isMac) {
    // Retirer image si null (peut causer des problèmes sur certains navigateurs Mac)
    if (cleanOptions.image === null) {
      delete cleanOptions.image;
    }
    // S'assurer que badge est toujours défini (requis sur macOS)
    if (!cleanOptions.badge) {
      cleanOptions.badge = '/192x192.svg';
    }
  }

  // Sur macOS, les notifications DOIVENT passer par le Service Worker
  // Pas de fallback avec new Notification()
  if (isMac) {
    if (!('serviceWorker' in navigator)) {
      return;
    }
    
    try {
      const registration = await navigator.serviceWorker.ready;
      
      if (!registration) {
        return;
      }
      
      // Afficher la notification via le service worker (obligatoire sur macOS)
      await registration.showNotification(title, cleanOptions);
    } catch (error) {
      // Erreur silencieuse
    }
  } else {
    // Sur les autres plateformes, essayer d'abord le Service Worker, puis fallback
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      try {
        const registration = await navigator.serviceWorker.ready;
        await registration.showNotification(title, cleanOptions);
      } catch (error) {
        // Fallback : notification simple sans service worker
        try {
          new Notification(title, cleanOptions);
        } catch (fallbackError) {
          // Erreur silencieuse
        }
      }
    } else {
      // Fallback : notification simple sans service worker
      try {
        new Notification(title, cleanOptions);
      } catch (error) {
        // Erreur silencieuse
      }
    }
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
    return {};
  }
}

function storeConversations(conversations) {
  try {
    localStorage.setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(conversations));
  } catch (error) {
    // Erreur silencieuse
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
      // Erreur silencieuse
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
  
  const isMac = isMacOS();
  
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
    // Badge = icône WhatsApp pour identifier l'app (important sur macOS)
    badge: '/192x192.svg',
    requireInteraction: false, // Disparaît automatiquement
    silent: existingNotification, // Son seulement pour nouveau message, pas pour mise à jour
    timestamp: Date.now(),
    dir: 'ltr',
    lang: 'fr',
    // Renotifier si plusieurs messages
    renotify: true,
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

  // Sur macOS, retirer certaines options non supportées ou problématiques
  if (isMac) {
    // Retirer vibrate (non supporté sur macOS)
    delete options.vibrate;
    // Retirer image si null (peut causer des problèmes)
    if (primaryConversation?.contactImage) {
      options.image = primaryConversation.contactImage;
    }
    // Retirer sticky (peut causer des problèmes sur macOS)
    delete options.sticky;
  } else {
    // Sur les autres plateformes, ajouter la vibration si nouvelle notification
    if (!existingNotification) {
      options.vibrate = [200, 100, 200];
    }
    // Ajouter l'image si disponible
    if (primaryConversation?.contactImage) {
      options.image = primaryConversation.contactImage;
    }
  }

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
    
    const isMac = isMacOS();
    const updateOptions = {
      body,
      tag: 'whatsapp-all-messages',
      data: { conversations, timestamp: Date.now() },
      icon: primaryConversation?.contactImage || '/192x192.svg',
      badge: '/192x192.svg',
      color: '#25d366',
      silent: true // Pas de son pour les mises à jour
    };
    
    // Sur macOS, ne pas ajouter vibrate
    if (!isMac) {
      updateOptions.vibrate = []; // Pas de vibration pour les mises à jour
    }
    
    showNotification(title, updateOptions);
  }
}

