# Scripts de maintenance

## Mise à jour de version

Le script `update-version.js` permet de mettre à jour automatiquement la version dans tous les fichiers nécessaires pour forcer la mise à jour du Service Worker et des icônes PWA.

### Utilisation

```bash
npm run version:update <nouvelle_version>
```

**Exemple :**
```bash
npm run version:update v2.0.2
```

ou directement avec Node.js :

```bash
node scripts/update-version.js v2.0.2
```

### Ce que fait le script

Le script met à jour automatiquement la version dans :

1. **`public/sw.js`** : Met à jour `SW_VERSION`
2. **`public/manifest.json`** : Met à jour toutes les URLs d'icônes avec `?v=<version>`
3. **`index.html`** : Met à jour toutes les références aux icônes et au manifest avec `?v=<version>`

### Format de version

Le format recommandé est `vX.Y.Z` (par exemple : `v2.0.2`), mais le script accepte aussi `X.Y.Z` sans le préfixe `v`.

### Workflow recommandé

1. Modifier les icônes si nécessaire (`192x192.svg`, `512x512.svg`)
2. Mettre à jour la version avec le script
3. Tester l'application localement
4. Déployer
5. Vérifier que les icônes se mettent à jour correctement sur les appareils

### Pourquoi utiliser ce système ?

- **Service Worker** : Force la mise à jour du cache et du code du Service Worker
- **Icônes PWA** : Force le navigateur/PWA à recharger les nouvelles icônes
- **Cohérence** : Garantit que tous les fichiers utilisent la même version
- **Automatisation** : Évite les oublis de mise à jour manuelle

### Notes importantes

- ⚠️ **Toujours incrémenter la version à chaque déploiement** pour forcer la mise à jour
- 📱 Les utilisateurs verront automatiquement la nouvelle version grâce au rechargement automatique
- 🔄 Le Service Worker mettra à jour automatiquement le cache et les icônes

