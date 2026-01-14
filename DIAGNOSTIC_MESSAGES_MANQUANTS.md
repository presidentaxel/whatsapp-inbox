# Diagnostic: Messages entrants ne s'affichent plus

## Problème identifié

Le diagnostic montre que **aucun message entrant n'a été sauvegardé dans la dernière heure**, alors que les messages sortants fonctionnent (les conversations sont mises à jour).

## Causes possibles

### 1. Les webhooks ne sont pas reçus par le backend
- **Symptôme**: Aucun log "📥 Webhook received" dans les logs du backend
- **Solution**: 
  - Vérifier que le webhook est bien configuré dans Meta Business Suite
  - Vérifier que l'URL du webhook est accessible depuis Internet
  - Vérifier les logs du serveur pour voir si les requêtes arrivent

### 2. Le compte n'est pas trouvé lors de la réception du webhook
- **Symptôme**: Logs "❌ CRITICAL: Cannot find account for webhook!"
- **Solution**: 
  - Vérifier que le `phone_number_id` dans le webhook correspond à un compte dans la table `whatsapp_accounts`
  - Vérifier que les comptes sont bien actifs (`is_active = true`)

### 3. L'insertion échoue silencieusement
- **Symptôme**: Logs "📨 Processing X messages" mais pas de "✅ Message processed successfully"
- **Solution**: 
  - Vérifier les logs d'erreur du backend
  - Vérifier les permissions RLS dans Supabase
  - Vérifier que le backend utilise bien `service_role` (qui bypass RLS)

## Actions à prendre

### 1. Vérifier les logs du backend en temps réel

```bash
# Si vous utilisez Docker
docker logs -f <container_name> | grep -E "webhook|message|MESSAGE"

# Si vous utilisez systemd
journalctl -u <service_name> -f | grep -E "webhook|message|MESSAGE"
```

Cherchez spécifiquement:
- `📥 Webhook received` - Confirme que les webhooks arrivent
- `❌ CRITICAL: Cannot find account` - Problème de compte
- `📨 Processing X messages` - Messages détectés dans le webhook
- `💾 [MESSAGE INSERT]` - Tentative d'insertion (nouveau logging)
- `✅ Message processed successfully` - Message sauvegardé avec succès
- `❌ Error in _process_incoming_message` - Erreur lors du traitement

### 2. Tester manuellement un webhook

Utilisez le script de test:
```bash
cd backend
python scripts/test_webhook_endpoint.py
```

### 3. Vérifier la configuration du webhook dans Meta

1. Allez dans Meta Business Suite > WhatsApp > Configuration
2. Vérifiez que l'URL du webhook est correcte
3. Vérifiez que le `verify_token` correspond
4. Testez le webhook depuis l'interface Meta

### 4. Vérifier les permissions RLS

Le backend doit utiliser `service_role` pour bypasser RLS. Vérifiez dans `.env`:
```
SUPABASE_SERVICE_ROLE_KEY=eyJ... (doit être la service_role key, pas l'anon key)
```

### 5. Vérifier que les comptes sont bien configurés

Exécutez le diagnostic:
```bash
cd backend
python scripts/diagnose_missing_messages.py
```

## Améliorations apportées

1. **Logging amélioré**: Ajout de logs détaillés lors de l'insertion des messages pour identifier exactement où ça bloque
2. **Vérification post-insertion**: Vérification que le message est bien sauvegardé avec les bons paramètres (conversation_id, direction)

## Prochaines étapes

1. Redémarrer le backend pour activer les nouveaux logs
2. Envoyer un message de test depuis WhatsApp
3. Vérifier les logs pour voir exactement où ça bloque
4. Partager les logs si le problème persiste

