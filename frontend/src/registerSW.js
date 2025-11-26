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
 * Afficher une notification locale
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

  // Vérifier si le service worker est disponible
  if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
    const registration = await navigator.serviceWorker.ready;
    
    // Afficher la notification via le service worker
    await registration.showNotification(title, {
      icon: '/icon-192x192.png',
      badge: '/icon-192x192.png',
      vibrate: [200, 100, 200],
      tag: 'whatsapp-notification',
      requireInteraction: false,
      ...options
    });
  } else {
    // Fallback : notification simple sans service worker
    new Notification(title, {
      icon: '/icon-192x192.png',
      ...options
    });
  }
}

/**
 * Afficher une notification pour un nouveau message
 * @param {string} contactName - Nom du contact
 * @param {string} messagePreview - Aperçu du message
 * @param {string} conversationId - ID de la conversation
 */
export async function showMessageNotification(contactName, messagePreview, conversationId) {
  await showNotification(`${contactName}`, {
    body: messagePreview,
    tag: `whatsapp-msg-${conversationId}`,
    data: { conversationId }, // Données personnalisées
    badge: '/icon-192x192.png',
    icon: '/icon-192x192.png',
    vibrate: [200, 100, 200], // Vibration comme WhatsApp
    requireInteraction: false, // Disparaît automatiquement
    silent: false, // Son activé
    timestamp: Date.now(),
    actions: [
      {
        action: 'open',
        title: '📱 Ouvrir'
      },
      {
        action: 'close',
        title: '✕'
      }
    ]
  });
}

