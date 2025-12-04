# Configuration du stockage des médias Supabase

Ce guide explique comment configurer le stockage Supabase pour sauvegarder automatiquement les médias WhatsApp (images, vidéos, documents) et éviter les erreurs 410 Gone.

## 1. Créer le bucket Supabase Storage

### Option A : Via le Dashboard Supabase (Recommandé)

1. Allez dans votre projet Supabase Dashboard
2. Naviguez vers **Storage** dans le menu de gauche
3. Cliquez sur **"New bucket"**
4. Configurez le bucket :
   - **Name**: `message-media`
   - **Public bucket**: ✅ Activé (pour accès direct aux URLs)
   - **File size limit**: 50 MB (ou selon vos besoins)
   - **Allowed MIME types**: Laissez vide pour accepter tous les types, ou spécifiez :
     - `image/jpeg`, `image/png`, `image/gif`, `image/webp`
     - `video/mp4`, `video/quicktime`
     - `audio/mpeg`, `audio/ogg`, `audio/wav`
     - `application/pdf`
     - `application/msword`
     - `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

### Option B : Via SQL (Alternative)

Exécutez ce SQL dans l'éditeur SQL de Supabase :

```sql
-- Créer le bucket
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'message-media',
  'message-media',
  true,  -- Public pour accès direct
  52428800,  -- 50MB max par fichier
  ARRAY[
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime',
    'audio/mpeg', 'audio/ogg', 'audio/wav',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  ]
)
ON CONFLICT (id) DO NOTHING;

-- Politique RLS pour lecture publique (bucket public)
CREATE POLICY IF NOT EXISTS "Public Access"
ON storage.objects FOR SELECT
USING (bucket_id = 'message-media');

-- Politique pour upload (utilisateurs authentifiés)
CREATE POLICY IF NOT EXISTS "Authenticated users can upload"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);

-- Politique pour suppression (utilisateurs authentifiés)
CREATE POLICY IF NOT EXISTS "Authenticated users can delete"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);
```

## 2. Appliquer la migration SQL

Exécutez la migration `018_message_storage_url.sql` pour ajouter la colonne `storage_url` à la table `messages` :

```bash
# Via Supabase CLI
supabase migration up

# Ou directement dans le SQL Editor de Supabase
# Copiez-collez le contenu de supabase/migrations/018_message_storage_url.sql
```

## 3. Fonctionnement

Une fois configuré, le système fonctionne automatiquement :

1. **Réception de média** : Quand un média arrive via webhook WhatsApp, il est automatiquement téléchargé et stocké dans Supabase Storage en arrière-plan
2. **Affichage** : Le frontend vérifie d'abord si `storage_url` existe, sinon essaie de récupérer depuis WhatsApp
3. **Rétention** : Les médias sont conservés 60 jours (configurable)

## 4. Nettoyage automatique (Optionnel)

Pour nettoyer automatiquement les médias de plus de 60 jours, vous pouvez créer un job périodique :

```python
# Dans backend/app/main.py, ajoutez :
from app.services.storage_service import cleanup_old_media

@app.on_event("startup")
async def startup_event():
    # ... code existant ...
    
    # Nettoyage quotidien des médias anciens (optionnel)
    async def periodic_cleanup():
        while True:
            await asyncio.sleep(86400)  # 24 heures
            await cleanup_old_media(days=60)
    
    asyncio.create_task(periodic_cleanup())
```

Ou utilisez un cron job externe qui appelle un endpoint API.

## 5. Vérification

Pour vérifier que tout fonctionne :

1. Envoyez une image via WhatsApp à votre bot
2. Vérifiez dans Supabase Storage que le fichier apparaît dans le bucket `message-media`
3. Vérifiez dans la table `messages` que la colonne `storage_url` est remplie
4. L'image devrait s'afficher dans le chat sans erreur 410

## Notes importantes

- Les médias existants (avant cette mise à jour) ne seront pas automatiquement téléchargés
- Seuls les nouveaux médias reçus après la configuration seront stockés
- Pour les médias existants, le système essaiera toujours de les récupérer depuis WhatsApp (peut échouer si expirés)
- Le stockage utilise l'espace de votre projet Supabase (vérifiez vos limites)

