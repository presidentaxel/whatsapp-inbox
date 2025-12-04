-- Créer le bucket pour stocker les médias de messages
-- Note: Cette migration doit être exécutée manuellement dans Supabase Dashboard
-- car la création de buckets nécessite des privilèges admin

-- Instructions pour créer le bucket manuellement :
-- 1. Aller dans Supabase Dashboard > Storage
-- 2. Créer un nouveau bucket nommé "message-media"
-- 3. Le rendre PUBLIC (pour que les URLs soient accessibles)
-- 4. Optionnel: Configurer une politique de rétention de 60 jours

-- SQL pour créer le bucket (à exécuter dans Supabase SQL Editor avec les droits admin) :
/*
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
*/

-- Politique RLS pour permettre la lecture publique (bucket public)
-- Note: Pour un bucket public, cette politique peut être simplifiée
/*
CREATE POLICY "Public Access"
ON storage.objects FOR SELECT
USING (bucket_id = 'message-media');
*/

-- Politique pour permettre l'upload (seulement pour les utilisateurs authentifiés)
/*
CREATE POLICY "Authenticated users can upload"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);
*/

-- Politique pour permettre la suppression (seulement pour les utilisateurs authentifiés)
/*
CREATE POLICY "Authenticated users can delete"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'message-media' 
  AND auth.role() = 'authenticated'
);
*/

