# Guide : Uploader une Image de Profil Manuellement

## Pourquoi uploader manuellement ?

WhatsApp Cloud API **ne fournit pas** d'endpoint pour récupérer les images de profil des contacts, même pour votre propre compte. C'est une limitation de l'API.

## Solution : Upload manuel

### Option 1 : Depuis un fichier local

1. **Téléchargez votre image de profil WhatsApp** :
   - Depuis WhatsApp Web : Cliquez droit sur votre photo de profil → Enregistrer l'image
   - Depuis l'app mobile : Prendre une capture d'écran ou partager l'image

2. **Sauvegardez l'image** quelque part sur votre ordinateur (ex: `C:\Users\louis\Pictures\profile.jpg`)

3. **Utilisez le script** :
   ```powershell
   cd backend
   python -m scripts.upload_profile_picture b00a5d98-c135-4ed2-a413-f4a4e56f2019 "C:\Users\louis\Pictures\profile.jpg"
   ```

### Option 2 : Depuis une URL

Si vous avez l'URL de l'image (depuis WhatsApp Web ou autre source) :

1. **Téléchargez l'image depuis l'URL** :
   ```powershell
   # Utiliser curl ou Invoke-WebRequest pour télécharger
   Invoke-WebRequest -Uri "https://url-de-l-image.com/image.jpg" -OutFile "profile.jpg"
   ```

2. **Puis utilisez le script** avec le fichier téléchargé

### Option 3 : Via l'interface Supabase

1. Allez dans **Supabase Dashboard** → **Storage** → **profile-pictures**
2. Cliquez sur **Upload file**
3. Nommez le fichier : `{contact_id}.jpg` (ex: `b00a5d98-c135-4ed2-a413-f4a4e56f2019.jpg`)
4. Copiez l'URL publique
5. Mettez à jour dans la base de données :
   ```sql
   UPDATE contacts 
   SET profile_picture_url = 'https://votre-projet.supabase.co/storage/v1/object/public/profile-pictures/b00a5d98-c135-4ed2-a413-f4a4e56f2019.jpg'
   WHERE id = 'b00a5d98-c135-4ed2-a413-f4a4e56f2019';
   ```

## Formats supportés

- JPG / JPEG
- PNG
- WEBP
- GIF

Taille maximale recommandée : 5MB

## Vérification

Après l'upload, l'image devrait apparaître automatiquement dans l'interface mobile lors du prochain rafraîchissement.

