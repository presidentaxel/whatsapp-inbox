# Guide Complet : Tester les Webhooks avec Ngrok

## 🎯 Objectif

Utiliser ngrok pour créer un tunnel public vers votre backend local et tester si les webhooks WhatsApp arrivent correctement. Cela permet d'isoler le problème :
- ✅ Si ça fonctionne avec ngrok → Le problème vient de l'URL de production (accessibilité, DNS, firewall)
- ❌ Si ça ne fonctionne pas avec ngrok → Le problème vient du code ou de la configuration

---

## 📋 Prérequis

1. **Ngrok installé**
   ```bash
   # Windows avec Chocolatey
   choco install ngrok
   
   # Ou télécharger depuis https://ngrok.com/download
   ```

2. **Backend démarré localement**
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

3. **Variables d'environnement configurées**
   - `WHATSAPP_VERIFY_TOKEN` doit être défini dans votre `.env`

---

## 🚀 Méthode Automatique (Recommandée)

### Étape 1 : Lancer le script de test

```bash
cd backend
python scripts/test_webhook_ngrok.py
```

Le script va :
- ✅ Vérifier que ngrok est installé
- ✅ Vérifier que le backend est démarré
- ✅ Démarrer un tunnel ngrok automatiquement
- ✅ Afficher l'URL publique ngrok
- ✅ Tester l'endpoint webhook
- ✅ Donner les instructions pour Meta

### Étape 2 : Configurer Meta

1. **Copiez l'URL ngrok** affichée par le script (ex: `https://xxxxx.ngrok.io/webhook/whatsapp`)

2. **Allez dans Meta for Developers**
   - https://developers.facebook.com/apps/
   - Sélectionnez votre app
   - Webhooks > WhatsApp

3. **Configurez le webhook**
   - **URL de rappel** : Collez l'URL ngrok complète
   - **Vérifier le token** : Entrez votre `WHATSAPP_VERIFY_TOKEN` (celui de votre `.env`)
   - Cliquez sur **"Vérifier et enregistrer"**

4. **Vérifiez l'abonnement**
   - Assurez-vous que le champ **"messages"** est **"Abonné(e)"** (toggle bleu à droite)
   - Si ce n'est pas le cas, cliquez sur le toggle pour l'activer

5. **Testez le webhook**
   - Cliquez sur le bouton **"Test"** à côté de "messages"
   - Ou utilisez **"Envoyer au serveur v24.0"** dans la fenêtre d'échantillon
   - Regardez les logs du backend

### Étape 3 : Vérifier les Logs

Dans les logs du backend, vous devriez voir :

```
INFO:     🔍 Webhook verification request: mode=subscribe, token=***..., challenge=present
INFO:     Webhook verified with global token
INFO:     127.0.0.1:XXXXX - "GET /webhook/whatsapp?hub.mode=subscribe&hub.verify_token=...&hub.challenge=... HTTP/1.1" 200 OK
```

Puis quand un message arrive :

```
INFO:     📥 POST /webhook/whatsapp received from <IP>
INFO:     📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1
INFO:     📥 Webhook received: object=whatsapp_business_account, entries=1
INFO:     📋 Processing entry 1/1
INFO:     🔍 Looking for account with phone_number_id from metadata: <PHONE_NUMBER_ID>
INFO:     ✅ Found account using metadata phone_number_id: <ACCOUNT_NAME>
INFO:     📨 Processing 1 messages
INFO:       Processing message 1/1: type=text, from=<NUMBER>
INFO:       ✅ Message 1 processed successfully
```

---

## 🔧 Méthode Manuelle

Si vous préférez faire manuellement :

### Étape 1 : Démarrer ngrok

```bash
ngrok http 8000
```

Ngrok va afficher quelque chose comme :
```
Forwarding   https://xxxxx.ngrok.io -> http://localhost:8000
```

### Étape 2 : Récupérer l'URL

- Ouvrez http://127.0.0.1:4040 dans votre navigateur
- Copiez l'URL "Forwarding" (ex: `https://xxxxx.ngrok.io`)

### Étape 3 : Configurer Meta

1. Allez dans Meta for Developers > Votre App > Webhooks > WhatsApp
2. **URL de rappel** : `https://xxxxx.ngrok.io/webhook/whatsapp`
3. **Vérifier le token** : Votre `WHATSAPP_VERIFY_TOKEN`
4. Cliquez sur **"Vérifier et enregistrer"**

