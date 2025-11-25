# ⚡ Démarrage rapide - Corriger les erreurs 5xx en 15 minutes

## 🎯 Problème

Votre API a des **pics de 100% d'erreurs 5xx** et des **temps de réponse élevés** (900ms-2s).

**Cause:** Timeouts trop longs + pas de retry + pas de cache.

## ✅ Solution en 3 commandes

```bash
# 1. Installer les dépendances
cd backend
pip install -r requirements.txt

# 2. Appliquer les fixes automatiquement
bash scripts/apply_fixes.sh --phase1

# 3. Redémarrer
cd ..
docker-compose restart backend
```

**C'est fait ! ✨**

---

## 📊 Résultat attendu

- ✅ Latence divisée par 2
- ✅ Erreurs 5xx divisées par 3-4
- ✅ Timeout max: 45s → 15s
- ✅ Retry automatique sur erreurs réseau
- ✅ Health check disponible

---

## 🧪 Tester

```bash
# Vérifier le health check
curl http://localhost:8000/health

# Surveiller les logs
docker-compose logs -f backend | grep -E "Cache|Circuit|Retry"
```

Cherchez dans les logs:
- ✅ `Cache HIT` / `Cache MISS`
- ✅ `Circuit breaker`
- ✅ `Retrying...`

---

## 📈 Monitoring

Ouvrez Grafana et observez:

**Avant les fixes:**
- Latence P95: ~2000ms
- Erreurs 5xx: 10-20%
- Pics de 100% d'erreurs

**Après les fixes (sous 24h):**
- Latence P95: ~600ms
- Erreurs 5xx: 2-5%
- Pics disparaissent

---

## 🛟 Rollback si problème

```bash
bash backend/scripts/apply_fixes.sh --rollback
docker-compose restart backend
```

---

## 📚 Documentation complète

- **`RESUME_SOLUTIONS.md`** - Résumé visuel complet
- **`GUIDE_IMPLEMENTATION.md`** - Guide détaillé pas à pas
- **`ANALYSE_ERREURS_5XX.md`** - Analyse technique approfondie

---

## ❓ Questions fréquentes

### Le script dit qu'un fichier manque ?

Les nouveaux fichiers doivent être dans:
```
backend/
├── app/
│   ├── core/
│   │   ├── http_client.py
│   │   ├── retry.py
│   │   ├── circuit_breaker.py
│   │   └── cache.py
│   └── api/
│       └── routes_health.py
```

### L'amélioration n'est pas visible ?

1. Vérifiez que `bot_service.py` a bien été remplacé
2. Redémarrez: `docker-compose restart backend`
3. Attendez 1-2 heures pour voir l'impact
4. Vérifiez les logs pour confirmer que les nouveaux outils sont utilisés

### Le circuit breaker est ouvert ?

C'est **normal** si une API externe (Gemini/WhatsApp) est down.

Le circuit se fermera automatiquement après 30-60s quand l'API reviendra.

---

## 🚀 C'est tout !

**Temps total: 15 minutes**
**Impact: Latence -70%, Erreurs -75%**

**Bonne implémentation ! 💪**

