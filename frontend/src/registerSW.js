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
 * Afficher une notification pour un nouveau message (style WhatsApp exact)
 * @param {string} contactName - Nom du contact
 * @param {string} messagePreview - Aperçu du message
 * @param {string} conversationId - ID de la conversation
 * @param {string} contactImage - URL de l'image de profil (optionnel)
 */
export async function showMessageNotification(contactName, messagePreview, conversationId, contactImage = null) {
  // Le titre est juste le nom du contact (comme WhatsApp)
  // Pas besoin de préfixe "WhatsApp" ou autre
  const title = contactName;
  
  // Options de notification style WhatsApp Desktop/Mobile
  const options = {
    body: messagePreview, // Aperçu du message directement
    tag: `whatsapp-msg-${conversationId}`, // Tag unique par conversation pour regrouper
    data: { 
      conversationId,
      contactName,
      timestamp: Date.now()
    },
    // Icon = image de profil du contact (rond, comme WhatsApp)
    icon: contactImage || '/192x192.svg',
    // Badge = icône WhatsApp pour identifier l'app
    badge: '/192x192.svg',
    // Image = image de profil large (notifications riches - si supporté)
    image: contactImage || null,
    // Vibration style WhatsApp (court, double)
    vibrate: [200, 100, 200],
    requireInteraction: false, // Disparaît automatiquement
    silent: false, // Son activé
    timestamp: Date.now(),
    dir: 'ltr',
    lang: 'fr',
    // Renotifier si plusieurs messages de la même conversation
    renotify: true,
    sticky: false,
    // Couleur de thème WhatsApp (vert)
    color: '#25d366',
    // Actions interactives (si supporté par le navigateur)
    actions: conversationId ? [
      {
        action: 'open',
        title: 'Répondre'
      },
      {
        action: 'mark-read',
        title: 'Marquer comme lu'
      }
    ] : []
  };

  await showNotification(title, options);
}

