# 🔍 Analyse des erreurs 5xx intermittentes - WhatsApp Inbox

## 📊 Résumé des symptômes

- ✅ **Majorité des requêtes réussies** (80%+ de 2xx)
- ❌ **Pics intermittents de 100% d'erreurs 5xx** (courte durée)
- 📉 **Faible volume** (1-5 requêtes/période)
- ⏱️ **Temps de réponse élevés** (900ms-2s sur certaines routes)
- 💻 **Ressources serveur OK** (CPU < 1%, RAM stable)
- 🎯 **Conclusion** : Les erreurs proviennent de **dépendances externes intermittentes**, pas d'un problème de ressources

---

## 🐛 Problèmes identifiés dans le code

### 1. ⏰ Timeouts incohérents et trop longs

**Localisation** : `backend/app/services/message_service.py`, `backend/app/services/bot_service.py`, `backend/app/core/auth.py`

```python
# Ligne 376 - message_service.py
async with httpx.AsyncClient(timeout=20) as client:  # ⚠️ 20s c'est trop long

# Ligne 183 - bot_service.py  
async with httpx.AsyncClient(timeout=45) as client:  # ⚠️ 45s c'est BEAUCOUP trop long

# Ligne 23 - auth.py
async with httpx.AsyncClient(timeout=10) as client:  # ⚠️ Pourrait être plus court
```

**Impact** :
- Si WhatsApp/Gemini sont lents, une requête peut prendre jusqu'à 45s avant de timeout
- Pendant ce temps, FastAPI attend → latence élevée
- Si le client frontend timeout avant (typiquement 30s), l'utilisateur voit une erreur mais le backend continue

**Solution recommandée** :
```python
# Timeout différencié : connection vs read
timeout = httpx.Timeout(
    connect=5.0,   # 5s max pour établir la connexion
    read=10.0,     # 10s max pour lire la réponse
    write=5.0,     # 5s max pour écrire la requête
    pool=5.0       # 5s max pour obtenir une connexion du pool
)
async with httpx.AsyncClient(timeout=timeout) as client:
    ...
```

---

### 2. 🔄 Absence de retry logic

**Problème** : Aucune tentative de réessai en cas d'échec temporaire des APIs externes.

**Impact** :
- Une micro-coupure réseau = échec immédiat
- Une API externe qui répond 503 temporairement = 5xx pour l'utilisateur

**Solution recommandée** : Ajouter des retries avec backoff exponentiel

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
)
async def call_external_api_with_retry(...):
    ...
```

---

### 3. 🚫 Pas de circuit breaker

**Problème** : Si Gemini API est down ou lente, **toutes** les requêtes qui l'utilisent vont échouer/ralentir.

**Impact** :
- Effet domino : une dépendance en panne affecte tout le système
- Pas de fallback gracieux

**Solution recommandée** : Implémenter un circuit breaker

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def call_gemini_with_circuit_breaker(...):
    # Si 5 échecs consécutifs, le circuit s'ouvre pendant 60s
    # Pendant ce temps, les appels échouent rapidement sans appeler l'API
    ...
```

---

### 4. 🗄️ Client Supabase synchrone + threadpool

**Localisation** : `backend/app/core/db.py`

```python
async def supabase_execute(query_builder):
    """
    Run a Supabase query in a worker thread so FastAPI's event loop stays free.
    """
    return await run_in_threadpool(query_builder.execute)
```

**Problème** :
- Le client Supabase Python est **synchrone**
- Utilise `run_in_threadpool` pour ne pas bloquer l'event loop
- Mais ça crée du overhead et peut causer des ralentissements sous charge

**Impact** :
- Latence accrue sur toutes les requêtes DB
- Potentiel de timeout si Supabase est lent

**Solution recommandée** :
1. **Court terme** : Ajouter un timeout sur les requêtes Supabase
```python
import asyncio

async def supabase_execute(query_builder, timeout: float = 10.0):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(query_builder.execute),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="database_timeout")
```

