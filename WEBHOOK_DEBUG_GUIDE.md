# Guide de Diagnostic - Problème de Réception des Messages

## Problème Identifié

Votre application ne reçoit plus les messages entrants, bien que les messages sortants fonctionnent et que les webhooks soient valides.

## Cause Probable

Le code cherche un compte dans la base de données en utilisant le `phone_number_id` qui arrive dans le webhook. Si ce `phone_number_id` ne correspond pas à celui stocké en base, le message est ignoré.

## Améliorations Apportées

### 1. Logging Amélioré
- ✅ Logs détaillés dans `routes_webhook.py` pour voir exactement ce qui arrive
- ✅ Logs détaillés dans `message_service.py` pour identifier pourquoi un compte n'est pas trouvé
- ✅ Affichage de tous les comptes disponibles en base quand un `phone_number_id` n'est pas trouvé

### 2. Script de Diagnostic
Un nouveau script `backend/scripts/diagnose_webhook_issue.py` a été créé pour:
- Vérifier tous les comptes dans la base de données
- Tester la recherche par `phone_number_id`
- Vérifier les variables d'environnement
- Afficher la structure attendue d'un webhook

## Comment Diagnostiquer

### Étape 1: Exécuter le Script de Diagnostic

```bash
cd backend
python scripts/diagnose_webhook_issue.py
```

Ce script va:
- Lister tous les comptes et leurs `phone_number_id`
- Vérifier que les variables d'environnement sont configurées
- Tester la recherche de compte

### Étape 2: Vérifier les Logs du Serveur

Quand un message arrive, vous devriez maintenant voir des logs détaillés comme:

```
📥 POST /webhook/whatsapp received from ...
📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1
   Entry 1: id=WABA_ID, changes=1
      Change 1: field=messages, phone_number_id=123456789, has_messages=True
🔍 Looking for account with phone_number_id: 123456789
```

Si vous voyez:
```
❌ Unknown account for phone_number_id: 123456789
📋 Available accounts in database:
   - Compte 1: phone_number_id=987654321
```

Cela signifie que le `phone_number_id` dans le webhook ne correspond pas à celui en base.

### Étape 3: Vérifier le phone_number_id

1. **Dans Meta Business:**
   - Allez dans votre compte WhatsApp Business
   - Notez le `phone_number_id` actuel

2. **Dans votre base de données:**
   ```sql
   SELECT id, name, phone_number_id, is_active 
   FROM whatsapp_accounts;
   ```

3. **Comparer:**
   - Le `phone_number_id` dans Meta doit correspondre EXACTEMENT à celui en base
   - Vérifiez aussi que `is_active = true`

### Étape 4: Corriger le Problème

#### Option A: Mettre à jour le phone_number_id en base

```sql
UPDATE whatsapp_accounts 
SET phone_number_id = 'NOUVEAU_PHONE_NUMBER_ID'
WHERE id = 'ID_DU_COMPTE';
```

#### Option B: Vérifier les variables d'environnement

Si vous utilisez le compte par défaut (via variables d'environnement), vérifiez que:
- `WHATSAPP_PHONE_ID` correspond au `phone_number_id` actuel dans Meta
- `WHATSAPP_TOKEN` est valide
- `WHATSAPP_VERIFY_TOKEN` correspond à celui configuré dans Meta

## Points à Vérifier

1. ✅ **Webhook configuré correctement dans Meta**
   - URL: `https://votre-domaine.com/webhook/whatsapp`
   - Verify token correspond
   - Webhook actif

2. ✅ **phone_number_id correspond**
   - Celui dans Meta = celui en base de données
   - Format correct (généralement un nombre)

3. ✅ **Compte actif**
   - `is_active = true` dans la table `whatsapp_accounts`

4. ✅ **Logs du serveur**
   - Les webhooks arrivent bien (voir les logs `📥 POST /webhook/whatsapp`)
   - Pas d'erreurs `❌ Unknown account`

## Test Manuel

Pour tester si le webhook fonctionne:

1. Envoyez un message à votre numéro WhatsApp Business depuis un autre numéro
2. Vérifiez les logs du serveur immédiatement
3. Vous devriez voir:
   - `📥 POST /webhook/whatsapp received`
   - `🔍 Looking for account with phone_number_id: ...`
   - Soit `✅ Account found` soit `❌ Unknown account`

## Nouvel Endpoint de Debug

Un nouvel endpoint de debug a été ajouté pour capturer exactement ce qui arrive dans les webhooks:

### Utilisation

1. **Configurer temporairement le webhook dans Meta Business:**
   - Allez dans Meta Business > Configuration > Webhooks
   - Changez temporairement l'URL vers: `https://votre-domaine.com/webhook/whatsapp/debug`
   - OU créez un webhook de test séparé pointant vers cet endpoint

2. **Envoyer un message de test:**
   - Envoyez un message à votre numéro WhatsApp Business
   - Les logs du serveur vont afficher la structure complète du webhook

3. **Vérifier les logs:**
   ```bash
   # Les logs vont afficher:
   🔍 WEBHOOK DEBUG - STRUCTURE COMPLÈTE
   [structure JSON complète]
   📋 Comptes disponibles en base
   🔄 Change analysis avec phone_number_id
   ```

4. **Remettre le webhook normal:**
   - Remettez l'URL vers: `https://votre-domaine.com/webhook/whatsapp`
   - L'endpoint `/webhook/whatsapp/debug` est juste pour le diagnostic

### Ce que l'endpoint de debug fait:

- ✅ Affiche la structure complète du webhook reçu
- ✅ Liste tous les comptes disponibles en base
- ✅ Montre exactement où se trouve (ou devrait se trouver) le `phone_number_id`
- ✅ Indique si un compte correspond ou non
- ✅ Affiche le nombre de messages et statuts dans le webhook

## Support

Si le problème persiste après ces vérifications:
1. Exécutez le script de diagnostic et partagez la sortie
2. Utilisez l'endpoint `/webhook/whatsapp/debug` pour voir la structure exacte
3. Partagez les logs du serveur (sans les tokens sensibles)
4. Vérifiez que le `phone_number_id` dans le webhook correspond à un compte en base

