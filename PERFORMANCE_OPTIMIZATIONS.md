# Optimisations de Performance - WhatsApp Inbox

Basé sur l'analyse des dashboards de monitoring, voici les optimisations prioritaires pour améliorer les performances de l'application.

## 🎯 Endpoints Critiques à Optimiser

### 1. GET /messages/media/{message_id} - **2.75s** (le plus lent)

**Problème identifié :**
- 2 requêtes HTTP séquentielles à l'API WhatsApp (métadonnées + téléchargement)
- Pas de cache sur les métadonnées
- Pas de storage_url dans certains cas → fallback lent

**Optimisations proposées :**

#### A. Cache des métadonnées média (priorité: HAUTE)
```python
# Dans fetch_message_media_content
# Ajouter un cache Redis/mémoire pour les métadonnées (media_id -> meta_json)
# TTL: 1 heure (métadonnées WhatsApp ne changent pas)
```

#### B. Vérification storage_url en premier (déjà fait ✅)
- Rediriger immédiatement si storage_url existe (ligne 88-91)
- ✅ Déjà optimisé

#### C. Téléchargement asynchrone avec retry
- Si pas de storage_url, retourner 202 Accepted immédiatement
- Traiter le téléchargement en arrière-plan
- Client peut poller le statut ou utiliser webhook

