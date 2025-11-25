# 🚀 Guide d'implémentation des améliorations

Ce guide vous accompagne étape par étape pour appliquer les corrections aux erreurs 5xx intermittentes.

## 📋 Prérequis

1. Sauvegarder votre code actuel
2. Tester en environnement de développement d'abord
3. Avoir accès aux logs pour vérifier l'impact

---

## 🔴 PHASE 1: Fixes urgents (1-2 heures)

### Étape 1.1: Installer les dépendances

```bash
cd backend
pip install -r requirements.txt
```

Vérifie que `tenacity` et `cachetools` sont bien installés.

### Étape 1.2: Activer le health check

Le health check est déjà configuré ! Il suffit de redémarrer l'application.

**Test:**
```bash
curl http://localhost:8000/health
```

Vous devriez voir le statut de toutes les dépendances.

### Étape 1.3: Améliorer bot_service

**Option A - Remplacement complet (recommandé):**

```bash
# Sauvegarder l'ancien
mv backend/app/services/bot_service.py backend/app/services/bot_service_old.py

# Activer la nouvelle version
mv backend/app/services/bot_service_improved.py backend/app/services/bot_service.py
```

**Option B - Modifications manuelles:**

Si vous préférez garder votre version actuelle et appliquer les changements progressivement, voici les modifications critiques:

#### 1. Réduire le timeout Gemini (ligne 183 de bot_service.py)

**Avant:**
```python
async with httpx.AsyncClient(timeout=45) as client:
    response = await client.post(...)
```

**Après:**
```python
from app.core.http_client import get_http_client

client = await get_http_client()
timeout = httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=5.0)
response = await client.post(..., timeout=timeout)
```

#### 2. Ajouter le circuit breaker (au début de generate_bot_reply)

**Ajouter après la ligne 103:**
```python
from app.core.circuit_breaker import gemini_circuit_breaker, CircuitBreakerOpenError

# Dans generate_bot_reply(), envelopper l'appel Gemini:
try:
    data = await gemini_circuit_breaker.call_async(
        _call_gemini_api,  # Créer cette fonction (voir bot_service_improved.py)
        endpoint,
        payload,
        conversation_id
    )
except CircuitBreakerOpenError:
    logger.error("Circuit breaker OPEN for Gemini")
    return None
```

#### 3. Ajouter le cache pour get_bot_profile (ligne 45)

**Ajouter avant la définition de la fonction:**
```python
from app.core.cache import cached

@cached(ttl_seconds=300, key_prefix="bot_profile")
async def get_bot_profile(account_id: str) -> Dict[str, Any]:
    # ... code existant
```

### Étape 1.4: Améliorer message_service

#### 1. Réduire les timeouts WhatsApp (lignes 376 et 499)

**Avant:**
```python
async with httpx.AsyncClient(timeout=20) as client:
```

**Après:**
```python
from app.core.http_client import get_http_client

client = await get_http_client()
# Le timeout est déjà optimisé dans get_http_client()
```

#### 2. Améliorer fetch_message_media_content (ligne 525)

**Avant:**
```python
async with httpx.AsyncClient(timeout=60) as client:
```

**Après:**
```python
from app.core.http_client import get_http_client_for_media

client = await get_http_client_for_media()
# Timeout optimisé pour les gros fichiers
```

#### 3. Ajouter retry sur send_message (ligne 376)

**Envelopper l'appel HTTP dans send_message:**
```python
from app.core.retry import retry_on_network_error

@retry_on_network_error(max_attempts=3)
async def _send_to_whatsapp(phone_id: str, token: str, body: dict):
    client = await get_http_client()
    response = await client.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    return response

# Dans send_message():
response = await _send_to_whatsapp(phone_id, token, body)
```

### Étape 1.5: Améliorer auth.py

**Ligne 23 - Réduire le timeout:**

**Avant:**
```python
async with httpx.AsyncClient(timeout=10) as client:
```

**Après:**
```python
from app.core.http_client import get_http_client

client = await get_http_client()
timeout = httpx.Timeout(connect=3.0, read=5.0, write=3.0, pool=3.0)
response = await client.get(url, headers=headers, timeout=timeout)
```

