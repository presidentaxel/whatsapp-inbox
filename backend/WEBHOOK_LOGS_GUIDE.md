# Guide des Logs Webhook - Comment Vérifier si les Messages Arrivent

## 🔍 Diagnostic Rapide

**Vos logs actuels montrent uniquement des requêtes GET :**

```
INFO: GET /messages/media/...
INFO: GET /conversations?...
INFO: GET /messages/...
```

**❌ AUCUN log POST /webhook/whatsapp = Les webhooks n'arrivent PAS au backend**

---

## ✅ À Quoi Ressemblent les Logs Quand un Webhook Arrive

Quand Meta envoie un webhook pour un nouveau message, vous devriez voir **TOUS** ces logs dans l'ordre :

### 1. Réception du Webhook (Endpoint)

```
INFO:     📥 POST /webhook/whatsapp received from <IP_ADDRESS>
INFO:     📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1
```

### 2. Détails de l'Entry

```
INFO:        Entry 1: id=<PHONE_NUMBER_ID>, changes=1
INFO:           Change 1: field=messages, phone_number_id=<PHONE_NUMBER_ID>, has_messages=True, has_statuses=False
```

### 3. Détection des Messages

```
INFO:     📨 Change contains 1 message(s)
INFO:        - Message type: text, from: <WHATSAPP_NUMBER>
INFO:     📨 Webhook contains 1 message(s) and 0 status(es)
```

### 4. Traitement du Webhook

```
INFO:     📥 Webhook received: object=whatsapp_business_account, entries=1
INFO:     📋 Processing entry 1/1
```

### 5. Recherche du Compte

```
INFO:     🔍 Looking for account with phone_number_id from metadata: <PHONE_NUMBER_ID>
INFO:     ✅ Found account using metadata phone_number_id: <ACCOUNT_NAME> (id: <ACCOUNT_ID>)
```

### 6. Traitement du Message

```
INFO:     📨 Processing 1 messages
INFO:       Processing message 1/1: type=text, from=<WHATSAPP_NUMBER>
INFO:       ✅ Message 1 processed successfully
INFO:     ✅ Message processed successfully: conversation_id=<CONV_ID>, type=text, from=<WHATSAPP_NUMBER>
```

### 7. Réponse au Webhook

```
INFO:     127.0.0.1:XXXXX - "POST /webhook/whatsapp HTTP/1.1" 200 OK
```

---

## ❌ Exemples de Logs d'Erreur

### Erreur : Compte Non Trouvé

```
ERROR:    ❌ CRITICAL: Cannot find account for webhook!
ERROR:       metadata phone_number_id: <PHONE_NUMBER_ID>
ERROR:       entry.id: <ENTRY_ID>
ERROR:       This webhook will be SKIPPED - messages will NOT be stored!
ERROR:    📋 Available accounts in database:
ERROR:       ✅ ACTIVE - <ACCOUNT_NAME>: phone_number_id=<PHONE_NUMBER_ID>
```

### Erreur : Format Invalide

```
WARNING:  ⚠️ No entries in webhook payload
DEBUG:   📋 Webhook data keys: ['object', 'entry']
```

### Erreur : Traitement du Message

```
ERROR:    ❌ Error processing message 1/1: <ERROR_MESSAGE>
ERROR:    Traceback (most recent call last):
ERROR:      ...
```

---

## 🔧 Comment Vérifier la Configuration du Webhook

### 1. Vérifier dans Meta for Developers

1. Allez sur : [https://developers.facebook.com/apps/](https://developers.facebook.com/apps/)
2. Sélectionnez votre application
3. Allez dans : **Webhooks** > **WhatsApp**
4. Vérifiez que :
  - ✅ Le statut est **"Actif"** (cercle vert)
  - ✅ L'URL est : `https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp`
  - ✅ Les champs suivants sont **cochés** :
    - `messages`
    - `message_status`

### 2. Tester le Webhook

Dans Meta for Developers :

1. Cliquez sur **"Tester"** ou **"Send test message"**
2. Regardez les logs du backend
3. Vous devriez voir les logs ci-dessus apparaître

### 3. Vérifier les Logs Meta

Dans Meta for Developers > Webhooks > WhatsApp > **Logs** :

- Vérifiez s'il y a des erreurs (codes 4xx ou 5xx)
- Vérifiez les tentatives de livraison
- Vérifiez les timestamps des dernières tentatives

### 4. Vérifier l'Accessibilité de l'Endpoint

Testez manuellement l'endpoint :

```bash
curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{"object":"whatsapp_business_account","entry":[]}'
```

Vous devriez recevoir : `{"status":"received"}`

---

## 🐛 Problèmes Courants

### Problème 1 : Aucun Log POST

**Symptôme :** Aucun log `POST /webhook/whatsapp` dans les logs

**Causes possibles :**

- Le webhook n'est pas activé dans Meta
- L'URL du webhook est incorrecte
- Le endpoint n'est pas accessible (firewall, DNS, etc.)
- Meta n'envoie pas les webhooks (vérifier les logs Meta)

**Solution :**

1. Vérifier la configuration dans Meta
2. Tester le webhook depuis Meta
3. Vérifier les logs Meta pour voir les tentatives de livraison

### Problème 2 : Webhook Arrive mais Compte Non Trouvé

**Symptôme :** Logs montrent `❌ CRITICAL: Cannot find account for webhook!`

**Causes possibles :**

- Le `phone_number_id` dans le webhook ne correspond à aucun compte
- Le compte existe mais est inactif (`is_active = false`)
- Le `phone_number_id` dans la base ne correspond pas à celui dans le webhook

**Solution :**

1. Vérifier les comptes disponibles dans la base
2. Vérifier que le `phone_number_id` correspond
3. Vérifier que le compte est actif

### Problème 3 : Webhook Arrive mais Message Non Stocké

**Symptôme :** Logs montrent le traitement mais le message n'apparaît pas en base

**Causes possibles :**

- Erreur lors de l'insertion (vérifier les logs d'erreur)
- Problème de connexion à la base de données
- Erreur silencieuse dans le traitement

**Solution :**

1. Vérifier les logs d'erreur complets
2. Vérifier la connexion à Supabase
3. Relancer le script de diagnostic

---

## 📊 Commandes Utiles

### Vérifier les Messages en Base

```bash
cd backend
python scripts/check_webhook_logs.py
```

### Diagnostic Complet

```bash
cd backend
python scripts/comprehensive_webhook_diagnostic.py
```

### Vérifier les Webhooks Récents

```bash
cd backend
python scripts/view_recent_webhooks.py
```

---

## ✅ Checklist de Vérification

- Le webhook est activé dans Meta (statut vert)
- L'URL du webhook est correcte
- Les champs `messages` et `message_status` sont cochés
- Les logs montrent des requêtes `POST /webhook/whatsapp`
- Le compte est trouvé lors du traitement
- Les messages sont stockés en base de données
- Les messages apparaissent dans l'interface

---

## 📝 Notes Importantes

1. **Les webhooks arrivent en temps réel** : Dès qu'un message est envoyé sur WhatsApp, Meta envoie un webhook dans les secondes qui suivent.
2. **Les logs sont essentiels** : Si vous ne voyez pas les logs `POST /webhook/whatsapp`, c'est que les webhooks n'arrivent pas.
3. **Vérifier les logs Meta** : Les logs dans Meta for Developers montrent les tentatives de livraison et les erreurs éventuelles.
4. **Tester régulièrement** : Utilisez le bouton "Tester" dans Meta pour vérifier que le webhook fonctionne.

