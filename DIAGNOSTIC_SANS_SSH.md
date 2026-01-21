# Diagnostic des Messages Manquants - Sans Accès SSH

## 🌐 Méthode 1: Via l'API de Diagnostic (Recommandé)

### Accéder aux diagnostics depuis votre navigateur

Ouvrez ces URLs dans votre navigateur (remplacez le domaine si nécessaire):

#### 1. État des Webhooks et Messages
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/webhook-status
```

Cet endpoint vous montre:
- ✅ Nombre de messages entrants dans la dernière heure
- ✅ Dernier message entrant reçu
- ✅ Liste des messages entrants récents
- ✅ État des comptes WhatsApp
- ⚠️ Avertissement si aucun message entrant dans la dernière heure

#### 2. Erreurs Récentes
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/recent-errors
```

Affiche les 50 dernières erreurs enregistrées par le backend.

#### 3. Diagnostic Complet
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/full
```

Diagnostic complet du système (webhooks, base de données, erreurs).

#### 4. Test de Connexion Base de Données
```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/database-connection
```

Vérifie que le backend peut se connecter à Supabase.

### Utiliser avec curl (depuis votre machine locale)

```bash
# État des webhooks
curl https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/webhook-status | jq

# Erreurs récentes
curl https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/recent-errors | jq

# Diagnostic complet
curl https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/full | jq
```

> **Note**: Si vous n'avez pas `jq`, enlevez `| jq` pour voir le JSON brut.

## 📊 Interprétation des Résultats

### Si `incoming_last_hour: 0`

Cela signifie qu'**aucun message entrant n'a été sauvegardé dans la dernière heure**.

**Causes possibles:**
1. ❌ Les webhooks ne sont pas reçus par le backend
2. ❌ Le compte n'est pas trouvé lors de la réception
3. ❌ L'insertion échoue (permissions, erreur, etc.)

**Actions:**
- Vérifiez `recent_errors` pour voir les erreurs
- Vérifiez que les comptes sont bien actifs
- Vérifiez la configuration du webhook dans Meta Business Suite

### Si `incoming_last_hour > 0`

Les messages sont bien sauvegardés ! Le problème est probablement côté frontend:
- Vérifiez les subscriptions Supabase Realtime
- Vérifiez le polling (toutes les 4.5 secondes)
- Vérifiez les permissions RLS

### Si `last_incoming_age_minutes` est très élevé

Le dernier message entrant date de plusieurs heures/jours. Cela confirme que les nouveaux messages ne sont pas sauvegardés.

## 🔍 Exemple de Réponse

```json
{
  "status": "ok",
  "messages": {
    "incoming_last_hour": 0,
    "incoming_last_24h": 5,
    "last_incoming_message": {
      "timestamp": "2026-01-14T12:41:33",
      "content_preview": "Et les conditions de rupture..."
    }
  },
  "diagnosis": {
    "has_recent_incoming": false,
    "last_incoming_age_minutes": 245.5,
    "warning": "Aucun message entrant dans la dernière heure"
  }
}
```

## 🚀 Méthode 2: Via SSH (Si vous avez accès)

Voir le guide complet: `deploy/VOIR_LOGS_OVH.md`

Commandes rapides:
```bash
# Se connecter
ssh votre_utilisateur@votre_ip_ovh

# Aller dans le projet
cd ~/whatsapp-inbox/deploy

# Voir les logs
docker compose -f docker-compose.prod.yml logs --tail=100 backend | grep -E "webhook|MESSAGE|message"

# Logs en temps réel
docker compose -f docker-compose.prod.yml logs -f backend
```

## 🧪 Méthode 3: Tester le Webhook Manuellement

### Via l'endpoint de test

```
https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/test-webhook
```

Cet endpoint vous donne:
- Un exemple de payload à envoyer
- La commande curl complète pour tester

### Tester avec curl

```bash
# Récupérer l'exemple de payload
curl https://whatsapp.lamaisonduchauffeurvtc.fr/_diagnostics/test-webhook > test_payload.json

# Envoyer le test (remplacez le payload par celui reçu)
curl -X POST https://whatsapp.lamaisonduchauffeurvtc.fr/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

## 📋 Checklist de Diagnostic

1. ✅ **Vérifier l'état des webhooks**
   - Ouvrir: `/_diagnostics/webhook-status`
   - Vérifier `incoming_last_hour`
   - Vérifier `last_incoming_age_minutes`

2. ✅ **Vérifier les erreurs**
   - Ouvrir: `/_diagnostics/recent-errors`
   - Chercher les erreurs "Cannot find account"
   - Chercher les erreurs "MESSAGE INSERT"

3. ✅ **Vérifier les comptes**
   - Dans `webhook-status`, vérifier que les comptes sont actifs
   - Vérifier que `phone_number_id` correspond à celui dans Meta

4. ✅ **Tester le webhook**
   - Utiliser l'endpoint `/_diagnostics/test-webhook`
   - Envoyer un test manuel

5. ✅ **Vérifier la configuration Meta**
   - Aller dans Meta Business Suite
   - Vérifier que l'URL du webhook est correcte
   - Vérifier que le `verify_token` correspond

## 🆘 Si le Problème Persiste

1. **Collecter les informations:**
   - Résultat de `/_diagnostics/webhook-status`
   - Résultat de `/_diagnostics/recent-errors`
   - Résultat de `/_diagnostics/full`

2. **Vérifier la configuration:**
   - URL du webhook dans Meta Business Suite
   - `phone_number_id` dans la base de données
   - `verify_token` dans la base de données

3. **Redémarrer le backend:**
   - Via SSH: `docker compose -f docker-compose.prod.yml restart backend`
   - Ou reconstruire: `docker compose -f docker-compose.prod.yml up -d --build backend`

## 💡 Astuce: Surveiller en Temps Réel

Ouvrez plusieurs onglets:
1. `/_diagnostics/webhook-status` - Rafraîchir toutes les 30 secondes
2. `/_diagnostics/recent-errors` - Rafraîchir toutes les 30 secondes

Puis envoyez un message de test depuis WhatsApp et observez si:
- `incoming_last_hour` augmente
- De nouvelles erreurs apparaissent
- Le `last_incoming_message` se met à jour