2. **Long terme** : Migrer vers un client asyncio natif (asyncpg + SQL direct ou httpx direct vers Supabase REST API)

---

### 5. 🔗 Chaînage d'appels externes sans parallélisation

**Exemple** : `backend/app/api/routes_messages.py` ligne 34-50

```python
@router.get("/media/{message_id}")
async def fetch_message_media(...):
    message = await get_message_by_id(message_id)              # DB call 1
    conversation = await get_conversation_by_id(...)           # DB call 2
    account = await get_account_by_id(...)                     # DB call 3
    content, mime_type, filename = await fetch_message_media_content(...)  # External API
```

**Problème** : 4 appels séquentiels → latence cumulée

**Solution** : Paralléliser quand possible avec `asyncio.gather()`

```python
message, conversation = await asyncio.gather(
    get_message_by_id(message_id),
    get_conversation_by_id(message["conversation_id"])
)
```

---

### 6. 🚨 Gestion d'erreurs incomplète

**Exemple** : `backend/app/services/bot_service.py` ligne 190-195

```python
except httpx.HTTPError as exc:
    body = getattr(exc, "response", None)
    detail = body.text if body else str(exc)
    status_code = getattr(body, "status_code", None)
    logger.warning("Gemini API error for %s (status=%s): %s", ...)
    return None  # ⚠️ Retourne None silencieusement
```

**Problème** :
- Les erreurs sont loguées mais retournent `None`
- Le code appelant doit gérer le `None`, sinon → exception plus tard
- Certaines erreurs 4xx/5xx de l'API externe ne remontent pas correctement

**Solution** :
```python
except httpx.TimeoutException:
    logger.error("Gemini timeout for conversation %s", conversation_id)
    raise HTTPException(status_code=504, detail="gemini_timeout")
except httpx.HTTPStatusError as exc:
    if exc.response.status_code >= 500:
        logger.error("Gemini server error: %s", exc.response.text)
        raise HTTPException(status_code=502, detail="gemini_unavailable")
    else:
        logger.warning("Gemini client error: %s", exc.response.text)
        raise HTTPException(status_code=400, detail="gemini_error")
```

---

### 7. 📦 Absence de cache

**Problème** : Certaines données rarement modifiées sont rechargées à chaque requête :
- Bot profiles (`get_bot_profile`)
- Account info (`get_account_by_id`)
- User permissions

**Impact** : Requêtes DB inutiles → latence accrue

**Solution** : Ajouter un cache simple avec TTL

```python
from functools import lru_cache
from datetime import datetime, timedelta

# Cache simple en mémoire (pour commencer)
_cache = {}

async def get_bot_profile_cached(account_id: str):
    cache_key = f"bot_profile:{account_id}"
    cached = _cache.get(cache_key)
    
    if cached and cached["expires_at"] > datetime.now():
        return cached["data"]
    
    profile = await get_bot_profile(account_id)
    _cache[cache_key] = {
        "data": profile,
        "expires_at": datetime.now() + timedelta(minutes=5)
    }
    return profile
```

---

### 8. 🏥 Pas de health checks sur les dépendances

**Problème** : Impossible de savoir si les erreurs viennent de :
- Supabase
- WhatsApp API
- Gemini API

**Solution** : Ajouter un endpoint de health check

```python
# backend/app/main.py
@app.get("/health")
async def health_check():
    health = {
        "status": "ok",
        "dependencies": {}
    }
    
    # Check Supabase
    try:
        await asyncio.wait_for(
            supabase_execute(supabase.table("accounts").select("id").limit(1)),
            timeout=2.0
        )
        health["dependencies"]["supabase"] = "ok"
    except Exception as e:
        health["dependencies"]["supabase"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    # Check WhatsApp API
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("https://graph.facebook.com/v19.0/")
            health["dependencies"]["whatsapp"] = "ok" if resp.is_success else "error"
    except Exception as e:
        health["dependencies"]["whatsapp"] = f"error: {str(e)}"
        health["status"] = "degraded"
    
    # Check Gemini API
    if settings.GEMINI_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}",
                    params={"key": settings.GEMINI_API_KEY}
                )
                health["dependencies"]["gemini"] = "ok" if resp.is_success else "error"
        except Exception as e:
            health["dependencies"]["gemini"] = f"error: {str(e)}"
            health["status"] = "degraded"
    
    return health
```

