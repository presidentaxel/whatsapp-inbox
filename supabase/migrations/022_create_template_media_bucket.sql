-- Créer le bucket pour stocker les images de templates
-- Note: Cette migration doit être exécutée manuellement dans Supabase Dashboard
-- car la création de buckets nécessite des privilèges admin

-- Instructions pour créer le bucket manuellement :
-- 1. Aller dans Supabase Dashboard > Storage
-- 2. Créer un nouveau bucket nommé "template-media"
-- 3. Le rendre PUBLIC (pour que les URLs soient accessibles)
-- 4. File size limit: 10MB (suffisant pour les images de templates)
-- 5. Allowed MIME types: image/jpeg, image/png, image/gif, image/webp, video/mp4, application/pdf

-- SQL pour créer le bucket (à exécuter dans Supabase SQL Editor avec les droits admin) :
/*
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'template-media',
  'template-media',
  true,  -- Public pour accès direct
  10485760,  -- 10MB max par fichier
  ARRAY[
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'video/mp4', 'video/quicktime',
    'application/pdf'
  ]
)
ON CONFLICT (id) DO NOTHING;
*/

-- Supprimer les politiques existantes si elles existent (pour éviter les erreurs)
DROP POLICY IF EXISTS "Public read access for template media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can upload template media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can update template media" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete template media" ON storage.objects;

-- Politique RLS pour permettre la lecture publique (bucket public)
CREATE POLICY "Public read access for template media"
ON storage.objects FOR SELECT
USING (bucket_id = 'template-media');

-- Politique pour permettre l'upload (seulement pour les utilisateurs authentifiés)
CREATE POLICY "Authenticated users can upload template media"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'template-media' 
  AND auth.role() = 'authenticated'
);

-- Politique pour permettre la mise à jour (seulement pour les utilisateurs authentifiés)
CREATE POLICY "Authenticated users can update template media"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'template-media' 
  AND auth.role() = 'authenticated'
);

-- Politique pour permettre la suppression (seulement pour les utilisateurs authentifiés)
CREATE POLICY "Authenticated users can delete template media"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'template-media' 
  AND auth.role() = 'authenticated'
);

