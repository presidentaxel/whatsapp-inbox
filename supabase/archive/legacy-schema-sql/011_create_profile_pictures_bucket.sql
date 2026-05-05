-- Créer le bucket pour les images de profil dans Supabase Storage
-- Note: Cette commande doit être exécutée via l'API Supabase ou le dashboard
-- car SQL ne peut pas créer directement des buckets

-- Instructions pour créer le bucket manuellement :
-- 1. Allez dans Supabase Dashboard > Storage
-- 2. Cliquez sur "New bucket"
-- 3. Nom: profile-pictures
-- 4. Public: true (pour que les images soient accessibles publiquement)
-- 5. File size limit: 5MB (suffisant pour les images de profil)
-- 6. Allowed MIME types: image/jpeg, image/png, image/webp

-- Alternative: Utiliser l'API Supabase Storage pour créer le bucket programmatiquement
-- Voir: https://supabase.com/docs/reference/javascript/storage-createbucket

-- Politique RLS pour permettre l'accès public en lecture
-- (à exécuter après création du bucket)

-- Supprimer les politiques existantes si elles existent (pour éviter les erreurs)
DROP POLICY IF EXISTS "Public read access for profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can upload profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can update profile pictures" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete profile pictures" ON storage.objects;

-- Permettre la lecture publique
CREATE POLICY "Public read access for profile pictures"
ON storage.objects FOR SELECT
USING (bucket_id = 'profile-pictures');

-- Permettre l'upload pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can upload profile pictures"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);

-- Permettre la mise à jour pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can update profile pictures"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);

-- Permettre la suppression pour les utilisateurs authentifiés
CREATE POLICY "Authenticated users can delete profile pictures"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);

