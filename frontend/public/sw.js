// Service Worker pour PWA
const CACHE_NAME = 'lmdcvtc-whatsapp-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192x192.png',
  '/icon-512x512.png'
];

// Installation du Service Worker
self.addEventListener('install', (event) => {
  console.log('Service Worker: Installation');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Mise en cache des assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// Activation du Service Worker
self.addEventListener('activate', (event) => {
  console.log('Service Worker: Activation');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            console.log('Service Worker: Suppression ancien cache', cache);
            return caches.delete(cache);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Stratégie de cache : Network First (toujours essayer le réseau d'abord)
self.addEventListener('fetch', (event) => {
  // Ignorer les requêtes non-GET
  if (event.request.method !== 'GET') return;
  
  // Ignorer les requêtes vers d'autres domaines (API, etc.)
  if (!event.request.url.startsWith(self.location.origin)) return;

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
        icon: data.icon || '/icon-192x192.png',
        badge: data.badge || '/icon-192x192.png'
      };
    } catch (e) {
      // Si ce n'est pas du JSON, essayer comme texte
      notificationData.body = event.data.text() || notificationData.body;
    }
  }

  const options = {
    body: notificationData.body,
    icon: notificationData.icon || '/icon-192x192.png',
    badge: notificationData.badge || '/icon-192x192.png',
    vibrate: [200, 100, 200], // Vibration comme WhatsApp
    tag: notificationData.conversationId 
      ? `whatsapp-msg-${notificationData.conversationId}` 
      : 'whatsapp-notification',
    requireInteraction: false,
    data: {
      conversationId: notificationData.conversationId
    }
  };

  event.waitUntil(
    self.registration.showNotification(notificationData.title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const conversationId = event.notification.data?.conversationId;
  const action = event.action;
  
  // Si l'utilisateur a cliqué sur "Fermer", ne rien faire
  if (action === 'close') {
    return;
  }
  
  event.waitUntil(
    (async () => {
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
          if (conversationId) {
            client.postMessage({
              type: 'OPEN_CONVERSATION',
              conversationId
            });
          }
          return;
        }
      }
      
      // Sinon, ouvrir une nouvelle fenêtre
      const url = conversationId 
        ? `/?conversation=${conversationId}` 
        : '/';
      await clients.openWindow(url);
    })()
  );
});

