# Endpoints de Diagnostic - Alternative aux logs Render

Puisque vous n'avez pas accès aux logs Render, j'ai créé des endpoints de diagnostic accessibles via l'API pour voir l'état du système et les erreurs.

## 📍 Endpoints disponibles

### 1. Diagnostic complet
**GET** `https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full`

Retourne un diagnostic complet du système :
- État des messages (entrants/sortants)
- Comptes configurés
- Connexion à la base de données
- Erreurs récentes

**Exemple :**
```bash
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full
```

### 2. État des webhooks
**GET** `https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/webhook-status`

Voir l'état des webhooks et des messages récents :
- Nombre de messages entrants/sortants
- Messages des dernières 24h
- Derniers messages reçus
- Comptes configurés

**Exemple :**
```bash
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/webhook-status
```

### 3. Erreurs récentes
**GET** `https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/recent-errors`

Voir les dernières erreurs enregistrées (stockées en mémoire) :
- Type d'erreur
- Message d'erreur
- Détails
- Timestamp

**Exemple :**
```bash
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/recent-errors
```

### 4. Test de webhook
**GET** `https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/test-webhook`

Retourne un exemple de payload pour tester un webhook, avec la commande curl prête à l'emploi.

**Exemple :**
```bash
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/test-webhook
```

### 5. Connexion base de données
**GET** `https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/database-connection`

Teste la connexion à la base de données.

**Exemple :**
```bash
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/database-connection
```

## 🔍 Comment utiliser

### Via le navigateur

Ouvrez simplement l'URL dans votre navigateur :
```
https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full
```

Vous verrez un JSON avec toutes les informations.

### Via curl (terminal)

```bash
# Diagnostic complet
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full | jq

# État des webhooks
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/webhook-status | jq

# Erreurs récentes
curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/recent-errors | jq
```

### Via un script Python

```python
import httpx
import json

response = httpx.get("https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full")
data = response.json()
print(json.dumps(data, indent=2))
```

## 📊 Ce que vous pouvez voir

### Messages
- Nombre total de messages récents
- Messages entrants vs sortants
- Messages des dernières 24h
- Derniers messages avec leur contenu

### Comptes
- Liste de tous les comptes WhatsApp
- Leur statut (actif/inactif)
- Leur phone_number_id

### Erreurs
- Type d'erreur (webhook_processing, message_processing_change, etc.)
- Message d'erreur complet
- Détails contextuels
- Timestamp

### Base de données
- État de la connexion
- Résultat des tests

## 🎯 Workflow de diagnostic

1. **Vérifier l'état général :**
   ```bash
   curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/full
   ```

2. **Voir les erreurs récentes :**
   ```bash
   curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/recent-errors
   ```

3. **Vérifier les messages :**
   ```bash
   curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/webhook-status
   ```

4. **Tester un webhook :**
   ```bash
   # Récupérer l'exemple de payload
   curl https://whatsapp.lamaisonduchauffeurvtc.fr/diagnostics/test-webhook
   
   # Utiliser la commande curl fournie pour tester
   ```

## ⚠️ Limitations

- Les erreurs sont stockées en mémoire (perdues au redémarrage)
- Seulement les 100 dernières erreurs sont conservées
- Les erreurs sont enregistrées seulement si le code de diagnostic est actif

## 🚀 Après déploiement

Une fois que vous avez pushé ces modifications :

1. Attendez que Render déploie
2. Testez les endpoints de diagnostic
3. Envoyez un webhook de test depuis Meta
4. Vérifiez immédiatement `/diagnostics/recent-errors` pour voir l'erreur exacte

Cela vous permettra de voir exactement où et pourquoi les webhooks échouent sans avoir accès aux logs Render !

