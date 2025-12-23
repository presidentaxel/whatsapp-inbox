# 📱 Système de Notifications

Ce document décrit en détail comment fonctionne le système de notifications dans WhatsApp Inbox, qui reçoit quoi et selon quelles règles.

## Vue d'ensemble

Le système de notifications fonctionne à deux niveaux :
1. **Notifications frontend (navigateur)** : notifications visuelles dans le navigateur pour les utilisateurs
2. **Notifications backend (WhatsApp)** : notifications WhatsApp envoyées lors d'escalades vers un humain

---

## 🔔 Notifications Frontend (Navigateur)

### Qu'est-ce qui déclenche une notification ?

Une notification est envoyée quand :
- **Un nouveau message entrant** (`direction = 'inbound'`) est reçu
- Le message n'est **pas** de type `reaction`
- Le message est **inséré** dans la table `messages` de Supabase

### Qui reçoit une notification ?

#### ✅ Conditions obligatoires (toutes doivent être remplies)

1. **Permission navigateur accordée**
   - L'utilisateur doit avoir accordé la permission de notifications au navigateur
   - Vérifié via `Notification.permission === 'granted'`

2. **Préférences utilisateur activées pour le compte**
   - Les notifications doivent être activées pour ce compte spécifique
   - Stockage : `localStorage` avec la clé `notif_prefs_v1`
   - Format : `{ [accountId]: { messages: boolean, previews: boolean, reactions: boolean, status: boolean } }`
   - Par défaut : `true` si aucune préférence n'est définie

3. **Accès à la conversation**
   - L'utilisateur doit avoir la permission `conversations.view` pour le compte
   - L'utilisateur ne doit **pas** avoir `access_level = 'aucun'` pour ce compte
   - Vérifié via `hasPermission('conversations.view', accountId)` dans `AuthContext`

4. **Profil chargé**
   - Le profil de l'utilisateur doit être chargé (pour vérifier les permissions)

#### ❌ Conditions qui empêchent la notification

1. **Message sortant** (`direction = 'outbound'`)
   - Les messages envoyés par l'utilisateur ne génèrent pas de notification

2. **Conversation ouverte ET fenêtre active**
   - Si l'utilisateur regarde déjà la conversation dans une fenêtre active (`document.hasFocus() && isVisible && conversationId === selectedConversationId`)
   - **Exception** : les notifications peuvent être forcées via l'option `force: true`

3. **Doublons**
   - Un système de cache empêche les notifications multiples pour le même message
   - Clé : `${message.id}-${conversation.id}`
   - Nettoyage automatique après 5 minutes

### Comment les notifications sont-elles déclenchées ?

Le système utilise **Supabase Realtime** pour écouter les nouveaux messages :

```javascript
// frontend/src/hooks/useGlobalNotifications.js
supabaseClient
  .channel('global-messages-notifications-all')
  .on('postgres_changes', {
    event: 'INSERT',
    schema: 'public',
    table: 'messages',
  }, async (payload) => {
    // Vérifier toutes les conditions ci-dessus
    // Puis appeler notifyNewMessage()
  })
```

### Contenu de la notification

#### Titre
- **Une conversation** : Nom du contact (ex: "Jean Dupont")
- **Plusieurs conversations** : "N conversations • X messages"

#### Corps de la notification
- Liste des conversations avec aperçu des messages
- Format : `"Contact: Aperçu du message"`
- Limité à 3-4 conversations principales

#### Aperçu du message
- **Texte** : Premiers 100 caractères du message
- **Médias** : 
  - 📷 Photo
  - 🎥 Vidéo
  - 🎵 Audio
  - 📎 Document
  - 😊 Autocollant
  - 🎤 Message vocal
- **Localisation** : 📍 Localisation
- **Contact** : 👤 Contact