---

### 9. 🔌 Pas de connection pooling optimisé

**Problème** : Chaque appel crée un nouveau `httpx.AsyncClient`

```python
async with httpx.AsyncClient(timeout=20) as client:  # Nouvelle connexion à chaque fois
    response = await client.post(...)
```

**Impact** : Overhead de création de connexion TCP/TLS à chaque requête

**Solution** : Utiliser un client HTTP partagé

```python
# backend/app/core/http_client.py
import httpx

_http_client: httpx.AsyncClient | None = None

async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            http2=True  # Optionnel : activer HTTP/2
        )
    return _http_client

async def close_http_client():
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None

# Dans main.py
@app.on_event("shutdown")
async def shutdown_event():
    await close_http_client()
```

---

## 🎯 Plan d'action prioritaire

### 🔴 **Urgent** (résout 80% des problèmes)

1. **Réduire les timeouts** (gains immédiats)
   - WhatsApp API : 20s → 10s (connect=3s, read=7s)
   - Gemini API : 45s → 15s (connect=3s, read=12s)
   - Supabase auth : 10s → 5s

2. **Ajouter des retries** sur les appels externes
   - 3 tentatives avec backoff exponentiel
   - Uniquement sur les erreurs réseau/timeout

3. **Implémenter un health check endpoint**
   - Pour identifier rapidement quelle dépendance pose problème

### 🟠 **Important** (améliore la stabilité)

4. **Ajouter un circuit breaker** sur Gemini API
   - Évite l'effet domino quand Gemini est down

5. **Améliorer la gestion d'erreurs**
   - Distinguer 4xx (client) vs 5xx (server)
   - Retourner des codes HTTP appropriés

6. **Ajouter un timeout sur Supabase**
   - Via `asyncio.wait_for` sur `supabase_execute`

### 🟢 **Optimisation** (réduit la latence)

7. **Implémenter un cache** pour bot_profile et accounts
   - TTL de 5 minutes

8. **Connection pooling** HTTP
   - Client httpx partagé au lieu de créer un nouveau client à chaque requête

9. **Paralléliser les appels DB** quand possible
   - `asyncio.gather()` sur les requêtes indépendantes

---

## 📈 Métriques à monitorer après les fixes

1. **Latence P50, P95, P99** par endpoint
2. **Taux d'erreur par dépendance** (Supabase, WhatsApp, Gemini)
3. **Nombre de retries** par API
4. **État du circuit breaker** (ouvert/fermé)
5. **Cache hit ratio**

---

## 🛠️ Outils recommandés à ajouter

```txt
# requirements.txt à compléter
tenacity>=8.0.0        # Retry logic
circuitbreaker>=1.4.0  # Circuit breaker pattern
cachetools>=5.3.0      # Cache simple
```

---

## 📝 Notes supplémentaires

### Pourquoi les pics montrent 100% d'erreurs ?

Avec seulement 1-2 requêtes par période :
- Si 1 requête arrive pendant qu'une dépendance est lente/down → 100% d'erreurs
- 30 secondes plus tard, la dépendance répond à nouveau → 100% de succès

C'est un **effet de volume faible** : statistiquement normal, mais visuellement dramatique sur les graphes.

### Recommandation finale

**Commencez par les fixes "Urgent"** (points 1-3). Ils sont simples à implémenter et résoudront la majorité des problèmes. Vous devriez voir :
- ⬇️ Réduction de la latence moyenne de ~50%
- ⬇️ Disparition des timeouts > 30s
- ⬇️ Meilleure résilience face aux micro-coupures

Puis implémentez progressivement les autres optimisations.