### Étape 1.6: Redémarrer et tester

```bash
# Arrêter l'app
# Ctrl+C ou docker-compose down

# Redémarrer
docker-compose up --build

# Tester le health check
curl http://localhost:8000/health

# Tester l'API
curl http://localhost:8000/auth/me -H "Authorization: Bearer YOUR_TOKEN"
```

**Vérifier les logs:**
- Les timeouts doivent être plus courts
- Les retries doivent apparaître en cas d'erreur réseau
- Le cache doit montrer "Cache HIT" / "Cache MISS"

---

## 🟠 PHASE 2: Améliorations importantes (2-3 heures)

### Étape 2.1: Ajouter timeout sur Supabase

**Modifier `backend/app/core/db.py`:**

**Avant:**
```python
async def supabase_execute(query_builder):
    return await run_in_threadpool(query_builder.execute)
```

**Après:**
```python
import asyncio
from fastapi import HTTPException

async def supabase_execute(query_builder, timeout: float = 10.0):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(query_builder.execute),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error("Supabase query timeout after %ss", timeout)
        raise HTTPException(status_code=504, detail="database_timeout")
```

### Étape 2.2: Paralléliser les appels DB

**Exemple dans `routes_messages.py` ligne 34:**

**Avant:**
```python
message = await get_message_by_id(message_id)
conversation = await get_conversation_by_id(message["conversation_id"])
account = await get_account_by_id(conversation["account_id"])
```

**Après:**
```python
import asyncio

message = await get_message_by_id(message_id)
if not message:
    raise HTTPException(status_code=404, detail="message_not_found")

# Paralléliser les 2 appels suivants
conversation, account = await asyncio.gather(
    get_conversation_by_id(message["conversation_id"]),
    get_account_by_id(message["account_id"])  # Si on a l'ID directement
)
```

### Étape 2.3: Améliorer la gestion d'erreurs

**Dans tous les services qui appellent des APIs externes, ajouter:**

```python
try:
    response = await client.post(...)
    response.raise_for_status()
except httpx.TimeoutException:
    logger.error("Timeout calling external API")
    raise HTTPException(status_code=504, detail="external_api_timeout")
except httpx.HTTPStatusError as exc:
    if exc.response.status_code >= 500:
        logger.error("External API server error: %s", exc.response.text)
        raise HTTPException(status_code=502, detail="external_api_unavailable")
    else:
        logger.warning("External API client error: %s", exc.response.text)
        raise HTTPException(status_code=400, detail="external_api_error")
except httpx.NetworkError as exc:
    logger.error("Network error calling external API: %s", exc)
    raise HTTPException(status_code=503, detail="network_error")
```

---

## 🟢 PHASE 3: Optimisations (optionnel, 1-2 heures)

### Étape 3.1: Ajouter cache sur account_service

**Dans `backend/app/services/account_service.py`:**

```python
from app.core.cache import cached

@cached(ttl_seconds=300, key_prefix="account")
async def get_account_by_id(account_id: str):
    # ... code existant
```

**Important:** Invalider le cache lors des modifications:

```python
from app.core.cache import invalidate_cache_pattern

async def update_account(account_id: str, data: dict):
    # ... update logic
    await invalidate_cache_pattern(f"account:{account_id}")
```

### Étape 3.2: Monitoring du circuit breaker

**Ajouter un endpoint admin pour voir l'état:**

```python
# Dans routes_admin.py ou routes_health.py
from app.core.circuit_breaker import get_all_circuit_breakers

@router.get("/admin/circuit-breakers")
async def get_circuit_breakers_status(current_user: CurrentUser = Depends(get_current_user)):
    current_user.require(PermissionCodes.ADMIN)
    return get_all_circuit_breakers()
```

### Étape 3.3: Grafana dashboard pour les nouveaux metrics

**Ajouter dans Grafana:**

1. **Health check status**:
   ```promql
   up{job="whatsapp_inbox_api"}
   ```

