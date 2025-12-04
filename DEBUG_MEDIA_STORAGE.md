# Guide de débogage - Stockage des médias

## Problème : Rien n'est stocké dans le bucket Supabase

### Étape 1 : Vérifier que le bucket existe

1. Allez dans votre **Supabase Dashboard**
2. Naviguez vers **Storage**
3. Vérifiez que le bucket `message-media` existe
4. Si il n'existe pas, créez-le :
   - Nom : `message-media`
   - Public : ✅ Activé
   - Limite de taille : 50 MB (ou selon vos besoins)

### Étape 2 : Tester le bucket avec le script de test

```bash
cd backend
python scripts/test_media_storage.py
```

Ce script va :
- Vérifier que le bucket existe
- Tester un upload de fichier
- Afficher les erreurs éventuelles

### Étape 3 : Vérifier les logs du backend

Quand vous recevez un message avec média, vous devriez voir dans les logs du backend :

```
📥 Media detected: message_id=..., media_id=..., type=image
✅ Account found, starting async media download for message_id=...
🚀 Starting media download and storage: message_id=..., media_id=...
📡 Fetching media metadata from WhatsApp: media_id=...
📥 Download URL obtained, downloading media: message_id=...
💾 Starting storage in Supabase: message_id=..., mime_type=...
📤 Uploading to bucket 'message-media': path=..., size=... bytes
✅ Upload result: ...
✅ Message media uploaded to Supabase Storage: ...
✅ Media stored in Supabase Storage: message_id=..., storage_url=...
```

Si vous ne voyez **aucun de ces logs**, cela signifie que :
- Le code n'est pas exécuté (vérifiez que `msg_type` est bien dans la liste)
- Le `message_db_id` est None
- Le `media_id` est None

### Étape 4 : Vérifier les permissions du bucket

Dans Supabase Dashboard > Storage > Policies, vérifiez que vous avez :

1. **Politique de lecture publique** :
   ```sql
   CREATE POLICY "Public Access"
   ON storage.objects FOR SELECT
   USING (bucket_id = 'message-media');
   ```

2. **Politique d'upload** (pour les utilisateurs authentifiés) :
   ```sql
   CREATE POLICY "Authenticated users can upload"
   ON storage.objects FOR INSERT
   WITH CHECK (
     bucket_id = 'message-media' 
     AND auth.role() = 'authenticated'
   );
   ```

### Étape 5 : Vérifier les variables d'environnement

Assurez-vous que `SUPABASE_URL` est bien configuré dans votre `.env` :

```env
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_KEY=votre-service-role-key
```

### Étape 6 : Vérifier que les messages ont bien un media_id

Dans votre base de données, vérifiez :

```sql
SELECT id, message_type, media_id, storage_url, timestamp 
FROM messages 
WHERE message_type IN ('image', 'video', 'audio', 'document', 'sticker')
ORDER BY timestamp DESC 
LIMIT 10;
```

Si `media_id` est NULL, le code ne s'exécutera pas.

### Étape 7 : Tester manuellement l'upload

Si le bucket existe et les permissions sont correctes, testez manuellement :

```python
# Dans un shell Python
from app.services.storage_service import upload_message_media

# Test avec une petite image
test_data = b'\x89PNG\r\n\x1a\n...'  # Données PNG
result = await upload_message_media(
    message_id="test-123",
    media_data=test_data,
    content_type="image/png"
)
print(result)
```

### Problèmes courants

1. **Bucket n'existe pas** : Créez-le dans le Dashboard
2. **Permissions manquantes** : Ajoutez les politiques RLS
3. **SUPABASE_URL non configuré** : Vérifiez votre `.env`
4. **Erreur silencieuse** : Vérifiez les logs du backend avec les nouveaux logs ajoutés
5. **Média expiré** : Les médias WhatsApp expirent après quelques heures/jours. Le stockage doit se faire immédiatement à la réception.

### Pour forcer le stockage d'un média existant

Si vous avez des messages avec `media_id` mais sans `storage_url`, vous pouvez créer un script pour les télécharger rétroactivement (si le média n'a pas encore expiré sur WhatsApp).

