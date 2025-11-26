# 📱 Guide des Notifications Push - WhatsApp LMDCVTC

## ✅ Ce qui est déjà configuré

Votre application PWA est **déjà prête** pour les notifications push ! Voici ce qui fonctionne :

1. ✅ Service Worker enregistré (`sw.js`)
2. ✅ Gestion des événements push
3. ✅ Manifest PWA configuré
4. ✅ Icônes et badges
5. ✅ Fonctions utilitaires créées

## 🚀 Comment utiliser les notifications

### 1️⃣ Initialiser les notifications au démarrage

Dans votre fichier `main.jsx` ou `App.jsx`, ajoutez :

```javascript
import { initNotifications } from './utils/notifications';

// Au démarrage de l'application
initNotifications();
```

### 2️⃣ Demander la permission manuellement

Vous pouvez créer un bouton dans vos paramètres :

```javascript
import { askForNotificationPermission } from './utils/notifications';

function SettingsPanel() {
  const handleEnableNotifications = async () => {
    const granted = await askForNotificationPermission();
    if (granted) {
      alert('Notifications activées ! ✅');
    } else {
      alert('Notifications refusées ❌');
    }
  };

  return (
    <button onClick={handleEnableNotifications}>
      Activer les notifications
    </button>
  );
}
```

### 3️⃣ Notifier lors de nouveaux messages

Dans votre composant `ChatWindow.jsx`, ajoutez les notifications automatiques :

```javascript
import { notifyNewMessage } from '../../utils/notifications';

// Dans votre useEffect qui écoute les nouveaux messages via Supabase
useEffect(() => {
  if (!conversationId) return;

  const channel = supabaseClient
    .channel(`messages:${conversationId}`)
    .on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'messages',
        filter: `conversation_id=eq.${conversationId}`
      },
      (payload) => {
        const newMessage = payload.new;
        
        // Afficher la notification si c'est un message entrant
        if (!newMessage.from_me) {
          notifyNewMessage(newMessage, conversation);
        }
        
        // Reste de votre code...
        setMessages(prev => sortMessages([...prev, newMessage]));
      }
    )
    .subscribe();

  return () => {
    channel.unsubscribe();
  };
}, [conversationId, conversation]);
```

### 4️⃣ Notification de test

Vous pouvez tester les notifications avec un bouton :

```javascript
import { showTestNotification } from './utils/notifications';

<button onClick={showTestNotification}>
  🔔 Tester les notifications
</button>
```

## 📱 Fonctionnalités disponibles

### Notifications locales (déjà fonctionnelles)

Les notifications locales fonctionnent **immédiatement** :
- ✅ Affichage de notifications quand l'app est ouverte en arrière-plan
- ✅ Vibration du téléphone
- ✅ Son de notification (natif)
- ✅ Badge d'application
- ✅ Actions (Ouvrir / Fermer)
- ✅ Ouverture de la conversation au clic

### Push notifications serveur (nécessite backend)

Pour recevoir des notifications même quand l'app est fermée, vous aurez besoin :

1. **Clés VAPID** (pour identifier votre serveur)
2. **Backend qui envoie les notifications**
3. **Abonnement push stocké en base de données**

## 🔧 Configuration avancée (optionnel)

### Ajouter les Push Notifications serveur

Si vous voulez envoyer des notifications depuis votre backend :

#### 1. Générer les clés VAPID

```bash
npm install web-push --save-dev
npx web-push generate-vapid-keys
```

Vous obtiendrez :
```
Public Key: BH8r...
Private Key: xyz...
```

#### 2. Souscrire aux push notifications

Ajoutez dans `registerSW.js` :

```javascript
export async function subscribeToPushNotifications() {
  const registration = await navigator.serviceWorker.ready;
  
  // Votre clé publique VAPID
  const vapidPublicKey = 'VOTRE_CLE_PUBLIQUE_ICI';
  
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
  });
  
  // Envoyer l'abonnement à votre backend
  await fetch('/api/notifications/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscription)
  });
  
  return subscription;
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');
  
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}
```