2. **Circuit breaker state**:
   - Via logs ou créer des métriques custom

3. **Cache hit ratio**:
   - Implémenter un counter Prometheus dans `cache.py`

---

## 🧪 Tests après implémentation

### Test 1: Vérifier les timeouts réduits

**Avant:**
- Gemini: 45s
- WhatsApp: 20s
- Auth: 10s

**Après:**
- Gemini: 15s max
- WhatsApp: 10s max
- Auth: 5s max

**Comment tester:**
```python
# Dans un test Python
import time
start = time.time()
try:
    # Appeler l'endpoint qui appelle Gemini
    response = requests.post("/bot/reply", ...)
except:
    pass
duration = time.time() - start
assert duration < 20  # Ne devrait plus prendre 45s
```

### Test 2: Vérifier le circuit breaker

**Simulation de panne Gemini:**

1. Désactiver temporairement `GEMINI_API_KEY` ou mettre une mauvaise clé
2. Envoyer 5 requêtes qui déclenchent le bot
3. Vérifier les logs: "Circuit breaker OPEN"
4. Les requêtes suivantes doivent échouer rapidement (< 1s) sans appeler Gemini

**Vérification:**
```bash
curl http://localhost:8000/admin/circuit-breakers
# Devrait montrer "state": "open" pour Gemini
```

### Test 3: Vérifier le cache

**Logs à chercher:**
```
Cache MISS: bot_profile:account_123
Cache SET: bot_profile:account_123 (TTL=300s)
Cache HIT: bot_profile:account_123
```

**Test manuel:**
```bash
# Premier appel (cache miss)
time curl http://localhost:8000/bot/profile?account_id=123

# Deuxième appel immédiat (cache hit, devrait être plus rapide)
time curl http://localhost:8000/bot/profile?account_id=123
```

### Test 4: Vérifier les retries

**Simulation:**
- Couper Internet brièvement pendant un appel
- Les logs doivent montrer: "Retrying... attempt 2/3"

---

## 📊 Métriques à surveiller après déploiement

### Dans Grafana:

1. **Latence P95 par endpoint**
   - Devrait baisser de 30-50%

2. **Taux d'erreur 5xx**
   - Devrait baisser significativement

3. **Nombre de retries**
   - Nouveau metric à ajouter

4. **Circuit breaker openings**
   - À monitorer (ne devrait s'ouvrir qu'en cas de vraie panne)

### Requêtes PromQL utiles:

```promql
# Latence P95
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Taux d'erreur
rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# Durée moyenne par route
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

---

## 🚨 Rollback en cas de problème

Si les changements causent des problèmes:

### Rollback rapide (Option A):

```bash
# Restaurer l'ancien bot_service
mv backend/app/services/bot_service_old.py backend/app/services/bot_service.py

# Redémarrer
docker-compose restart backend
```

### Rollback complet (Option B):

```bash
git stash  # Sauvegarder les changements non committés
git checkout HEAD~1  # Revenir à la version précédente
docker-compose up --build
```

---

## ✅ Checklist finale

Après avoir tout implémenté, vérifier:

- [ ] Les nouveaux modules sont dans `backend/app/core/`
- [ ] `requirements.txt` contient `tenacity` et `cachetools`
- [ ] Le health check répond sur `/health`
- [ ] Les logs montrent les timeouts réduits
- [ ] Le cache fonctionne (logs "Cache HIT/MISS")
- [ ] Les retries fonctionnent (logs "Retrying...")
- [ ] Le circuit breaker s'affiche dans `/admin/circuit-breakers`
- [ ] Les tests manuels passent
- [ ] Grafana montre une amélioration de la latence
- [ ] Le taux d'erreur 5xx a baissé

---

## 📞 Support

Si vous rencontrez des problèmes:

1. Vérifier les logs: `docker-compose logs -f backend`
2. Tester le health check: `curl http://localhost:8000/health`
3. Vérifier les dépendances: `pip list | grep -E "tenacity|httpx"`

Les changements sont **backward compatible** : si un module n'est pas importé, l'ancien code continue de fonctionner.

