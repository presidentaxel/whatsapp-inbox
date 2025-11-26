# 🎨 Guide de l'Interface WhatsApp Business

## 🎉 Nouveautés dans l'Interface

L'interface WhatsApp Inbox dispose maintenant de **toutes les fonctionnalités** de l'API WhatsApp Business !

---

## 📦 Installation

### 1. Installer les dépendances manquantes

```bash
cd frontend
npm install react-icons
```

### 2. Redémarrer le frontend

```bash
npm run dev
```

---

## 🚀 Fonctionnalités de l'Interface

### 1. 📨 Messages Avancés dans le Chat

Dans chaque conversation, vous avez maintenant un **champ de saisie amélioré** avec 4 modes :

#### Mode Texte (par défaut)
- Envoi de messages texte classiques
- Aperçu des URLs optionnel

#### Mode Média
1. Cliquez sur l'icône grille en bas à gauche
2. Sélectionnez "Média"
3. Choisissez un fichier (image, vidéo, audio, document)
4. Ajoutez une légende (optionnelle)
5. Le fichier est automatiquement uploadé et envoyé

#### Mode Boutons Interactifs
1. Cliquez sur l'icône grille
2. Sélectionnez "Boutons"
3. Ajoutez jusqu'à 3 boutons (ID + Titre)
4. En-tête et pied de page optionnels
5. Tapez le texte principal
6. Envoyez !

**Exemple :**
- Texte : "Comment souhaitez-vous être contacté ?"
- Bouton 1 : ID=`email`, Titre=`Par email`
- Bouton 2 : ID=`phone`, Titre=`Par téléphone`
- Bouton 3 : ID=`whatsapp`, Titre=`Par WhatsApp`

#### Mode Liste Déroulante
1. Cliquez sur l'icône grille
2. Sélectionnez "Liste"
3. Configurez les sections et les lignes
4. Chaque ligne a un ID, un titre et une description
5. Envoyez !

**Exemple :**
- Section "Produits" :
  - Ligne 1 : ID=`prod_1`, Titre=`Smartphone`, Description=`599€`
  - Ligne 2 : ID=`prod_2`, Titre=`Laptop`, Description=`999€`
- Section "Services" :
  - Ligne 1 : ID=`svc_1`, Titre=`Réparation`, Description=`À partir de 50€`

---

### 2. 🏢 Panneau WhatsApp Business

Cliquez sur l'icône **WhatsApp** (logo vert) dans la barre latérale.

#### Onglet "Informations"

**Informations du Numéro :**
- Numéro affiché
- Nom vérifié
- Qualité du numéro (GREEN/YELLOW/RED)
- Statut de vérification

**Détails WABA :**
- WABA ID
- Nom du compte
- Fuseau horaire
- Statut de review

> ⚠️ **Note :** Pour voir ces informations, configurez `waba_id` dans la table `whatsapp_accounts`.

#### Onglet "Profil Business"

**Consultation :**
- Voir toutes les informations de votre profil WhatsApp Business
- À propos, description, email, adresse, sites web, secteur

**Modification :**
1. Cliquez sur "Modifier"
2. Remplissez les champs souhaités
3. **À propos** : max 139 caractères (affiché dans WhatsApp)
4. **Description** : max 512 caractères
5. **Secteur** : sélectionnez dans la liste déroulante
6. Cliquez sur "Enregistrer"

Les modifications sont visibles immédiatement sur WhatsApp pour vos clients !

#### Onglet "Templates"

**Lister vos templates :**
- Voir tous vos templates existants
- Statut : APPROVED (vert), PENDING (jaune), REJECTED (rouge)
- Catégorie et langue affichées

**Créer un template :**
1. Cliquez sur "+ Nouveau Template"
2. **Nom** : sans espaces, minuscules (ex: `confirmation_commande`)
3. **Catégorie** :
   - **UTILITY** : notifications transactionnelles (recommandé)
   - **MARKETING** : messages promotionnels
   - **AUTHENTICATION** : codes de vérification
4. **Langue** : Français, Anglais, Espagnol
5. **Corps** : utilisez `{{1}}`, `{{2}}` pour les variables dynamiques
6. Cliquez sur "Créer et Soumettre à Meta"

**Exemple de template :**
```
Nom: nouvelle_commande
Catégorie: UTILITY
Langue: fr
Corps: Bonjour {{1}}, votre commande #{{2}} d'un montant de {{3}}€ a été confirmée !
```

> ⚠️ **Important :** Les templates doivent être approuvés par Meta (quelques heures à quelques jours).

**Supprimer un template :**
- Cliquez sur "Supprimer" à côté du template
- Confirmez la suppression

#### Onglet "Médias"

**Upload de médias :**
1. Cliquez sur "Cliquez pour sélectionner un fichier"
2. Choisissez votre image/vidéo/audio/document
3. Le fichier est uploadé instantanément
4. **Copiez le Media ID** affiché

**Utiliser un média uploadé :**
1. Dans un chat, activez le mode "Média"
2. OU : utilisez le Media ID dans un template qui contient une image

**Formats supportés :**
- **Images** : JPEG, PNG (max 5 MB)
- **Audio** : MP3, OGG, AMR (max 16 MB)
- **Vidéo** : MP4, 3GP (max 16 MB)
- **Documents** : PDF, DOC, DOCX, XLS, XLSX (max 100 MB)

> 💡 **Astuce :** Les médias sont conservés 30 jours sur les serveurs Meta.

---

## 🎯 Cas d'Usage Réels

### Cas 1 : Menu de Support Client