### Étape 4 : Tester

- Utilisez le bouton **"Test"** dans Meta
- Ou envoyez un vrai message depuis WhatsApp
- Regardez les logs du backend

---

## 🧪 Test avec un Webhook Simulé

Vous pouvez aussi tester manuellement avec curl :

```bash
curl -X POST https://xxxxx.ngrok.io/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "YOUR_PHONE_NUMBER_ID",
      "changes": [{
        "value": {
          "messaging_product": "whatsapp",
          "metadata": {
            "phone_number_id": "YOUR_PHONE_NUMBER_ID"
          },
          "messages": [{
            "from": "16315551181",
            "id": "TEST_123",
            "timestamp": "1504902988",
            "type": "text",
            "text": {"body": "Test message"}
          }]
        },
        "field": "messages"
      }]
    }]
  }'
```

Remplacez `YOUR_PHONE_NUMBER_ID` par votre vrai `phone_number_id`.

---

## 🔍 Diagnostic

### ✅ Si les webhooks arrivent via ngrok

**Conclusion** : Le code fonctionne, le problème vient de l'URL de production.

**Actions** :
1. Vérifiez que l'URL de production est accessible publiquement
2. Vérifiez les logs du serveur de production (firewall, proxy, etc.)
3. Testez l'URL de production avec curl :
   ```bash
   curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \
     -H "Content-Type: application/json" \
     -d '{"object":"whatsapp_business_account","entry":[]}'
   ```
4. Vérifiez les logs Meta pour voir les tentatives de livraison vers l'URL de production

### ❌ Si les webhooks n'arrivent pas via ngrok

**Conclusion** : Le problème vient du code ou de la configuration.

**Actions** :
1. Vérifiez les logs du backend pour voir les erreurs
2. Vérifiez que le `WHATSAPP_VERIFY_TOKEN` correspond exactement
3. Vérifiez que le backend répond bien sur le port 8000
4. Vérifiez que l'endpoint `/webhook/whatsapp` est bien accessible

---

## ⚠️ Notes Importantes

1. **L'URL ngrok change à chaque redémarrage** (sauf avec un compte payant ngrok)
   - Si vous redémarrez ngrok, vous devez mettre à jour l'URL dans Meta

2. **Ngrok doit rester actif** pendant les tests
   - Si vous fermez ngrok, les webhooks ne pourront plus arriver

3. **Limitations ngrok gratuit**
   - L'URL change à chaque redémarrage
   - Limite de connexions simultanées
   - Pour un usage en production, utilisez votre URL de production

4. **Vérification du token**
   - Le token dans Meta doit correspondre EXACTEMENT à `WHATSAPP_VERIFY_TOKEN`
   - Vérifiez qu'il n'y a pas d'espaces avant/après
   - Vérifiez la casse (majuscules/minuscules)

---

## 🐛 Problèmes Courants

### Ngrok ne démarre pas
- Vérifiez que ngrok est installé : `ngrok version`
- Vérifiez que le port 8000 n'est pas déjà utilisé
- Essayez un autre port : `ngrok http 8001`

### La vérification échoue dans Meta
- Vérifiez que le token correspond exactement
- Vérifiez que le backend est bien démarré
- Vérifiez les logs du backend pour voir l'erreur exacte

### Les webhooks n'arrivent pas
- Vérifiez que ngrok est toujours actif
- Vérifiez que l'URL dans Meta est correcte
- Vérifiez que le champ "messages" est bien abonné
- Regardez les logs Meta pour voir les tentatives de livraison

---

## 📊 Checklist

- [ ] Ngrok installé
- [ ] Backend démarré sur le port 8000
- [ ] Tunnel ngrok créé
- [ ] URL ngrok copiée
- [ ] Webhook configuré dans Meta avec l'URL ngrok
- [ ] Token de vérification correspond
- [ ] Champ "messages" abonné
- [ ] Test effectué depuis Meta
- [ ] Logs du backend vérifiés
- [ ] Message de test reçu et stocké

---

## 🎉 Résultat Attendu

Si tout fonctionne, vous devriez voir dans les logs :

1. **Vérification du webhook** (GET)
2. **Réception d'un webhook** (POST)
3. **Traitement du message**
4. **Message stocké en base**

Et le message devrait apparaître dans votre interface !

