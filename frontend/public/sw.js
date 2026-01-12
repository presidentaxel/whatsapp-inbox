// Service Worker pour PWA avec notifications en arrière-plan
// IMPORTANT: Incrémenter cette version à chaque déploiement pour forcer la mise à jour
// Cette version est aussi utilisée pour forcer la mise à jour des icônes PWA
const SW_VERSION = 'v2.0.3';
const CACHE_NAME = `lmdcvtc-whatsapp-${SW_VERSION}`;

// URLs des icônes (sans version pour compatibilité développement Vite)
const ICON_192 = `/192x192.svg`;
const ICON_512 = `/512x512.svg`;
const MANIFEST = `/manifest.json`;

const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  MANIFEST,
  ICON_192,
  ICON_512
];

// Intervalle pour vérifier les nouveaux messages quand l'app est en arrière-plan
const BACKGROUND_SYNC_TAG = 'background-sync-messages';
const SYNC_INTERVAL = 30000; // 30 secondes - ajustez selon vos besoins

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('Service Worker: Installation');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Mise en cache des assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => {
        // skipWaiting() pour activer immédiatement le nouveau Service Worker
        // Important sur macOS pour que les notifications fonctionnent rapidement
        self.skipWaiting();
      })
      .catch((error) => {
        console.error('Service Worker: Erreur lors de la mise en cache', error);
        // Même en cas d'erreur, activer le Service Worker
        self.skipWaiting();
      })
  );
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
  console.log(`Service Worker: Activation (version ${SW_VERSION})`);
  event.waitUntil(
    Promise.all([
      // Nettoyer les anciens caches
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cache) => {
            if (cache !== CACHE_NAME && cache.startsWith('lmdcvtc-whatsapp-')) {
              console.log('Service Worker: Suppression ancien cache', cache);
              return caches.delete(cache);
            }
          })
        );
      }),
      // Prendre le contrôle de toutes les pages (important pour macOS)
      self.clients.claim()
    ]).then(() => {
      console.log(`Service Worker: Activé et prêt pour les notifications (version ${SW_VERSION})`);
      // Notifier tous les clients de la nouvelle version
      return self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then((clients) => {
        clients.forEach((client) => {
          client.postMessage({
            type: 'SW_UPDATED',
            version: SW_VERSION,
            message: 'Une nouvelle version est disponible. Veuillez recharger la page.'
          });
        });
      });
    })
  );
});

// Écouter les messages pour activer immédiatement (skip waiting)
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Stratégie de cache : Network First (toujours essayer le réseau d'abord)
self.addEventListener('fetch', (event) => {
  // Ignorer les requêtes non-GET
  if (event.request.method !== 'GET') return;
  
  // Ignorer les requêtes vers d'autres domaines (API, etc.)
  if (!event.request.url.startsWith(self.location.origin)) return;

  const url = new URL(event.request.url);
  
  // Ne PAS mettre en cache les fichiers statiques (SVG, manifest, etc.) en développement
  // Pour forcer le rechargement des icônes et du manifest
  const shouldSkipCache = 
    url.pathname.endsWith('.svg') ||
    url.pathname === '/manifest.json' ||
    url.pathname.includes('/192x192') ||
    url.pathname.includes('/512x512') ||
    url.pathname.includes('/favicon');

  if (shouldSkipCache) {
    // Pour les fichiers statiques, toujours aller chercher sur le réseau sans cache
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cloner la réponse car elle ne peut être consommée qu'une fois
        const responseClone = response.clone();
        
        // Mettre en cache la nouvelle réponse
        if (response.status === 200) {
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        
        return response;
      })
      .catch(() => {
        // Si le réseau échoue, essayer le cache
        return caches.match(event.request);
      })
  );
});

// Background Sync : Synchroniser les messages même quand l'app est fermée
self.addEventListener('sync', (event) => {
  if (event.tag === BACKGROUND_SYNC_TAG) {
    event.waitUntil(
      (async () => {
        try {
          // Cette fonction sera appelée périodiquement même quand l'app est fermée
          // Vous pouvez faire un fetch vers votre API pour vérifier les nouveaux messages
          
          // Optionnel : envoyer un message à toutes les fenêtres ouvertes
          const clients = await self.clients.matchAll();
          clients.forEach(client => {
            client.postMessage({
              type: 'BACKGROUND_SYNC',
              timestamp: Date.now()
            });
          });
        } catch (error) {
          console.error('❌ Erreur background sync:', error);
        }
      })()
    );
  }
});

