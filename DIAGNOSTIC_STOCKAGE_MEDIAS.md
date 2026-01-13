# Diagnostic du Stockage des Médias

Si les médias (images, vidéos, documents) ne sont pas sauvegardés dans Supabase Storage, suivez ce guide de diagnostic.

## 🔍 Vérifications à faire

### 1. Vérifier que le bucket existe

**Via Supabase Dashboard :**
1. Allez dans **Storage** dans le menu de gauche
2. Vérifiez qu'un bucket nommé `message-media` existe
3. Si le bucket n'existe pas :
   - Cliquez sur **"New bucket"**
   - Nom : `message-media`
   - **Public bucket** : ✅ Activé (important !)
   - File size limit : `52428800` (50MB)
   - Créez le bucket

**Via SQL :**
Exécutez le script `supabase/migrations/027_message_media_bucket_permanent_storage.sql` dans Supabase SQL Editor.

### 2. Vérifier la configuration backend

Vérifiez votre fichier `.env` (backend) :

```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # ⚠️ IMPORTANT: doit être la clé SERVICE_ROLE
```

**⚠️ CRITIQUE :** `SUPABASE_KEY` doit être la clé **service_role**, pas la clé **anon** !

- ✅ **Service Role Key** : Commence généralement par `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (longue)
- ❌ **Anon Key** : Commence généralement par `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` mais plus courte

**Où trouver la clé service_role :**
1. Supabase Dashboard → **Settings** → **API**
2. Section **Project API keys**
3. Copiez la clé **service_role** (pas la clé **anon public**)

### 3. Vérifier les politiques RLS

Les politiques RLS doivent être configurées. Exécutez le script SQL :
```sql
supabase/migrations/027_message_media_bucket_permanent_storage.sql
```

Ou vérifiez manuellement dans Supabase Dashboard :
1. **Storage** → **Policies** (onglet en haut)
2. Vérifiez que les politiques suivantes existent pour `message-media` :
   - ✅ "Public read access for message media" (SELECT)
   - ✅ "Authenticated users can upload message media" (INSERT)
   - ✅ "Authenticated users can update message media" (UPDATE)
   - ✅ "Authenticated users can delete message media" (DELETE)

### 4. Tester avec le script de diagnostic

Exécutez le script de diagnostic :

```bash
cd backend
python scripts/diagnose_media_storage.py
```

Ce script va :
- ✅ Vérifier la configuration
- ✅ Vérifier que le bucket existe
- ✅ Lister les messages avec média
- ✅ Tester un upload

### 5. Vérifier les logs du backend

Quand vous recevez un nouveau média, vérifiez les logs du backend. Vous devriez voir :

```
📥 Media detected: message_id=xxx, media_id=yyy, type=image
📡 Fetching media metadata from WhatsApp: media_id=yyy
📥 Downloading media from WhatsApp: message_id=xxx
✅ Media downloaded: message_id=xxx, size=12345 bytes
📤 Uploading to bucket 'message-media': path=xxx.jpg, size=12345 bytes
✅ Upload result: {...}
✅ Message media uploaded to Supabase Storage: https://...
✅ Media stored in Supabase Storage: message_id=xxx, storage_url=https://...
```

Si vous voyez des erreurs :
- ❌ `Bucket 'message-media' does not exist!` → Le bucket n'existe pas
- ❌ `Permission error` ou `401/403` → La clé SUPABASE_KEY n'est pas la service_role
- ❌ `Upload error` → Vérifiez les logs détaillés

### 6. Tester manuellement un upload

Si vous avez un message avec média qui n'a pas été stocké, vous pouvez forcer le téléchargement :

```bash
# Via l'API
POST /api/messages/test-storage/{message_id}
```

Ou utilisez curl :
```bash
curl -X POST http://localhost:8000/api/messages/test-storage/{message_id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🔧 Solutions aux problèmes courants

### Problème : "Bucket does not exist"
**Solution :** Créez le bucket via le Dashboard ou exécutez le script SQL

### Problème : "Permission denied" ou "401/403"
**Solution :** 
1. Vérifiez que `SUPABASE_KEY` dans `.env` est la clé **service_role**
2. Redémarrez le backend après modification

### Problème : Les médias sont téléchargés mais pas stockés
**Solution :**
1. Vérifiez les logs pour voir l'erreur exacte
2. Vérifiez que les politiques RLS sont bien configurées
3. Vérifiez que le bucket est **public**

### Problème : Les anciens médias ne sont pas stockés
**Solution :** Les médias sont stockés automatiquement seulement pour les **nouveaux messages**. Pour les anciens messages, vous devrez :
1. Soit attendre qu'un nouveau média arrive
2. Soit utiliser le script de backfill (si disponible)

## 📝 Checklist de vérification

- [ ] Le bucket `message-media` existe dans Supabase Dashboard
- [ ] Le bucket est **public** (Public bucket = ✅)
- [ ] `SUPABASE_KEY` dans `.env` est la clé **service_role** (pas anon)
- [ ] Les politiques RLS sont configurées (script SQL exécuté)
- [ ] Le backend a été redémarré après modification de `.env`
- [ ] Les logs montrent des tentatives d'upload (pas d'erreurs silencieuses)

## 🆘 Si rien ne fonctionne

1. Exécutez le script de diagnostic : `python scripts/diagnose_media_storage.py`
2. Vérifiez les logs du backend en temps réel
3. Testez un upload manuel via l'API
4. Vérifiez que vous utilisez bien la dernière version du code

