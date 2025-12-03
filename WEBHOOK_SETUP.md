# Configuration du Webhook WhatsApp en Production

## Prérequis

1. Votre backend doit être accessible publiquement via HTTPS
2. Vous devez avoir un domaine configuré (ex: `https://api.votre-domaine.com`)
3. Le verify_token doit être configuré dans votre `.env`

## Configuration dans Meta/Facebook

### 1. Obtenir le verify_token

Le verify_token est stocké dans votre fichier `.env` sous la variable `WHATSAPP_VERIFY_TOKEN`.

Si vous ne l'avez pas, générez-en un :

```bash
cd backend
python scripts/generate_verify_token.py
```

Cela affichera un token que vous devrez copier.

### 2. Configurer le webhook dans Meta

1. Allez dans [Meta for Developers](https://developers.facebook.com/)
2. Sélectionnez votre app WhatsApp Business
3. Allez dans **Webhooks** > **WhatsApp**
4. Cliquez sur **Configurer** ou **Modifier**
5. Entrez les informations suivantes :
   - **URL du callback** : `https://votre-domaine.com/webhook/whatsapp`
     - Remplacez `votre-domaine.com` par votre domaine réel
     - L'URL doit être en HTTPS
   - **Token de vérification** : Collez le token depuis `WHATSAPP_VERIFY_TOKEN` dans votre `.env`
6. Cliquez sur **Vérifier et enregistrer**

### 3. S'abonner aux événements

Après avoir configuré le webhook, vous devez vous abonner aux événements :

1. Dans la section **Webhooks**, cliquez sur **S'abonner aux champs**
2. Cochez au minimum :
   - ✅ `messages` (pour recevoir les messages)
   - ✅ `message_status` (pour recevoir les statuts de livraison)
3. Cliquez sur **Enregistrer**

## Vérification

### Test manuel de l'endpoint

Testez que votre endpoint répond correctement :

```bash
# Test de vérification (GET)
curl "https://votre-domaine.com/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=VOTRE_TOKEN&hub.challenge=test123"

# Devrait retourner : test123
```

### Vérifier dans Meta

1. Dans Meta for Developers, allez dans **Webhooks** > **WhatsApp**
2. Vérifiez que le statut est **Actif** (cercle vert)
3. Cliquez sur **Tester** pour envoyer un webhook de test
4. Vérifiez les logs de votre backend pour voir si le webhook arrive

### Vérifier les logs du backend

Quand un message arrive, vous devriez voir dans les logs :

```
INFO: 📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1
INFO: 📨 Webhook contains 1 message(s) and 0 status(es)
INFO: 📋 Processing entry 1/1
INFO: ✅ Account found: ...
INFO: 📨 Processing 1 messages
INFO: ✅ Message processed successfully: ...
```

## Dépannage

### Le webhook n'est pas appelé

1. **Vérifiez que l'URL est correcte** :
   - L'URL doit être accessible publiquement
   - L'URL doit être en HTTPS (pas HTTP)
   - L'URL doit pointer vers `/webhook/whatsapp`

2. **Vérifiez le verify_token** :
   - Le token dans Meta doit correspondre à `WHATSAPP_VERIFY_TOKEN` dans votre `.env`
   - Le token est sensible à la casse

3. **Vérifiez les abonnements** :
   - Assurez-vous que vous êtes abonné au champ `messages`
   - Vérifiez dans Meta que les abonnements sont actifs

4. **Vérifiez les logs du backend** :
   - Cherchez les erreurs dans les logs
   - Vérifiez que le backend est bien démarré et accessible

### Erreur 403 lors de la vérification

- Vérifiez que le `verify_token` dans Meta correspond exactement à `WHATSAPP_VERIFY_TOKEN`
- Vérifiez que le token n'a pas d'espaces avant/après

### Le webhook arrive mais les messages ne sont pas traités

- Vérifiez les logs du backend pour voir les erreurs
- Vérifiez que `phone_number_id` dans le webhook correspond à un compte dans `whatsapp_accounts`
- Vérifiez que le compte a un `access_token` valide

## Script de diagnostic

Utilisez le script de diagnostic pour vérifier la configuration :

```bash
cd backend
python scripts/check_webhook_status.py
```

Ce script vérifie :
- Les abonnements webhook dans Meta
- La configuration du verify_token
- L'accessibilité de l'endpoint

## Configuration multi-compte

Si vous avez plusieurs comptes WhatsApp, chaque compte peut avoir son propre `verify_token` :

1. Ajoutez le compte dans la table `whatsapp_accounts` avec son propre `verify_token`
2. Configurez un webhook séparé dans Meta pour chaque compte (ou utilisez le même endpoint)
3. Le backend détectera automatiquement quel compte utiliser en fonction du `phone_number_id` dans le webhook

