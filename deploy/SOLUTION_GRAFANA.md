# Solution : Problème d'accès à Grafana via /grafana

## Problème identifié

Quand vous accédiez à `/grafana`, cela redirigeait vers votre application React au lieu de Grafana. Cela était dû à plusieurs problèmes :

1. **Configuration Caddyfile** : La route Grafana n'était pas correctement structurée
2. **Variables d'environnement manquantes** : Les variables `DOMAIN` et `EMAIL` n'étaient pas définies
3. **Configuration Grafana** : La syntaxe pour `GF_SERVER_ROOT_URL` était incorrecte

## Corrections apportées

### ✅ 1. Caddyfile corrigé
- Routes Grafana clarifiées et mieux structurées
- Redirection `/grafana` → `/grafana/` 
- Proxy correct vers Grafana avec les bons headers
- Ordre des routes corrigé (Grafana avant le catch-all frontend)

### ✅ 2. Docker Compose & GitHub Actions mis à jour
- Ajout de `env_file` pour charger `deploy/.env`
- Workflow `deploy-ovh.yml` génère maintenant `deploy/.env` automatiquement depuis les secrets `OVH_DOMAIN` et `OVH_TLS_EMAIL`
- Configuration Grafana corrigée : `GF_SERVER_ROOT_URL=https://${DOMAIN}/grafana/`
- Grafana ajouté comme dépendance de Caddy

### ✅ 3. Scripts créés
- `setup-env.ps1` : Script PowerShell pour créer le fichier `.env` automatiquement
- `ENV_SETUP.md` : Documentation détaillée

## 🔧 Actions à effectuer SUR VOTRE MV OVH

### Étape 1 : Créer le fichier `.env` dans `deploy/`

Sur votre serveur OVH, créez le fichier `deploy/.env` :

```bash
cd /opt/whatsapp-inbox/deploy  # ou le chemin où se trouve votre projet
cat > .env << 'EOF'
DOMAIN=whatsapp.lamaisonduchauffeurvtc.fr
EMAIL=votre-email@example.com
EOF
```

**⚠️ Important** : Remplacez `votre-email@example.com` par votre vraie adresse email (utilisée pour les certificats SSL Let's Encrypt).

### Étape 2 : Redémarrer les services

```bash
cd deploy
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

### Étape 3 : Vérifier que tout fonctionne

1. **Vérifier les logs Caddy** :
   ```bash
   docker-compose -f docker-compose.prod.yml logs caddy
   ```
   Vous ne devriez voir aucune erreur liée à `DOMAIN` ou `EMAIL`.

2. **Vérifier que Grafana démarre** :
   ```bash
   docker-compose -f docker-compose.prod.yml logs grafana
   ```

3. **Tester l'accès** :
   - Ouvrez votre navigateur : `https://whatsapp.lamaisonduchauffeurvtc.fr/grafana`
   - Vous devriez voir la page de connexion Grafana
   - Identifiants par défaut : `admin` / `admin` (à changer après la première connexion)

## 🔍 Si ça ne marche toujours pas

### Vérifier que le fichier .env est bien lu :

```bash
cd deploy
docker-compose -f docker-compose.prod.yml config | grep DOMAIN
```

Cela devrait afficher votre domaine.

### Vérifier les logs détaillés :

```bash
docker-compose -f docker-compose.prod.yml logs caddy | grep -i grafana
docker-compose -f docker-compose.prod.yml logs grafana | tail -20
```

### Vérifier que Caddy route correctement :

```bash
curl -I https://whatsapp.lamaisonduchauffeurvtc.fr/grafana/
```

Vous devriez recevoir une réponse HTTP 200 ou 302, pas une 404.

## 📝 Résumé des fichiers modifiés

- ✅ `deploy/Caddyfile` : Configuration des routes corrigée
- ✅ `deploy/docker-compose.prod.yml` : Ajout de `env_file` et correction de la config Grafana
- ✅ Documentation ajoutée : `deploy/ENV_SETUP.md` et `deploy/SOLUTION_GRAFANA.md`
- ✅ Script créé : `deploy/setup-env.ps1` (Windows) et `deploy/restart-services.ps1`

## 🎯 Résultat attendu

Après ces corrections, vous devriez pouvoir :
- ✅ Accéder à Grafana via `https://whatsapp.lamaisonduchauffeurvtc.fr/grafana`
- ✅ Tout fonctionner depuis une seule machine virtuelle OVH
- ✅ Avoir les certificats SSL générés automatiquement par Let's Encrypt