#### Icône
- Image de profil du contact (si disponible)
- Sinon : `/192x192.svg` (icône WhatsApp de l'app)

#### Actions disponibles
- **Ouvrir** : Ouvre la conversation dans l'app
- **Tout marquer comme lu** : Marque toutes les conversations comme lues

### Gestion des notifications groupées

Le système regroupe toutes les notifications en une seule notification globale :
- **Tag unique** : `'whatsapp-all-messages'`
- **Stockage** : `localStorage` avec la clé `'whatsapp_notifications_conversations'`
- **Mise à jour** : Chaque nouveau message met à jour la notification globale au lieu d'en créer une nouvelle
- **Nettoyage** : Quand une conversation est marquée comme lue, elle est retirée du stockage et la notification est mise à jour

### Configuration des préférences

Les préférences sont configurables via l'interface dans **Paramètres → Notifications** :

- **Notifications des messages** : Recevoir une notification pour chaque nouveau message
- **Voir les aperçus** : Afficher un aperçu du message dans la notification
- **Notifications des réactions** : Recevoir une notification pour les réactions aux messages
- **Réactions au statut** : Recevoir des notifications pour les réactions aux statuts

Les préférences sont **par compte WhatsApp**, permettant un contrôle granulaire.

---

## 📞 Notifications Backend (Escalade vers Humain)

### Qu'est-ce qui déclenche une notification WhatsApp ?

Une notification WhatsApp est envoyée lors d'une **escalade vers un humain**, qui se produit dans deux cas :

1. **Le bot ne peut pas répondre**
   - Le bot Gemini retourne une réponse vide
   - Le bot retourne le message de fallback : `"Je me renseigne auprès d'un collègue et je reviens vers vous au plus vite."`

2. **Le bot rencontre une erreur**
   - Erreur lors de l'envoi de la réponse du bot
   - Erreur lors de la génération de la réponse

### Qui reçoit la notification WhatsApp ?

Le numéro configuré dans `HUMAN_BACKUP_NUMBER` (variable d'environnement).

**Important** : Si `HUMAN_BACKUP_NUMBER` n'est pas configuré, aucune notification n'est envoyée (mais l'escalade a quand même lieu).

### Contenu de la notification

Le message WhatsApp envoyé contient :
```
[Escalade] Conversation {conversation_id} (client: {client_number})
Dernier message: {dernier_message_du_client}
```

### Comment fonctionne l'escalade ?

```python
# backend/app/services/message_service.py

async def _escalate_to_human(conversation: Dict[str, Any], last_customer_message: str):
    # Désactiver le mode bot pour cette conversation
    await set_conversation_bot_mode(conversation["id"], False)
    # Envoyer la notification WhatsApp
    await _notify_backup(conversation, last_customer_message)

async def _notify_backup(conversation: Dict[str, Any], last_customer_message: str):
    backup_number = settings.HUMAN_BACKUP_NUMBER
    if not backup_number:
        logger.info("No HUMAN_BACKUP_NUMBER configured; skipping backup notification")
        return
    
    account_id = conversation["account_id"]
    summary = (
        f"[Escalade] Conversation {conversation['id']} (client: {conversation.get('client_number')})\n"
        f"Dernier message: {last_customer_message}"
    )
    await _send_direct_whatsapp(account_id, backup_number, summary)
```

### Compte WhatsApp utilisé

Le système utilise le compte WhatsApp associé à la conversation (`conversation.account_id`) pour envoyer la notification. Cela permet d'avoir plusieurs comptes WhatsApp Business avec chacun son numéro de backup.

---

## 🔄 Flux complet d'une notification frontend

```
1. WhatsApp envoie un webhook → Backend
   ↓
2. Backend stocke le message dans Supabase (table messages)
   ↓
3. Supabase Realtime déclenche un événement INSERT
   ↓
4. useGlobalNotifications.js écoute l'événement
   ↓
5. Vérification des conditions :
   - Permission navigateur ✓
   - Préférences activées pour le compte ✓
   - Permissions utilisateur ✓
   - Pas de doublon ✓
   - Message entrant ✓
   - Conversation pas ouverte OU fenêtre inactive ✓
   ↓
6. notifyNewMessage() construit la notification
   ↓
7. showMessageNotification() affiche la notification (via Service Worker)
   ↓
8. Utilisateur clique sur la notification → Ouvre la conversation
```

---

## 🔄 Flux complet d'une escalade backend

```
1. Client envoie un message WhatsApp
   ↓
2. Backend reçoit le webhook et stocke le message
   ↓
3. Si conversation en mode bot :
   - Bot Gemini génère une réponse
   ↓
4. Si réponse vide OU réponse = fallback message :
   - _escalate_to_human() est appelé
   ↓
5. Mode bot désactivé pour la conversation
   ↓
6. _notify_backup() envoie un message WhatsApp à HUMAN_BACKUP_NUMBER
   ↓
7. L'humain reçoit la notification avec les détails de l'escalade
```

---

## 📝 Configuration

### Variables d'environnement (Backend)

```bash
# Numéro WhatsApp qui reçoit les notifications d'escalade
HUMAN_BACKUP_NUMBER=+33123456789
```

### Préférences utilisateur (Frontend)

Stockées dans `localStorage` avec la clé `notif_prefs_v1` :

```json
{
  "account-id-1": {
    "messages": true,
    "previews": true,
    "reactions": false,
    "status": false
  },
  "account-id-2": {
    "messages": true,
    "previews": false,
    "reactions": true,
    "status": true
  }
}
```

---

## 🛠️ Fichiers clés

### Frontend
- `frontend/src/utils/notifications.js` : Utilitaires de base pour les notifications
- `frontend/src/hooks/useGlobalNotifications.js` : Hook qui écoute tous les nouveaux messages
- `frontend/src/components/chat/ChatWindow.jsx` : Notifications dans la fenêtre de chat
- `frontend/src/components/settings/NotificationSettings.jsx` : Interface de configuration
- `frontend/src/registerSW.js` : Service Worker pour afficher les notifications

### Backend
- `backend/app/services/message_service.py` : 
  - `_escalate_to_human()` : Escalade vers un humain
  - `_notify_backup()` : Envoi de la notification WhatsApp
  - `_send_direct_whatsapp()` : Envoi direct via WhatsApp API

---

## 🐛 Debug

### Les notifications ne s'affichent pas

1. Vérifier la permission navigateur : `Notification.permission`
2. Vérifier les préférences dans `localStorage` : `localStorage.getItem('notif_prefs_v1')`
3. Vérifier les permissions utilisateur dans `AuthContext`
4. Vérifier les logs de la console pour les erreurs

### Les notifications d'escalade ne sont pas envoyées

1. Vérifier que `HUMAN_BACKUP_NUMBER` est configuré dans `.env`
2. Vérifier les logs backend pour voir si `_notify_backup()` est appelé
3. Vérifier que le compte WhatsApp a les permissions pour envoyer des messages