**Impact attendu :** Réduction de ~2.5s à ~0.3s (80% d'amélioration)

---

### 2. POST /messages/send-with-auto-template - **2.51s**

**Problème identifié :**
- Requêtes DB séquentielles multiples :
  1. `get_conversation_by_id`
  2. `is_within_free_window` → requête DB séparée
  3. `find_or_create_template` → plusieurs requêtes DB
  4. Insertion message

**Optimisations proposées :**

#### A. Optimiser `is_within_free_window` avec un index (priorité: HAUTE)
```sql
-- Ajouter un index composite pour accélérer la requête
CREATE INDEX IF NOT EXISTS idx_messages_conversation_direction_timestamp 
ON messages(conversation_id, direction, timestamp DESC) 
WHERE status != 'failed' OR status IS NULL;
```

#### B. Requête DB combinée (priorité: MOYENNE)
- Combiner `get_conversation_by_id` et `is_within_free_window` en une seule requête
- Utiliser un JOIN pour récupérer conversation + dernier message entrant

#### C. Cache de la fenêtre gratuite (priorité: MOYENNE)
- Mettre en cache `is_free` avec TTL court (5 minutes)
- Invalider lors d'un nouveau message entrant
- Clé: `free_window:{conversation_id}`

**Impact attendu :** Réduction de ~2.5s à ~1.0s (60% d'amélioration)

---

### 3. GET /contacts/{contact_id}/whatsapp-info - **1.74s, 100% erreurs 5xx**

**Problème identifié :**
- L'endpoint WhatsApp `/contacts` retourne systématiquement des erreurs 5xx
- Pas de gestion d'erreur robuste
- Pas de fallback

**Optimisations proposées :**

#### A. Améliorer la gestion d'erreur (priorité: HAUTE)
```python
# Dans get_contact_info
# Retourner un code 5xx seulement si c'est une erreur critique
# Pour les erreurs WhatsApp API, retourner 503 Service Unavailable avec retry-after
```

#### B. Ajouter un fallback avec données existantes (priorité: HAUTE)
- Si l'appel WhatsApp échoue, retourner les données déjà stockées dans la DB
- Ne pas lever d'exception si les données existent déjà

#### C. Désactiver temporairement l'endpoint si trop d'erreurs (priorité: MOYENNE)
- Ajouter un circuit breaker pour éviter les appels inutiles
- Retourner les données en cache/local si disponible

**Impact attendu :** Réduction des erreurs 5xx de 100% à <10%

---

### 4. POST /messages/check-media/{conversation_id} - **792 requêtes/24h**

**Problème identifié :**
- Appelé très fréquemment (33 fois/heure en moyenne)
- Démarre un traitement asynchrone mais la requête est acceptée immédiatement

**Optimisations proposées :**

#### A. Debounce côté frontend (priorité: MOYENNE)
```javascript
// Dans ChatWindow.jsx
// Ne pas appeler check-media si déjà appelé il y a moins de 5 minutes
// Utiliser un flag local
```

#### B. Cache côté backend (priorité: MOYENNE)
- Ne pas relancer le traitement si déjà en cours (< 5 minutes)
- Clé: `check_media:{conversation_id}` avec TTL 5 min

**Impact attendu :** Réduction de ~792 à ~200 requêtes/jour (75% de réduction)

---

### 5. POST /webhook/whatsapp - **816 requêtes/24h** (volume élevé)

**Problème identifié :**
- Traitement synchrone qui peut être lent
- WhatsApp peut timeout si la réponse est trop longue

**Optimisations proposées :**

#### A. Réponse HTTP immédiate (priorité: HAUTE)
```python
# Dans routes_webhook.py
# Retourner 200 OK immédiatement
# Traiter handle_incoming_message en arrière-plan (background task)
# Utiliser asyncio.create_task() pour ne pas bloquer
```

#### B. Optimiser le traitement des webhooks (priorité: MOYENNE)
- Traiter les messages en parallèle (grouper par account_id)
- Éviter les requêtes DB redondantes (cache des accounts)

**Impact attendu :** Réduction du temps de réponse de ~1.5s à ~50ms (97% d'amélioration)

---

## 📊 Optimisations Globales

### 1. Ajouter des index de base de données (priorité: HAUTE)

```sql
-- Pour is_within_free_window
CREATE INDEX IF NOT EXISTS idx_messages_conversation_direction_timestamp 
ON messages(conversation_id, direction, timestamp DESC) 
WHERE status != 'failed' OR status IS NULL;

-- Pour get_conversation_by_id (si pas déjà fait)
CREATE INDEX IF NOT EXISTS idx_conversations_id ON conversations(id);

-- Pour les requêtes de messages fréquentes
CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp 
ON messages(conversation_id, timestamp DESC);
```

### 2. Implémenter un système de cache Redis/mémoire (priorité: MOYENNE)

**Éléments à mettre en cache :**
- Métadonnées média (1 heure)
- Statut fenêtre gratuite (5 minutes)
- Accounts (30 minutes)
- Conversations fréquentes (10 minutes)

### 3. Optimiser les requêtes DB fréquentes (priorité: MOYENNE)

- Éviter les N+1 queries
- Utiliser `.select()` pour limiter les champs récupérés
- Utiliser des JOINs au lieu de requêtes multiples

### 4. Ajouter de la pagination et des limites (priorité: BASSE)

- Limiter les résultats par défaut
- Ajouter des paramètres `limit` et `offset` partout

---

## 🚀 Plan d'Implémentation

### Phase 1 - Quick Wins (1-2 jours)
1. ✅ Réponse HTTP immédiate pour `/webhook/whatsapp`
2. ✅ Cache de `is_within_free_window` (5 min)
3. ✅ Améliorer gestion d'erreur `/contacts/whatsapp-info`
4. ✅ Ajouter index DB pour `is_within_free_window`

### Phase 2 - Optimisations Moyennes (3-5 jours)
1. Cache métadonnées média (Redis/mémoire)
2. Debounce côté frontend pour `check-media`
3. Requête combinée pour `send-with-auto-template`
4. Circuit breaker pour endpoints WhatsApp API

### Phase 3 - Optimisations Avancées (1 semaine+)
1. Cache Redis complet avec invalidation intelligente
2. Traitement parallèle des webhooks
3. Monitoring et alertes de performance
4. Load testing et tuning final

---

## 📈 Métriques à Surveiller

Après implémentation, surveiller :
- **GET /messages/media/{message_id}** : Objectif < 500ms (P95)
- **POST /messages/send-with-auto-template** : Objectif < 1s (P95)
- **GET /contacts/{contact_id}/whatsapp-info** : Objectif < 5% erreurs 5xx
- **POST /messages/check-media** : Objectif < 300 requêtes/jour
- **POST /webhook/whatsapp** : Objectif < 100ms (P95)

---

## ⚠️ Notes Importantes

- Tester chaque optimisation dans un environnement de staging
- Monitorer les métriques après chaque changement
- Implémenter progressivement (pas tout en même temps)
- Documenter les changements dans le code

---

## 🧪 Tests de performance (Locust)

Un fichier `backend/locustfile.py` permet d'exécuter des tests de charge.

```bash
cd backend
pip install locust

# Tests health only (sans auth)
locust -f locustfile.py --host=http://localhost:8000

# Tests avec auth (endpoints protégés)
$env:LOCUST_AUTH_TOKEN = "eyJ..."   # Windows
$env:LOCUST_ACCOUNT_ID = "uuid"
$env:LOCUST_CONVERSATION_ID = "uuid"
locust -f locustfile.py --host=http://localhost:8000

# Mode headless (10 users, 2/s, 60 secondes)
locust -f locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 -t 60s
```

Ouvrir http://localhost:8089 pour l'interface Locust.

