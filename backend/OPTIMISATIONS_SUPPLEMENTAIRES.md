# 🚀 Optimisations supplémentaires appliquées

## ✅ Ce qui a été fait

### 1. Cache pour `/auth/me` ⚡ (Gain attendu: -80% latence)

**Problème:** `/auth/me` prenait 1.01s et est appelé à **chaque requête authentifiée**.

**Solution appliquée:**
- Cache de l'utilisateur authentifié avec TTL de 2 minutes
- Basé sur le hash du token JWT
- Première requête: 1.01s, requêtes suivantes: ~10ms

**Impact attendu:**
- `/auth/me`: 1.01s → **~50ms en moyenne**
- **Toutes les routes authentifiées seront plus rapides** (car elles appellent get_current_user)

---

### 2. Cache pour `get_conversation_by_id()` (Gain: -70%)

**Problème:** Appelé plusieurs fois par requête, toujours en DB.

**Solution appliquée:**
- Cache avec TTL de 1 minute
- Les conversations changent rarement

**Impact attendu:**
- Première lecture: ~200ms, suivantes: ~10ms

---

## 🎯 Optimisations à faire manuellement (SQL)

### 3. Ajouter des index Supabase

Si vous avez accès à Supabase, exécutez ces requêtes SQL pour accélérer les queries :

```sql
-- Index pour les conversations (optimise list_conversations)
CREATE INDEX IF NOT EXISTS idx_conversations_account_updated 
ON conversations(account_id, updated_at DESC);

-- Index pour les messages (optimise get_messages)
CREATE INDEX IF NOT EXISTS idx_messages_conversation_timestamp 
ON messages(conversation_id, timestamp DESC);

-- Index pour les contacts
CREATE INDEX IF NOT EXISTS idx_conversations_contact 
ON conversations(contact_id);

-- Index pour les accounts (si pas déjà présent)
CREATE INDEX IF NOT EXISTS idx_accounts_phone_number_id 
ON whatsapp_accounts(phone_number_id);

-- Index pour les app_users
CREATE INDEX IF NOT EXISTS idx_app_users_user_id 
ON app_users(user_id);

-- Index pour les role assignments
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id 
ON app_user_roles(user_id);
```

**Impact attendu:**
- `/conversations`: 798ms → **~200-300ms**
- `/messages/{conversation_id}`: 873ms → **~200-300ms**

---

### 4. Optimiser les requêtes admin (si nécessaire)

Si les routes admin restent lentes après les caches, vous pouvez :

**Option A - Dénormaliser (recommandé) :**
```sql
-- Ajouter une colonne JSON pour éviter les JOINs
ALTER TABLE app_users ADD COLUMN roles_cache JSONB;

-- Trigger pour maintenir à jour
CREATE OR REPLACE FUNCTION update_user_roles_cache()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE app_users 
  SET roles_cache = (
    SELECT json_agg(json_build_object(
      'role_id', r.role_id,
      'account_id', r.account_id,
      'role_name', ar.name
    ))
    FROM app_user_roles r
    JOIN app_roles ar ON ar.id = r.role_id
    WHERE r.user_id = NEW.user_id
  )
  WHERE user_id = NEW.user_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_user_roles_cache
AFTER INSERT OR UPDATE OR DELETE ON app_user_roles
FOR EACH ROW EXECUTE FUNCTION update_user_roles_cache();
```

**Option B - Utiliser des vues matérialisées :**
```sql
CREATE MATERIALIZED VIEW mv_users_with_roles AS
SELECT 
  u.*,
  json_agg(json_build_object(
    'role_id', r.role_id,
    'account_id', r.account_id,
    'role_name', ar.name
  )) as roles
FROM app_users u
LEFT JOIN app_user_roles r ON r.user_id = u.user_id
LEFT JOIN app_roles ar ON ar.id = r.role_id
GROUP BY u.user_id;

CREATE UNIQUE INDEX ON mv_users_with_roles(user_id);

-- Rafraîchir toutes les 5 minutes
-- (ou créer un trigger pour rafraîchir après chaque modification)
```

---

## 📊 Impact global attendu

| Endpoint | Avant | Après | Gain |
|----------|-------|-------|------|
| `/auth/me` | 1010ms | **~50ms** | **-95%** ✅ |
| `/accounts` | 1120ms | **~400ms** | **-64%** 🔄 |
| `/admin/*` | 1220ms | **~500ms** | **-59%** 🔄 |
| `/conversations` | 798ms | **~250ms** | **-69%** 🔄 |
| `/messages/{id}` | 873ms | **~300ms** | **-66%** 🔄 |
| `/bot/profile` | 679ms | **~100ms** | **-85%** ✅ |

