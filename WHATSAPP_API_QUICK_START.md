# 🚀 Démarrage Rapide - API WhatsApp Complète

## Installation et Configuration

### 1. Appliquer la migration SQL

```bash
# Via psql
psql -d votre_database -f supabase/migrations/011_whatsapp_extended_fields.sql

# Ou via Supabase Dashboard
# Copiez le contenu du fichier et exécutez-le dans l'éditeur SQL
```

### 2. Mettre à jour les variables d'environnement

Ajoutez ces lignes à votre fichier `.env` :

```bash
# Configuration Meta App (nouvelles variables)
META_APP_ID=votre_meta_app_id
META_APP_SECRET=votre_meta_app_secret
```

**Comment obtenir ces valeurs ?**

1. Allez sur [Meta for Developers](https://developers.facebook.com/)
2. Sélectionnez votre app WhatsApp Business
3. Dans Settings > Basic :
   - **App ID** → `META_APP_ID`
   - **App Secret** (cliquez sur Show) → `META_APP_SECRET`

### 3. Configurer les IDs dans la base de données (optionnel)

Pour utiliser les fonctionnalités avancées (templates, WABA management), ajoutez ces informations dans la table `whatsapp_accounts` :

```sql
UPDATE whatsapp_accounts
SET 
  waba_id = 'votre_waba_id',
  business_id = 'votre_business_id'
WHERE id = 'votre_account_id';
```

**Comment obtenir ces IDs ?**

1. **WABA ID** (WhatsApp Business Account ID) :
   - Meta for Developers > WhatsApp > API Setup
   - L'ID affiché en haut de la page

2. **Business ID** :
   - [Business Manager](https://business.facebook.com/)
   - Settings > Business Info > Business ID

### 4. Redémarrer l'application

```bash
cd backend
uvicorn app.main:app --reload
```

Ou avec Docker :
```bash
docker-compose restart backend
```

---

## 🧪 Tester les Endpoints

### Via Swagger UI

1. Ouvrez http://localhost:8000/docs
2. Cliquez sur "Authorize" en haut à droite
3. Entrez votre JWT token
4. Explorez tous les endpoints disponibles

### Via cURL

#### Envoyer un message texte

```bash
curl -X POST "http://localhost:8000/api/whatsapp/messages/text/ACCOUNT_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "33612345678",
    "text": "Test de message",
    "preview_url": true
  }'
```

#### Envoyer un message avec boutons

```bash
curl -X POST "http://localhost:8000/api/whatsapp/messages/interactive/buttons/ACCOUNT_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "33612345678",
    "body_text": "Choisissez une option:",
    "buttons": [
      {"id": "1", "title": "Option 1"},
      {"id": "2", "title": "Option 2"}
    ]
  }'
```

#### Upload un média

```bash
curl -X POST "http://localhost:8000/api/whatsapp/media/upload/ACCOUNT_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@/path/to/image.jpg"
```

#### Récupérer le profil business

```bash
curl -X GET "http://localhost:8000/api/whatsapp/profile/ACCOUNT_ID" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## 📋 Checklist de Configuration

- [ ] Migration SQL appliquée
- [ ] `META_APP_ID` et `META_APP_SECRET` ajoutés au `.env`
- [ ] `waba_id` configuré dans `whatsapp_accounts` (pour templates)
- [ ] `business_id` configuré dans `whatsapp_accounts` (pour WABA management)
- [ ] Application redémarrée
- [ ] Test d'un endpoint simple réussi

---

## 🎯 Fonctionnalités Disponibles

### ✅ Messages (tous types)
- ✉️ Texte simple
- 🖼️ Images, vidéos, documents, audio
- 📋 Templates (après approbation Meta)
- 🔘 Boutons interactifs (max 3)
- 📜 Listes déroulantes

### ✅ Médias
- 📤 Upload de fichiers
- 📥 Téléchargement
- 🗑️ Suppression
- ℹ️ Informations sur un média

### ✅ Numéros de téléphone
- 📋 Liste des numéros
- 🔍 Détails d'un numéro
- ✅ Enregistrement / Désenregistrement
- 🔐 Vérification (codes SMS/VOICE)

### ✅ Profil Business
- 👁️ Consultation du profil
- ✏️ Mise à jour (description, email, adresse, etc.)

### ✅ Templates
- 📋 Liste des templates
- ➕ Création (soumis à review Meta)
- 🗑️ Suppression

### ✅ Webhooks
- ✅ Vérification automatique
- 📨 Réception des événements
- 🔔 Abonnement / Désabonnement

### ✅ WABA Management
- 🏢 Détails du WABA
- 📋 Liste des WABAs (owned/client)
- 🔔 Gestion des webhooks

### ✅ Utilitaires
- 🔍 Debug de token
- 🎫 Génération d'app token
- ☎️ Validation de numéros

---

## 🆘 Problèmes Fréquents

### "account_not_configured"
→ Vérifiez que `phone_number_id` et `access_token` sont présents dans `whatsapp_accounts`.

### "waba_id not configured"
→ Ajoutez le WABA ID dans la base de données (voir étape 3).

### "Webhook verification failed"
→ Vérifiez que `WHATSAPP_VERIFY_TOKEN` dans `.env` correspond à celui dans Meta Dashboard.

### "403 Forbidden" sur les routes
→ Vérifiez que votre JWT token est valide et que vous avez les permissions nécessaires.

### Template rejeté par Meta
→ Assurez-vous que le contenu respecte les [politiques Meta](https://www.facebook.com/business/help/896873687365001).

---

## 📚 Documentation Complète

Pour plus de détails, consultez [WHATSAPP_API_COMPLETE_GUIDE.md](./WHATSAPP_API_COMPLETE_GUIDE.md)

---

## 🎉 Prêt à l'emploi !

Tous les endpoints sont maintenant disponibles et documentés dans Swagger UI.

Bonne utilisation ! 🚀