#### 3. Envoyer des notifications depuis le backend (Node.js)

```javascript
const webpush = require('web-push');

webpush.setVapidDetails(
  'mailto:votre@email.com',
  process.env.VAPID_PUBLIC_KEY,
  process.env.VAPID_PRIVATE_KEY
);

// Envoyer une notification
async function sendNotification(subscription, data) {
  const payload = JSON.stringify({
    title: 'Nouveau message',
    body: data.message,
    icon: '/icon-192x192.png',
    conversationId: data.conversationId
  });

  await webpush.sendNotification(subscription, payload);
}
```

## 🎨 Personnalisation des notifications

Vous pouvez personnaliser les notifications dans `utils/notifications.js` :

```javascript
await showNotification('Titre', {
  body: 'Message de la notification',
  icon: '/icon-192x192.png',          // Icône principale
  badge: '/icon-192x192.png',          // Badge (Android)
  image: '/screenshot.png',            // Image large (optionnel)
  vibrate: [200, 100, 200],           // Pattern de vibration
  tag: 'unique-id',                    // ID unique (remplace les notifs similaires)
  requireInteraction: false,           // true = reste jusqu'au clic
  silent: false,                       // true = pas de son
  actions: [                           // Boutons d'action
    { action: 'open', title: 'Ouvrir' },
    { action: 'close', title: 'Fermer' }
  ],
  data: {                              // Données personnalisées
    conversationId: '123',
    url: '/chat/123'
  }
});
```

## 📊 Statut des notifications

Pour vérifier le statut des notifications :

```javascript
import { areNotificationsEnabled } from './utils/notifications';

if (areNotificationsEnabled()) {
  console.log('✅ Notifications activées');
} else {
  console.log('❌ Notifications désactivées');
}

// Ou directement :
console.log(Notification.permission); // "granted", "denied", ou "default"
```

## 🐛 Dépannage

### Les notifications ne s'affichent pas

1. ✅ Vérifiez que vous êtes en **HTTPS** ou **localhost**
2. ✅ Vérifiez que le Service Worker est actif : `chrome://serviceworker-internals/`
3. ✅ Vérifiez les permissions : `Notification.permission`
4. ✅ Testez avec `showTestNotification()`
5. ✅ Regardez la console pour les erreurs

### Les notifications ne vibrent pas

- Sur iOS : les vibrations sont limitées
- Sur Android : vérifiez les paramètres système

### Les notifications disparaissent trop vite

Ajoutez `requireInteraction: true` pour qu'elles restent jusqu'au clic.

### L'application ne s'ouvre pas au clic

Vérifiez que le Service Worker gère bien l'événement `notificationclick` (déjà fait dans `sw.js`).

## 📱 Compatibilité

| Plateforme | Notifications locales | Push notifications | Actions |
|-----------|----------------------|-------------------|---------|
| Chrome Android | ✅ | ✅ | ✅ |
| Firefox Android | ✅ | ✅ | ✅ |
| Samsung Internet | ✅ | ✅ | ✅ |
| Safari iOS | ⚠️ Limitées | ⚠️ Limitées | ❌ |
| Chrome Desktop | ✅ | ✅ | ✅ |
| Firefox Desktop | ✅ | ✅ | ✅ |
| Safari Desktop | ⚠️ | ⚠️ | ❌ |

⚠️ **Note iOS** : iOS a des limitations importantes sur les PWA et les notifications. Pour une meilleure expérience iOS, envisagez une app native.

## 🎯 Prochaines étapes recommandées

1. ✅ Intégrer `initNotifications()` dans `main.jsx`
2. ✅ Ajouter `notifyNewMessage()` dans `ChatWindow.jsx`
3. ✅ Créer un bouton dans `SettingsPanel.jsx` pour activer/désactiver
4. ✅ Tester sur mobile
5. ⏭️ (Optionnel) Implémenter les push notifications serveur avec VAPID

## 💡 Exemple complet

Voir le composant d'exemple dans `components/NotificationSettings.jsx` pour une implémentation complète.