**Dans le chat :**
1. Cliquez sur l'icône grille
2. Sélectionnez "Boutons"
3. Configuration :
   - En-tête : `Support Client`
   - Texte : `Comment puis-je vous aider ?`
   - Bouton 1 : `track_order` / `Suivre ma commande`
   - Bouton 2 : `cancel` / `Annuler commande`
   - Bouton 3 : `contact` / `Contacter un agent`
   - Pied de page : `Disponible 24/7`
4. Envoyez

Le client voit un message avec 3 boutons cliquables dans WhatsApp !

### Cas 2 : Catalogue de Produits

**Dans le chat :**
1. Cliquez sur l'icône grille
2. Sélectionnez "Liste"
3. Configuration :
   - Texte : `Découvrez nos produits`
   - Texte du bouton : `Voir le catalogue`
   - Section 1 : `Électronique`
     - Ligne 1 : `laptop` / `Laptop Pro` / `999€`
     - Ligne 2 : `smartphone` / `Smartphone XL` / `599€`
   - Section 2 : `Accessoires`
     - Ligne 1 : `ecouteurs` / `Écouteurs Sans Fil` / `79€`
4. Envoyez

Le client reçoit une liste déroulante élégante dans WhatsApp !

### Cas 3 : Confirmation de Commande Automatique

**Créer le template (une fois) :**
1. Onglet WhatsApp Business > Templates
2. Nouveau Template :
   - Nom : `confirmation_commande`
   - Catégorie : `UTILITY`
   - Langue : `fr`
   - Corps : `Bonjour {{1}}, votre commande #{{2}} d'un montant de {{3}}€ a été confirmée ! Livraison estimée : {{4}}.`
3. Attendez l'approbation Meta

**Utiliser le template :**
- Une fois approuvé, utilisez l'API backend pour envoyer des confirmations automatiques
- Les variables seront remplacées dynamiquement

### Cas 4 : Envoyer une Facture PDF

**Upload du PDF :**
1. Onglet WhatsApp Business > Médias
2. Uploadez la facture PDF
3. Copiez le Media ID (ex: `1234567890`)

**Envoyer au client :**
1. Dans le chat, activez le mode "Média"
2. Sélectionnez le PDF ou entrez le Media ID
3. Ajoutez une légende : `Voici votre facture pour la commande #12345`
4. Envoyez

---

## ⚙️ Configuration Requise

### Pour voir toutes les fonctionnalités :

1. **Configurer waba_id** (pour templates et infos WABA) :
   ```sql
   UPDATE whatsapp_accounts
   SET waba_id = 'votre_waba_id'
   WHERE id = 'votre_account_id';
   ```

2. **Configurer business_id** (pour management avancé) :
   ```sql
   UPDATE whatsapp_accounts
   SET business_id = 'votre_business_id'
   WHERE id = 'votre_account_id';
   ```

3. **Variables d'environnement** :
   ```bash
   META_APP_ID=votre_app_id
   META_APP_SECRET=votre_app_secret
   ```

### Obtenir ces valeurs :

**WABA ID :**
1. Meta for Developers > WhatsApp > API Setup
2. L'ID affiché en haut de la page

**Business ID :**
1. [Business Manager](https://business.facebook.com/)
2. Settings > Business Info > Business ID

---

## 🎨 Interface Utilisateur

### Navigation Principale

L'icône WhatsApp (logo vert) apparaît maintenant dans la barre latérale gauche :

```
[💬 Chat]
[👥 Contacts]
[📱 WhatsApp Business] ← NOUVEAU !
[🤖 Assistant Gemini]
[⚙️ Paramètres]
```

### Raccourcis Clavier

Dans le champ de saisie :
- **Entrée** : Envoyer le message
- **Maj + Entrée** : Nouvelle ligne (pour les listes)

---

## 🆘 Résolution de Problèmes

### "waba_id not configured"
→ Ajoutez le WABA ID dans la table `whatsapp_accounts` (voir Configuration Requise)

### Les templates n'apparaissent pas
→ Vérifiez que `waba_id` est configuré et que vous avez créé des templates dans Meta

### L'upload de média échoue
→ Vérifiez la taille du fichier (max 100 MB) et le format

### Les boutons/listes ne s'affichent pas
→ Assurez-vous que le destinataire utilise une version récente de WhatsApp

### Erreur 502 Bad Gateway
→ Vérifiez que `python-multipart` est installé : `pip install python-multipart`

---

## 💡 Bonnes Pratiques

1. **Templates** :
   - Utilisez UTILITY pour les notifications transactionnelles
   - Évitez le langage promotionnel agressif
   - Testez toujours avant de soumettre à Meta

2. **Boutons Interactifs** :
   - Max 20 caractères par titre de bouton
   - Utilisez des IDs descriptifs (ex: `confirm_order` pas `btn1`)
   - Max 3 boutons par message

3. **Listes** :
   - Max 10 sections
   - Max 10 lignes par section
   - Titres courts et descriptifs

4. **Médias** :
   - Optimisez la taille avant upload
   - Utilisez des noms de fichiers clairs
   - Conservez les Media IDs pour réutilisation

---

## 📚 Ressources

- **Documentation API** : [WHATSAPP_API_COMPLETE_GUIDE.md](./WHATSAPP_API_COMPLETE_GUIDE.md)
- **Démarrage rapide** : [WHATSAPP_API_QUICK_START.md](./WHATSAPP_API_QUICK_START.md)
- **Documentation Meta** : https://developers.facebook.com/docs/whatsapp/cloud-api

---

## 🎉 C'est Tout !

Vous avez maintenant une **plateforme WhatsApp Business complète** directement dans votre interface web !

Profitez de toutes les fonctionnalités pour améliorer votre communication client. 🚀

