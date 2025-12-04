# 🧪 Guide des Tests Automatiques

Ce projet utilise des tests automatiques qui se déclenchent à chaque `git push` pour éviter de déployer du code cassé.

## 📋 Types de Tests

### 1. Tests Backend
- ✅ **Syntaxe Python** : Vérifie que tous les fichiers Python sont valides
- ✅ **Imports** : Vérifie que tous les imports fonctionnent
- ✅ **Configuration** : Vérifie que les variables d'environnement sont correctement chargées
- ✅ **Routes critiques** : Vérifie que les routes principales peuvent être importées

### 2. Tests Frontend
- ✅ **Syntaxe JavaScript/JSX** : Vérifie la validité du code
- ✅ **package.json** : Vérifie que le fichier est valide
- ✅ **Build** : Tente de construire l'application (si configuré)

### 3. Validation de Configuration
- ✅ **Caddyfile** : Vérifie que `BACKEND_URL` est présent et que les routes critiques existent
- ✅ **docker-compose.prod.yml** : Vérifie que tous les services sont configurés
- ✅ **Workflows GitHub** : Détecte les workflows en double

### 4. Tests de Déploiement
- ✅ **Scripts de déploiement** : Vérifie que les scripts sont valides
- ✅ **Dockerfiles** : Vérifie que les Dockerfiles existent
- ✅ **Documentation** : Vérifie la présence de documentation

## 🚦 Workflow

```
git push
    ↓
Tests automatiques (workflow: "Tests and Validation")
    ↓
    ├─ ✅ Tous les tests passent → Déploiement automatique
    └─ ❌ Un test échoue → Déploiement BLOQUÉ
```

## 🔍 Voir les Résultats

1. Allez dans l'onglet **Actions** de votre repo GitHub
2. Cliquez sur le workflow "Tests and Validation"
3. Voir les détails de chaque test

## ⚠️ Si un Test Échoue

### Erreur de syntaxe Python
```bash
# Testez localement
cd backend
python -m py_compile app/main.py
```

### Erreur dans Caddyfile
```bash
# Vérifiez que BACKEND_URL est présent
grep BACKEND_URL deploy/Caddyfile
```

### Erreur dans docker-compose
```bash
# Vérifiez la syntaxe YAML
docker compose -f deploy/docker-compose.prod.yml config
```

## 🛠️ Tests Locaux (Optionnel)

Vous pouvez exécuter les tests localement avant de pusher :

```bash
# Backend
cd backend
python -m py_compile app/main.py
python -c "import app.main"

# Frontend
cd frontend
npm run build

# Configuration
grep BACKEND_URL deploy/Caddyfile
grep BACKEND_URL deploy/docker-compose.prod.yml
```

## 📝 Ajouter de Nouveaux Tests

Modifiez `.github/workflows/test.yml` pour ajouter :
- Tests unitaires
- Tests d'intégration
- Tests de performance
- Tests de sécurité

## ✅ Checklist Avant Push

- [ ] Code Python sans erreurs de syntaxe
- [ ] Imports fonctionnent
- [ ] Caddyfile contient BACKEND_URL
- [ ] docker-compose.prod.yml est valide
- [ ] Pas de workflows en double

## 🎯 Objectif

**Bloquer automatiquement les déploiements qui casseraient la production.**

Si les tests passent, le déploiement se fait automatiquement.
Si les tests échouent, vous devez corriger avant de pouvoir déployer.

