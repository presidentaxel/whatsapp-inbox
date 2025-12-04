# Configuration des Images de Profil

## 📋 Étapes de Configuration

### 1. Créer le Bucket dans Supabase Storage

1. Allez dans votre **Supabase Dashboard**
2. Cliquez sur **Storage** dans le menu de gauche
3. Cliquez sur **New bucket**
4. Configurez le bucket :
   - **Name**: `profile-pictures`
   - **Public bucket**: ✅ **Activé** (pour que les images soient accessibles publiquement)
   - **File size limit**: `5MB` (suffisant pour les images de profil)
   - **Allowed MIME types**: `image/jpeg, image/png, image/webp`

5. Cliquez sur **Create bucket**

### 2. Configurer les Politiques RLS (Row Level Security)

Exécutez le fichier SQL suivant dans **Supabase SQL Editor** :

```sql
-- Permettre la lecture publique
CREATE POLICY IF NOT EXISTS "Public read access for profile pictures"
ON storage.objects FOR SELECT
USING (bucket_id = 'profile-pictures');

-- Permettre l'upload pour les utilisateurs authentifiés
CREATE POLICY IF NOT EXISTS "Authenticated users can upload profile pictures"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);

-- Permettre la mise à jour pour les utilisateurs authentifiés
CREATE POLICY IF NOT EXISTS "Authenticated users can update profile pictures"
ON storage.objects FOR UPDATE
USING (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);

-- Permettre la suppression pour les utilisateurs authentifiés
CREATE POLICY IF NOT EXISTS "Authenticated users can delete profile pictures"
ON storage.objects FOR DELETE
USING (
  bucket_id = 'profile-pictures' 
  AND auth.role() = 'authenticated'
);
```

**OU** exécutez directement le fichier :
```bash
# Dans Supabase SQL Editor, copiez-collez le contenu de :
supabase/schema/011_create_profile_pictures_bucket.sql
```

### 3. Vérifier la Migration SQL

Assurez-vous d'avoir exécuté la migration pour ajouter la colonne `profile_picture_url` :

```sql
-- Dans Supabase SQL Editor
ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS profile_picture_url text;

CREATE INDEX IF NOT EXISTS idx_contacts_profile_picture 
  ON contacts(profile_picture_url) 
  WHERE profile_picture_url IS NOT NULL;
```

**OU** exécutez directement :
```bash
# Dans Supabase SQL Editor
supabase/schema/010_contacts_profile_picture.sql
```

## ✅ Vérification

Une fois configuré, le système va automatiquement :

1. **Récupérer les images de profil** depuis WhatsApp (si disponibles)
2. **Télécharger l'image** depuis l'URL WhatsApp
3. **Uploader l'image** dans Supabase Storage
4. **Stocker l'URL Supabase** dans la base de données

L'URL stockée sera au format :
```
https://votre-projet.supabase.co/storage/v1/object/public/profile-pictures/{contact_id}.jpg
```

## 🔍 Tester

Pour tester manuellement :

```bash
cd backend
python -m scripts.test_profile_picture <contact_id> <account_id>
```

## 📝 Notes

- Les images sont stockées avec le nom `{contact_id}.jpg`
- Si une image existe déjà, elle sera remplacée (upsert)
- Les images sont accessibles publiquement (bucket public)
- Si l'upload dans Supabase échoue, l'URL WhatsApp sera utilisée directement (moins idéal)