**Légende:**
- ✅ Cache appliqué automatiquement
- 🔄 Nécessite les index SQL

---

## 🔧 Autres optimisations possibles (optionnel)

### 5. Migrer vers asyncpg (long terme)

Le client Supabase Python est synchrone. Pour de meilleures performances :

```python
# Installer asyncpg
pip install asyncpg

# Utiliser asyncpg directement
import asyncpg

pool = await asyncpg.create_pool(
    host='db.xxx.supabase.co',
    port=5432,
    user='postgres',
    password='...',
    database='postgres',
    min_size=5,
    max_size=20
)

async def get_conversation_by_id(conversation_id: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT * FROM conversations WHERE id = $1 LIMIT 1',
            conversation_id
        )
        return dict(row) if row else None
```

**Avantages:**
- Vraiment async (pas de threadpool)
- Connection pooling natif
- Plus rapide (~30% de gain)

**Inconvénients:**
- Nécessite de réécrire toutes les requêtes
- Perte du query builder Supabase
- Plus de code à maintenir

---

### 6. Ajouter un cache Redis (production)

Pour un cache partagé entre instances :

```python
# requirements.txt
redis>=4.5.0
aioredis>=2.0.1

# backend/app/core/redis_cache.py
import aioredis
import json

redis = await aioredis.from_url("redis://localhost:6379")

async def get_cached(key: str):
    value = await redis.get(key)
    return json.loads(value) if value else None

async def set_cached(key: str, value: any, ttl: int):
    await redis.setex(key, ttl, json.dumps(value))
```

**Avantages:**
- Cache partagé entre instances
- Persistant (survit aux redémarrages)
- Très rapide (~1ms)

---

### 7. Pagination cursor-based (au lieu de offset)

Pour `/conversations` et `/messages`, utiliser la pagination par cursor :

**Avant (offset):**
```sql
SELECT * FROM conversations 
WHERE account_id = $1 
ORDER BY updated_at DESC 
LIMIT 50 OFFSET 100;  -- Lent sur grandes tables
```

**Après (cursor):**
```sql
SELECT * FROM conversations 
WHERE account_id = $1 
  AND updated_at < $2  -- Cursor
ORDER BY updated_at DESC 
LIMIT 50;  -- Rapide avec index
```

**Impact:** 50-70% plus rapide sur les grandes tables.

---

## 🎯 Plan d'action recommandé

### Immédiat (fait automatiquement) ✅
1. Cache `/auth/me` ← **Déjà appliqué**
2. Cache `get_conversation_by_id` ← **Déjà appliqué**

### Court terme (5 min) 🔴
3. Ajouter les index SQL dans Supabase ← **À faire maintenant**

### Moyen terme (si besoin) 🟡
4. Optimiser les routes admin si elles restent lentes
5. Vérifier les autres requêtes lentes dans Grafana

### Long terme (optionnel) 🟢
6. Migrer vers asyncpg
7. Ajouter Redis en production
8. Optimiser la pagination

---

## ✅ Comment tester

```powershell
# 1. Redémarrer
docker-compose restart backend

# 2. Vérifier les logs (chercher "Cache HIT")
docker-compose logs -f backend | Select-String -Pattern "Cache"

# 3. Tester /auth/me (devrait être beaucoup plus rapide)
# Première requête: ~1s, suivantes: ~50ms
curl http://localhost:8000/auth/me -H "Authorization: Bearer YOUR_TOKEN"

# 4. Attendre 10-15 minutes et vérifier Grafana
# - /auth/me devrait passer de 1.01s à ~100-200ms en moyenne
# - Toutes les autres routes devraient être plus rapides aussi
```

---

## 📈 Résultats attendus dans Grafana

**Après redémarrage (avec cache auth + conversation) :**
- P50 global: 800ms → **~300ms** (-62%)
- P95 global: 1000ms → **~500ms** (-50%)
- /auth/me: 1010ms → **~100ms** (-90%)

**Après ajout des index SQL :**
- P50 global: ~300ms → **~150ms** (-50%)
- P95 global: ~500ms → **~300ms** (-40%)
- /conversations: 798ms → **~200ms** (-75%)
- /messages: 873ms → **~250ms** (-71%)

---

**Faites les changements SQL et observez les résultats dans 15-20 minutes ! 🚀**

