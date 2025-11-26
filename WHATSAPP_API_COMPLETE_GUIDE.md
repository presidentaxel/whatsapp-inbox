# Guide Complet de l'API WhatsApp Business

Ce guide explique comment utiliser toutes les fonctionnalités de l'API WhatsApp Business Cloud API implémentées dans cette application.

## 📋 Table des matières

1. [Configuration](#configuration)
2. [Messages](#1-messages)
3. [Médias](#2-médias)
4. [Numéros de téléphone](#3-numéros-de-téléphone)
5. [Profil Business](#4-profil-business)
6. [Templates de messages](#5-templates-de-messages)
7. [Webhooks](#6-webhooks)
8. [WABA Management](#7-waba-management)
9. [Utilitaires](#8-utilitaires)

---

## Configuration

### Variables d'environnement requises

Ajoutez ces variables à votre fichier `.env` :

```bash
# Configuration de base WhatsApp (obligatoire)
WHATSAPP_TOKEN=votre_access_token
WHATSAPP_PHONE_ID=votre_phone_number_id
WHATSAPP_VERIFY_TOKEN=votre_verify_token
WHATSAPP_PHONE_NUMBER=+33123456789

# Configuration Meta App (pour fonctionnalités avancées)
META_APP_ID=votre_app_id
META_APP_SECRET=votre_app_secret
```

### Configuration dans la base de données

Exécutez la migration SQL pour ajouter les champs nécessaires :

```bash
psql -d votre_database -f supabase/migrations/011_whatsapp_extended_fields.sql
```

Ou via Supabase Dashboard, ajoutez ces champs à la table `whatsapp_accounts` :
- `waba_id` (text) - WhatsApp Business Account ID
- `business_id` (text) - Meta Business Manager ID
- `app_id` (text) - Meta App ID (optionnel, surcharge global)
- `app_secret` (text) - Meta App Secret (optionnel, surcharge global)

---

## 1. Messages

### 1.1 Envoyer un message texte

**Endpoint:** `POST /api/whatsapp/messages/text/{account_id}`

```json
{
  "to": "33612345678",
  "text": "Bonjour ! Ceci est un message de test.",
  "preview_url": true
}
```

**Exemple cURL :**
```bash
curl -X POST "http://localhost:8000/api/whatsapp/messages/text/account_uuid" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "33612345678",
    "text": "Bonjour !",
    "preview_url": true
  }'
```

### 1.2 Envoyer un message avec média

**Endpoint:** `POST /api/whatsapp/messages/media/{account_id}`

```json
{
  "to": "33612345678",
  "media_type": "image",
  "media_id": "123456789",
  "caption": "Voici une belle image"
}
```

**Types de médias supportés :**
- `image` - Images (JPEG, PNG)
- `audio` - Fichiers audio (MP3, OGG, AMR)
- `video` - Vidéos (MP4, 3GP)
- `document` - Documents (PDF, DOC, etc.)

### 1.3 Envoyer un message template

**Endpoint:** `POST /api/whatsapp/messages/template/{account_id}`

```json
{
  "to": "33612345678",
  "template_name": "hello_world",
  "language_code": "en",
  "components": [
    {
      "type": "body",
      "parameters": [
        {
          "type": "text",
          "text": "John Doe"
        }
      ]
    }
  ]
}
```

### 1.4 Envoyer un message avec boutons interactifs

**Endpoint:** `POST /api/whatsapp/messages/interactive/buttons/{account_id}`

```json
{
  "to": "33612345678",
  "body_text": "Choisissez une option :",
  "buttons": [
    {
      "id": "btn_1",
      "title": "Option 1"
    },
    {
      "id": "btn_2",
      "title": "Option 2"
    }
  ],
  "header_text": "Menu principal",
  "footer_text": "Merci de votre choix"
}
```

**Limites :**
- Maximum 3 boutons
- Titre du bouton : max 20 caractères

### 1.5 Envoyer un message avec liste déroulante

**Endpoint:** `POST /api/whatsapp/messages/interactive/list/{account_id}`

```json
{
  "to": "33612345678",
  "body_text": "Sélectionnez un produit",
  "button_text": "Voir les produits",
  "sections": [
    {
      "title": "Catégorie A",
      "rows": [
        {
          "id": "prod_1",
          "title": "Produit 1",
          "description": "Description du produit 1"
        },
        {
          "id": "prod_2",
          "title": "Produit 2"
        }
      ]
    }
  ],
  "header_text": "Notre catalogue",
  "footer_text": "Prix TTC"
}
```

---

## 2. Médias

### 2.1 Upload un média

**Endpoint:** `POST /api/whatsapp/media/upload/{account_id}`

```bash
curl -X POST "http://localhost:8000/api/whatsapp/media/upload/account_uuid" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

**Réponse :**
```json
{
  "success": true,
  "data": {
    "id": "media_id_123456"
  }
}
```

### 2.2 Récupérer les infos d'un média

**Endpoint:** `GET /api/whatsapp/media/info/{account_id}/{media_id}`

**Réponse :**
```json
{
  "success": true,
  "data": {
    "url": "https://lookaside.fbsbx.com/...",
    "mime_type": "image/jpeg",
    "sha256": "...",
    "file_size": 123456
  }
}
```

### 2.3 Télécharger un média

**Endpoint:** `GET /api/whatsapp/media/download/{account_id}/{media_id}`

Retourne le fichier en binaire avec les headers appropriés.

### 2.4 Supprimer un média

**Endpoint:** `DELETE /api/whatsapp/media/{account_id}/{media_id}`

---

## 3. Numéros de téléphone

### 3.1 Lister les numéros

**Endpoint:** `GET /api/whatsapp/phone/list/{account_id}`

**Prérequis :** Le champ `waba_id` doit être configuré dans `whatsapp_accounts`.

### 3.2 Détails d'un numéro

**Endpoint:** `GET /api/whatsapp/phone/details/{account_id}`

**Réponse :**
```json
{
  "success": true,
  "data": {
    "verified_name": "Ma Société",
    "display_phone_number": "+33 6 12 34 56 78",
    "quality_rating": "GREEN",
    "code_verification_status": "VERIFIED"
  }
}
```

### 3.3 Enregistrer un numéro

**Endpoint:** `POST /api/whatsapp/phone/register/{account_id}`

```json
{
  "pin": "123456"
}
```

⚠️ **Important :** Cette opération nécessite des permissions admin.

### 3.4 Demander un code de vérification

**Endpoint:** `POST /api/whatsapp/phone/request-verification/{account_id}`

```json
{
  "code_method": "SMS",
  "language": "fr_FR"
}
```

**Méthodes disponibles :** `SMS` ou `VOICE`

### 3.5 Vérifier le code

**Endpoint:** `POST /api/whatsapp/phone/verify/{account_id}`

```json
{
  "code": "123456"
}
```

---

## 4. Profil Business

### 4.1 Récupérer le profil

**Endpoint:** `GET /api/whatsapp/profile/{account_id}`

**Réponse :**
```json
{
  "success": true,
  "data": {
    "about": "Description de votre entreprise",
    "address": "123 Rue de la Paix, Paris",
    "description": "Description longue...",
    "email": "contact@entreprise.com",
    "profile_picture_url": "https://...",
    "websites": ["https://entreprise.com"],
    "vertical": "RETAIL"
  }
}
```

### 4.2 Mettre à jour le profil

**Endpoint:** `POST /api/whatsapp/profile/{account_id}`

```json
{
  "about": "Nouvelle description courte (max 139 caractères)",
  "address": "Nouvelle adresse",
  "description": "Nouvelle description longue (max 512 caractères)",
  "email": "nouveau@email.com",
  "websites": ["https://site1.com", "https://site2.com"],
  "vertical": "RETAIL"
}
```

**Secteurs disponibles :**
- `AUTOMOTIVE`, `BEAUTY`, `APPAREL`, `EDU`, `ENTERTAINMENT`
- `EVENT_PLANNING`, `FINANCE`, `GROCERY`, `GOVT`, `HOTEL`
- `HEALTH`, `NONPROFIT`, `PROF_SERVICES`, `RETAIL`, `TRAVEL`
- `RESTAURANT`, `NOT_A_BIZ`, `OTHER`

---

## 5. Templates de messages

### 5.1 Lister les templates

**Endpoint:** `GET /api/whatsapp/templates/list/{account_id}?limit=100&after=cursor`

**Prérequis :** Le champ `waba_id` doit être configuré.

### 5.2 Créer un template

**Endpoint:** `POST /api/whatsapp/templates/create/{account_id}`

```json
{
  "name": "order_confirmation",
  "category": "UTILITY",
  "language": "fr",
  "components": [
    {
      "type": "HEADER",
      "format": "TEXT",
      "text": "Confirmation de commande"
    },
    {
      "type": "BODY",
      "text": "Bonjour {{1}}, votre commande {{2}} a été confirmée !"
    },
    {
      "type": "FOOTER",
      "text": "Merci de votre confiance"
    },
    {
      "type": "BUTTONS",
      "buttons": [
        {
          "type": "URL",
          "text": "Suivre ma commande",
          "url": "https://exemple.com/track/{{1}}"
        }
      ]
    }
  ]
}
```

**Catégories de templates :**
- `AUTHENTICATION` - Codes de vérification (gratuit)
- `UTILITY` - Notifications transactionnelles (gratuit pendant 24h après message client)
- `MARKETING` - Messages promotionnels (nécessite opt-in, payant)

**Variables :**
- Utilisez `{{1}}`, `{{2}}`, etc. pour les variables dynamiques
- Les variables sont numérotées séquentiellement

### 5.3 Supprimer un template

**Endpoint:** `DELETE /api/whatsapp/templates/delete/{account_id}`

```json
{
  "name": "order_confirmation"
}
```

---

## 6. Webhooks

### 6.1 Vérification du webhook (déjà implémenté)

**Endpoint:** `GET /webhook/whatsapp`

Ce endpoint est appelé automatiquement par Meta lors de la configuration.

**Configuration dans Meta Dashboard :**
1. Allez dans App Dashboard > Webhooks
2. Configurez l'URL : `https://votre-domaine.com/webhook/whatsapp`
3. Utilisez le `WHATSAPP_VERIFY_TOKEN` de votre `.env`
4. Abonnez-vous aux événements : `messages`, `message_status`

### 6.2 Réception des événements (déjà implémenté)

**Endpoint:** `POST /webhook/whatsapp`

Reçoit automatiquement :
- Nouveaux messages
- Statuts de messages (sent, delivered, read, failed)
- Mises à jour de profil
- Alertes de compte

### 6.3 S'abonner aux webhooks

**Endpoint:** `POST /api/whatsapp/waba/webhooks/subscribe/{account_id}`

Active la réception des webhooks pour ce WABA.

### 6.4 Se désabonner

**Endpoint:** `DELETE /api/whatsapp/waba/webhooks/unsubscribe/{account_id}`

### 6.5 Lister les abonnements

**Endpoint:** `GET /api/whatsapp/waba/webhooks/subscriptions/{account_id}`

---

## 7. WABA Management

### 7.1 Détails du WABA

**Endpoint:** `GET /api/whatsapp/waba/details/{account_id}`

**Prérequis :** `waba_id` configuré.

**Réponse :**
```json
{
  "success": true,
  "data": {
    "id": "123456789",
    "name": "Mon Business",
    "timezone_id": "Europe/Paris",
    "message_template_namespace": "abc123_xyz",
    "account_review_status": "APPROVED"
  }
}
```

### 7.2 Lister les WABAs possédés

**Endpoint:** `GET /api/whatsapp/waba/owned/{account_id}`

**Prérequis :** `business_id` configuré.

### 7.3 Lister les WABAs partagés

**Endpoint:** `GET /api/whatsapp/waba/client/{account_id}`

**Prérequis :** `business_id` configuré.

---

## 8. Utilitaires

### 8.1 Debug d'un token

**Endpoint:** `GET /api/whatsapp/utils/debug-token/{account_id}`

Vérifie la validité et les scopes d'un token d'accès.

**Réponse :**
```json
{
  "success": true,
  "data": {
    "app_id": "123456789",
    "type": "USER",
    "application": "Mon App",
    "expires_at": 0,
    "is_valid": true,
    "scopes": [
      "whatsapp_business_management",
      "whatsapp_business_messaging"
    ],
    "user_id": "987654321"
  }
}
```

### 8.2 Générer un app access token

**Endpoint:** `POST /api/whatsapp/utils/generate-app-token`

Nécessite des permissions admin globales.

### 8.3 Valider un numéro de téléphone

**Endpoint:** `POST /api/whatsapp/utils/validate-phone?phone=+33612345678`

Normalise un numéro au format WhatsApp.

---

## 🔐 Authentification

Toutes les routes nécessitent un JWT token valide dans le header :

```
Authorization: Bearer YOUR_JWT_TOKEN
```

Obtenez un token via :
```bash
POST /auth/login
{
  "email": "user@example.com",
  "password": "password"
}
```

## 🚀 Démarrage rapide

1. **Appliquer la migration SQL :**
   ```bash
   psql -d votre_database -f supabase/migrations/011_whatsapp_extended_fields.sql
   ```

2. **Configurer les variables d'environnement :**
   ```bash
   META_APP_ID=votre_app_id
   META_APP_SECRET=votre_app_secret
   ```

3. **Redémarrer l'application :**
   ```bash
   cd backend
   uvicorn app.main:app --reload
   ```

4. **Tester avec Swagger UI :**
   Ouvrez `http://localhost:8000/docs`

## 📚 Documentation officielle Meta

- [WhatsApp Business Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Webhooks](https://developers.facebook.com/docs/graph-api/webhooks)
- [Message Templates](https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates)
- [Business Profile](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/business-profiles)

## ⚠️ Limites et quotas

- **Messages templates :** Limités par le tier de votre numéro (1000-100K/jour)
- **Messages conversationnels :** Gratuits pendant 24h après message client
- **Médias :** Max 100 MB, gardés 30 jours
- **Boutons interactifs :** Max 3 boutons
- **Listes :** Max 10 sections, 10 lignes par section

## 🆘 Résolution de problèmes

### "waba_id not configured"
→ Ajoutez le WABA ID dans la table `whatsapp_accounts` pour cet account.

### "META_APP_ID must be configured"
→ Ajoutez `META_APP_ID` et `META_APP_SECRET` dans votre `.env`.

### "Webhook verification failed"
→ Vérifiez que `WHATSAPP_VERIFY_TOKEN` correspond à celui configuré dans Meta Dashboard.

### Template rejeté
→ Vérifiez que le contenu respecte les [politiques Meta](https://www.facebook.com/business/help/896873687365001).

---

## 🎯 Exemples d'utilisation

### Cas d'usage 1 : Envoyer une confirmation de commande

```python
import requests

# 1. Créer un template (une seule fois)
response = requests.post(
    "http://localhost:8000/api/whatsapp/templates/create/account_id",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "name": "order_confirmation",
        "category": "UTILITY",
        "language": "fr",
        "components": [
            {
                "type": "BODY",
                "text": "Bonjour {{1}}, votre commande #{{2}} d'un montant de {{3}}€ a été confirmée !"
            }
        ]
    }
)

# 2. Envoyer le template (après approbation Meta)
response = requests.post(
    "http://localhost:8000/api/whatsapp/messages/template/account_id",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "to": "33612345678",
        "template_name": "order_confirmation",
        "language_code": "fr",
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Marie"},
                    {"type": "text", "text": "12345"},
                    {"type": "text", "text": "49.90"}
                ]
            }
        ]
    }
)
```

### Cas d'usage 2 : Menu interactif

```python
# Envoyer un menu avec boutons
response = requests.post(
    "http://localhost:8000/api/whatsapp/messages/interactive/buttons/account_id",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "to": "33612345678",
        "body_text": "Que souhaitez-vous faire ?",
        "buttons": [
            {"id": "track_order", "title": "Suivre commande"},
            {"id": "support", "title": "Support"},
            {"id": "new_order", "title": "Nouvelle commande"}
        ],
        "header_text": "Bienvenue !",
        "footer_text": "Service client disponible 24/7"
    }
)
```

### Cas d'usage 3 : Catalogue de produits

```python
# Envoyer une liste de produits
response = requests.post(
    "http://localhost:8000/api/whatsapp/messages/interactive/list/account_id",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={
        "to": "33612345678",
        "body_text": "Découvrez nos produits",
        "button_text": "Voir le catalogue",
        "sections": [
            {
                "title": "Électronique",
                "rows": [
                    {
                        "id": "prod_1",
                        "title": "Laptop Pro",
                        "description": "999€"
                    },
                    {
                        "id": "prod_2",
                        "title": "Smartphone XL",
                        "description": "599€"
                    }
                ]
            },
            {
                "title": "Accessoires",
                "rows": [
                    {
                        "id": "prod_3",
                        "title": "Écouteurs Sans Fil",
                        "description": "79€"
                    }
                ]
            }
        ]
    }
)
```

---

Bon développement ! 🚀