// Gestion des notifications push (pour les push serveur)
self.addEventListener('push', (event) => {
  let notificationData = {
    title: 'WhatsApp LMDCVTC',
    body: 'Nouveau message',
    conversationId: null
  };

  // Parser les données push si disponibles
  if (event.data) {
    try {
      const data = event.data.json();
      notificationData = {
        title: data.title || notificationData.title,
        body: data.body || notificationData.body,
        conversationId: data.conversationId || null,
        icon: data.icon || ICON_192,
        badge: data.badge || ICON_192,
        image: data.image || null // Image du contact pour notification riche
      };
    } catch (e) {
      // Si ce n'est pas du JSON, essayer comme texte
      notificationData.body = event.data.text() || notificationData.body;
    }
  }

  // Options de notification style WhatsApp Desktop/Mobile
  const options = {
    body: notificationData.body,
    // Icon = image de profil du contact (affiché en rond)
    icon: notificationData.icon || ICON_192,
    // Badge = icône WhatsApp (petite icône dans le coin)
    badge: ICON_192,
    // Image = image de profil large pour notifications riches (si supporté)
    image: notificationData.image || null,
    // Vibration courte et double (style WhatsApp)
    vibrate: [200, 100, 200],
    // Tag unique par conversation pour regrouper les notifications
    tag: notificationData.conversationId 
      ? `whatsapp-msg-${notificationData.conversationId}` 
      : 'whatsapp-notification',
    requireInteraction: false, // Disparaît automatiquement
    silent: false, // Son activé
    timestamp: Date.now(),
    dir: 'ltr',
    lang: 'fr',
    // Couleur de thème WhatsApp (vert #25d366)
    color: '#25d366',
    // Renotifier si plusieurs messages dans la même conversation
    renotify: true,
    // Données personnalisées pour l'interaction
    data: {
      conversationId: notificationData.conversationId,
      contactName: notificationData.title,
      timestamp: Date.now()
    },
    // Actions interactives (Répondre, Marquer comme lu)
    actions: notificationData.conversationId ? [
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

  event.waitUntil(
    self.registration.showNotification(notificationData.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const notificationData = event.notification.data || {};
  const conversationId = notificationData.conversationId;
  const conversations = notificationData.conversations || {};
  const action = event.action;
  
  event.waitUntil(
    (async () => {
      // Gérer les actions
      if (action === 'mark-all-read') {
        // Marquer toutes les conversations comme lues
        const allClients = await clients.matchAll({
          type: 'window',
          includeUncontrolled: true
        });
        const conversationIds = Object.keys(conversations);
        for (const client of allClients) {
          if (client.url.includes(self.location.origin)) {
            client.postMessage({
              type: 'MARK_ALL_AS_READ',
              conversationIds: conversationIds
            });
          }
        }
        // Nettoyer le localStorage dans le client
        return;
      }
      
      if (action === 'mark-read' || action === 'open') {
        // Si on a plusieurs conversations, ouvrir la plus récente
        // Sinon, ouvrir celle spécifiée
        const targetConvId = conversationId || (Object.keys(conversations).length > 0 
          ? Object.keys(conversations).sort((a, b) => 
              (conversations[b]?.lastUpdate || 0) - (conversations[a]?.lastUpdate || 0)
            )[0]
          : null);
        
        if (action === 'mark-read' && targetConvId) {
          // Marquer comme lu (message sera envoyé à l'app si ouverte)
          const allClients = await clients.matchAll({
            type: 'window',
            includeUncontrolled: true
          });
          for (const client of allClients) {
            if (client.url.includes(self.location.origin)) {
              client.postMessage({
                type: 'MARK_AS_READ',
                conversationId: targetConvId
              });
            }
          }
          return;
        }
        
        // Action par défaut : ouvrir la conversation
        // Essayer de trouver une fenêtre/tab ouverte
        const allClients = await clients.matchAll({
          type: 'window',
          includeUncontrolled: true
        });
        
        // Si une fenêtre est déjà ouverte, la focus et y naviguer
        for (const client of allClients) {
          if (client.url.includes(self.location.origin)) {
            await client.focus();
            
            // Envoyer un message pour ouvrir la conversation
            if (targetConvId) {
              client.postMessage({
                type: 'OPEN_CONVERSATION',
                conversationId: targetConvId
              });
            }
            return;
          }
        }
        
        // Sinon, ouvrir une nouvelle fenêtre
        const url = targetConvId 
          ? `/?conversation=${targetConvId}` 
          : '/';
        await clients.openWindow(url);
      }
    })()
  );
});

