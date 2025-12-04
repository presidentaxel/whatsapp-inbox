# Politiques RLS (Row Level Security)

Ce dossier contient les politiques de sécurité au niveau des lignes (RLS) pour protéger les données de l'application WhatsApp Inbox.

## 📋 Fichiers

- `rls_policies.sql` - Toutes les politiques RLS pour toutes les tables

## 🚀 Application des politiques

### Option 1: Via Supabase Dashboard (Recommandé)

1. Connectez-vous à votre projet Supabase
2. Allez dans **SQL Editor**
3. Ouvrez le fichier `rls_policies.sql`
4. Copiez-collez le contenu complet
5. Exécutez la requête

### Option 2: Via CLI Supabase

```bash
# Si vous utilisez Supabase CLI
supabase db push
# ou
psql -h <your-db-host> -U postgres -d postgres -f supabase/policies/rls_policies.sql
```

## 🔒 Comment ça fonctionne

### Stratégie de sécurité

1. **Backend (service_role)** : Bypass complet de RLS
   - Le backend Python utilise `SUPABASE_KEY` (service_role)
   - Toutes les opérations backend continuent de fonctionner normalement
   - Les webhooks WhatsApp continuent de fonctionner

2. **Frontend (anon key)** : Protection RLS active
   - Le frontend utilise `VITE_SUPABASE_ANON_KEY` (anon key)
   - Les utilisateurs ne voient que les données autorisées
   - Protection multi-tenant basée sur `account_id`

3. **Système RBAC** : Permissions granulaires
   - Permissions globales (tous les accounts)
   - Permissions par account (scope limité)
   - Rôles: admin, manager, viewer
   - Overrides personnalisés possibles

### Fonctions helper créées

- `user_has_global_permission(permission_code)` - Vérifie une permission globale
- `user_has_account_permission(permission_code, account_id)` - Vérifie une permission pour un account
- `is_user_active()` - Vérifie si l'utilisateur est actif
- `user_accessible_account_ids()` - Liste les accounts accessibles

## 📊 Tables protégées

Toutes les tables suivantes ont RLS activé:

- ✅ `whatsapp_accounts` - Comptes WhatsApp
- ✅ `contacts` - Contacts
- ✅ `conversations` - Conversations
- ✅ `messages` - Messages
- ✅ `app_users` - Utilisateurs de l'app
- ✅ `app_roles` - Rôles
- ✅ `app_permissions` - Permissions
- ✅ `role_permissions` - Permissions des rôles
- ✅ `app_user_roles` - Assignations de rôles
- ✅ `app_user_overrides` - Overrides de permissions
- ✅ `bot_profiles` - Profils de bot

## 🔍 Permissions requises

### Pour voir les données

- `accounts.view` - Voir les comptes WhatsApp
- `conversations.view` - Voir les conversations
- `messages.view` - Voir les messages
- `contacts.view` - Voir les contacts

### Pour modifier les données

- `accounts.manage` - Gérer les comptes
- `messages.send` - Envoyer des messages
- `users.manage` - Gérer les utilisateurs
- `roles.manage` - Gérer les rôles

## ⚠️ Points importants

1. **Le backend n'est PAS affecté**
   - Utilise `service_role` qui bypass RLS
   - Toutes les opérations backend continuent normalement

2. **Les webhooks continuent de fonctionner**
   - Utilisent le backend qui a service_role
   - Aucun changement nécessaire

3. **Les utilisateurs doivent avoir des rôles**
   - Le système auto-assigne "viewer" par défaut
   - Voir `backend/app/core/permissions.py` pour les détails

4. **Protection multi-tenant**
   - Les données sont filtrées par `account_id`
   - Un utilisateur ne voit que les accounts où il a des permissions

## 🧪 Tests recommandés

Après avoir appliqué les politiques:

1. **Test backend** : Vérifiez que toutes les routes API fonctionnent
2. **Test frontend** : Connectez-vous avec un utilisateur normal
3. **Test permissions** : Vérifiez que les utilisateurs ne voient que leurs données
4. **Test webhooks** : Vérifiez que les webhooks WhatsApp fonctionnent

## 🔧 Désactiver temporairement RLS

Si vous devez désactiver RLS sur une table (pour debug uniquement):

```sql
ALTER TABLE nom_table DISABLE ROW LEVEL SECURITY;
```

**⚠️ Ne jamais faire ça en production!**

## 📝 Notes de développement

- Les fonctions helper sont marquées `SECURITY DEFINER` pour avoir accès aux tables système
- Les fonctions sont `STABLE` pour optimisation des performances
- Les politiques utilisent des index existants pour de bonnes performances

## 🆘 Dépannage

### Problème: "permission denied" sur toutes les requêtes

**Solution**: Vérifiez que:
1. L'utilisateur a un rôle assigné (au moins "viewer")
2. L'utilisateur est actif dans `app_users`
3. Le rôle a les permissions nécessaires

### Problème: Le backend ne fonctionne plus

**Solution**: Vérifiez que:
1. `SUPABASE_KEY` dans le backend est bien la service_role key
2. Le backend utilise bien `create_client(url, service_role_key)`

### Problème: Les webhooks ne fonctionnent plus

**Solution**: Les webhooks utilisent le backend qui a service_role, donc ils devraient fonctionner. Vérifiez:
1. Les logs du backend
2. La configuration Supabase
3. Les permissions du service_role

