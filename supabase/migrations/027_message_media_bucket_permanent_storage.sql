-- ============================================================================
-- Création du bucket message-media avec RLS pour stockage permanent
-- ============================================================================
-- Ce script crée le bucket pour stocker tous les médias (images, vidéos, documents)
-- reçus et envoyés via WhatsApp, avec une politique de stockage permanent
-- (pas d'expiration automatique).
--
-- IMPORTANT: Les médias stockés dans ce bucket ne seront JAMAIS supprimés
-- automatiquement. Ils resteront accessibles indéfiniment pour les utilisateurs.
--
-- NOTE: Si vous obtenez une erreur de permissions lors de la création du bucket,
-- créez-le manuellement via Supabase Dashboard > Storage > New bucket, puis
-- exécutez uniquement les sections 2-6 (politiques RLS) de ce script.
-- ============================================================================

-- 1. Créer le bucket message-media s'il n'existe pas
-- Si cette commande échoue avec une erreur de permissions, créez le bucket
-- manuellement via le Dashboard Supabase (Storage > New bucket)
-- Note: Le bucket est PUBLIC pour permettre l'accès direct aux URLs
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'message-media',
  'message-media',
  true,  -- Public pour accès direct via URLs
  209715200,  -- 200MB max par fichier (suffisant pour la plupart des vidéos)
  ARRAY[
    -- Images
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    -- Vidéos
    'video/mp4',
    'video/quicktime',
    'video/x-msvideo',
    'video/webm',
    -- Audio
    'audio/mpeg',
    'audio/ogg',
    'audio/wav',
    'audio/aac',
    'audio/mp4',
    'audio/webm',
    -- Documents
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'text/plain',
    'text/csv',
    -- Autres
    'application/zip',
    'application/x-zip-compressed',
    'application/vnd.rar',
    'application/x-tar'
  ]
)
ON CONFLICT (id) DO UPDATE
SET
  public = true,  -- S'assurer que le bucket reste public
  file_size_limit = 209715200,  -- 200MB (mise à jour de la limite)
  allowed_mime_types = EXCLUDED.allowed_mime_types;  -- Mettre à jour les types MIME

-- 2. Supprimer les anciennes politiques RLS si elles existent (pour éviter les conflits)
DROP POLICY IF EXISTS "Public read access for message media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can upload message media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can update message media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete message media" ON storage.objects;
DROP POLICY IF EXISTS "Public Access" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can upload" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete" ON storage.objects;

-- Note: RLS est déjà activé par défaut sur storage.objects dans Supabase
-- Pas besoin de l'activer manuellement

-- 3. Politique RLS pour la lecture publique
-- Permet à tous (authentifiés et non-authentifiés) de lire les médias
-- car le bucket est public et les URLs doivent être accessibles
CREATE POLICY "Public read access for message media"
ON storage.objects FOR SELECT
USING (bucket_id = 'message-media');

-- 4. Politique RLS pour l'upload (INSERT)
-- Seuls les utilisateurs authentifiés peuvent uploader des médias
CREATE POLICY "Authenticated users can upload message media"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);

-- 5. Politique RLS pour la mise à jour (UPDATE)
-- Permet aux utilisateurs authentifiés de mettre à jour les métadonnées des fichiers
CREATE POLICY "Authenticated users can update message media"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
)
WITH CHECK (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);

-- 6. Politique RLS pour la suppression (DELETE)
-- Seuls les utilisateurs authentifiés peuvent supprimer des médias
-- Note: Cette politique permet la suppression manuelle, mais il n'y a pas
-- de politique d'expiration automatique configurée dans Supabase Storage
CREATE POLICY "Authenticated users can delete message media"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);

-- ============================================================================
-- NOTES IMPORTANTES:
-- ============================================================================
-- 1. STOCKAGE PERMANENT: 
--    - Aucune politique d'expiration automatique n'est configurée
--    - Les médias resteront dans le bucket indéfiniment
--    - Pour supprimer des médias, il faut le faire manuellement via l'API ou le dashboard
--
-- 2. ACCÈS PUBLIC:
--    - Le bucket est PUBLIC, donc les URLs sont accessibles sans authentification
--    - Cela permet d'afficher les images/vidéos directement dans le frontend
--    - Les URLs sont de la forme: {SUPABASE_URL}/storage/v1/object/public/message-media/{file_path}
--
-- 3. SÉCURITÉ:
--    - Seuls les utilisateurs authentifiés peuvent uploader/modifier/supprimer
--    - La lecture est publique (nécessaire pour l'affichage des médias)
--    - Les noms de fichiers sont basés sur les IDs de messages (UUID), donc non devinables
--
-- 4. LIMITES:
--    - Taille max par fichier: 200MB (suffisant pour la plupart des vidéos)
--    - Types MIME autorisés: images, vidéos, audio, documents
--
-- 5. MIGRATION DES DONNÉES EXISTANTES:
--    - Si vous avez déjà des médias dans un autre bucket, vous devrez les migrer manuellement
--    - Le code backend télécharge automatiquement les nouveaux médias dans ce bucket
-- ============================================================================

