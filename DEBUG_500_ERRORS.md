# 🚨 Debug : Erreurs 500 sur les Routes API

Date: 26 Novembre 2025

## ❌ Erreurs Détectées

### 1. GET /api/conversations?account_id=xxx → 500
```
GET http://192.168.1.165:5173/api/conversations?account_id=122fb91e-660a-461d-ae7b-d0c310e36873 500 (Internal Server Error)
```

**Fichier source:** `conversationsApi.js:4`

### 2. GET /api/messages/{conversation_id} → 500
```
GET http://192.168.1.165:5173/api/messages/075ae834-0938-4062-96d9-b7556b3b5495 500 (Internal Server Error)
```

**Fichier source:** `messagesApi.js:3`

---

## 🔍 Causes Possibles

### 1. Problème de Base de Données
- Table manquante
- Colonne manquante
- Contrainte de clé étrangère violée
- Connexion BD perdue

### 2. Problème Backend Python
- Exception non gérée
- Imports manquants
- Variable non définie
- Erreur de logique

### 3. Problème de Configuration
- Variable d'environnement manquante
- Credentials Supabase incorrects
- Token d'authentification invalide

---

## 🛠️ Actions de Débogage

### Étape 1: Vérifier les Logs Backend

```bash
# Si tu utilises Docker
docker logs whatsapp-inbox-backend

# Si tu lances Python directement
# Regarder la console où uvicorn tourne
```

**Ce qu'on cherche:**
```
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File ...
  [DÉTAILS DE L'ERREUR]
```

### Étape 2: Tester les Routes Directement

```bash
# Test route conversations
curl -X GET "http://localhost:8000/api/conversations?account_id=122fb91e-660a-461d-ae7b-d0c310e36873" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Test route messages
curl -X GET "http://localhost:8000/api/messages/075ae834-0938-4062-96d9-b7556b3b5495" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Étape 3: Vérifier la Base de Données

```sql
-- Vérifier que les tables existent
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public';

-- Vérifier la structure de conversations
\d conversations

-- Vérifier la structure de messages
\d messages

-- Tester une requête simple
SELECT * FROM conversations LIMIT 1;
SELECT * FROM messages LIMIT 1;
```

### Étape 4: Vérifier les Migrations

```bash
# Aller dans le dossier backend
cd backend

# Vérifier les migrations Supabase
ls -la ../supabase/migrations/

# S'assurer que toutes les migrations sont appliquées
```

---

## 🔧 Corrections Potentielles

### Si c'est un problème de champ manquant

```sql
-- Exemple: Ajouter une colonne manquante
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS account_id UUID;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS conversation_id UUID;
```

### Si c'est un problème de token d'auth

```javascript
// Vérifier que le token est bien envoyé
// Dans axiosClient.js
console.log("Token d'auth:", localStorage.getItem('token'));
```

### Si c'est un problème Supabase

```python
# Dans backend/app/core/db.py
# Vérifier la connexion
from app.core.config import settings
print(f"Supabase URL: {settings.SUPABASE_URL}")
print(f"Supabase Key présente: {bool(settings.SUPABASE_SERVICE_KEY)}")
```

---

## 📋 Checklist de Vérification

### Backend
- [ ] Le serveur backend tourne (port 8000)
- [ ] Pas d'erreur au démarrage
- [ ] Les variables d'environnement sont définies
- [ ] La connexion Supabase fonctionne

### Base de Données
- [ ] Supabase est accessible
- [ ] Les tables existent
- [ ] Les données de test existent
- [ ] Les migrations sont appliquées

### Frontend
- [ ] Le token d'auth est présent
- [ ] Les requêtes vont vers la bonne URL
- [ ] Le CORS est configuré

---

## 🚀 Solution Temporaire

En attendant de corriger les erreurs 500, ajouter une gestion d'erreur gracieuse :

### Dans MobileInboxPage.jsx

```javascript
const loadConversations = async () => {
  try {
    const response = await getConversations({ account_id: selectedAccount });
    setConversations(response.data || []);
  } catch (error) {
    console.error("Erreur chargement conversations:", error);
    // Afficher un message à l'utilisateur
    setError("Impossible de charger les conversations. Vérifiez votre connexion.");
    // Ne pas crasher l'app
    setConversations([]);
  }
};
```

### Dans MobileChatWindow.jsx

```javascript
const refreshMessages = useCallback(() => {
  if (!conversation?.id) return;
  
  getMessages(conversation.id)
    .then((res) => setMessages(sortMessages(res.data || [])))
    .catch((error) => {
      console.error("Erreur chargement messages:", error);
      // Continuer avec les messages existants
    });
}, [conversation?.id, sortMessages]);
```

---

## 📊 Logs à Collecter

Pour résoudre le problème, j'ai besoin de voir:

1. **Logs Backend Python** (uvicorn/FastAPI)
   ```bash
   # Copier les logs d'erreur complets
   ```

2. **Structure de la base de données**
   ```sql
   -- Résultat de \d conversations
   -- Résultat de \d messages
   ```

3. **Variables d'environnement** (sans les secrets !)
   ```bash
   SUPABASE_URL=https://xxx.supabase.co
   SUPABASE_SERVICE_KEY=[PRÉSENT/ABSENT]
   WHATSAPP_TOKEN=[PRÉSENT/ABSENT]
   ```

---

## 🎯 Prochaine Étape

**URGENT:** Vérifier les logs backend pour identifier la cause exacte des erreurs 500.

Sans les logs backend, je ne peux que deviner. Les erreurs 500 signifient que le serveur backend a crashé en traitant la requête.

---

## 💡 Note sur l'Upload d'Images

Le problème d'upload d'images devrait maintenant être **résolu** avec la correction:

```javascript
// Gère les deux structures de réponse possibles
const mediaId = uploadResult.data?.data?.id || uploadResult.data?.id;
```

Cette ligne essaie d'abord `uploadResult.data.data.id`, et si ça échoue, essaie `uploadResult.data.id`.

---

## ✅ Résumé

| Problème | Status |
|----------|--------|
| Upload images (media_id) | ✅ **CORRIGÉ** |
| GET /conversations | ❌ **500 Error - À déboguer** |
| GET /messages | ❌ **500 Error - À déboguer** |

**Action immédiate requise:** Consulter les logs backend pour les erreurs 500.

