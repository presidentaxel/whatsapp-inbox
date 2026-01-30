# Optimisation base de données (PostgreSQL direct)

## Vue d'ensemble

Le backend peut utiliser **PostgreSQL en direct** (via `asyncpg`) au lieu de l'API Supabase (PostgREST) pour les requêtes métier. Cela réduit la latence, évite le blocage du thread pool et permet à plusieurs requêtes de s'exécuter en parallèle sans se bloquer.

## Activation

1. **Récupérer l’URL de connexion PostgreSQL (pooler)**  
   Dans le dashboard Supabase : **Project Settings → Database** → onglet **Connection string**.  
   **Ne pas utiliser** « Direct connection » (`db.xxx.supabase.co`) : ce host ne résout souvent pas en DNS depuis l’extérieur.  
   Choisir **Connection pooling** → mode **Session** ou **Transaction** → copier l’URL.  
   Format attendu : `postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres` (port **6543**, host en `.pooler.supabase.com`).

2. **Définir la variable d’environnement**  
   Dans ton `.env` (racine du repo ou `backend/.env`) :
   ```env
   DATABASE_URL=postgresql://postgres.xxxx:YYYY@aws-0-eu-west-3.pooler.supabase.com:6543/postgres
   ```

3. **Redémarrer le backend**  
   Au démarrage, le pool PostgreSQL est créé (min 5, max 20 connexions). Les chemins migrés utilisent alors le pool au lieu de l’API Supabase.

Si `DATABASE_URL` n’est pas défini, le backend continue d’utiliser uniquement l’API Supabase (comportement par défaut).

## Chemins migrés vers PostgreSQL direct

- **Conversations** : liste des conversations (une requête avec LATERAL pour le dernier message), détail, marquer lu/non lu, favori, mode bot.
- **Comptes** : `get_account_by_id` (avec cache).
- **Permissions** : chargement des rôles et permissions utilisateur (async, sans bloquer le thread pool).
- **Messages** :
  - `get_messages` : une requête messages + requêtes quoted et reactions en parallèle (`asyncio.gather`).
  - `get_message_by_id`, `update_message_content`, `delete_message_scope`, `add_reaction`, `remove_reaction`.
  - Galeries média (par conversation et par compte) en une seule requête.
- **Webhook** : mise à jour de statut des messages, recherche conversation par account+client_number, `_upsert_contact`, `_upsert_conversation`, `_update_conversation_timestamp`. Insertion des messages entrants (upsert avec RETURNING), recherche du message référencé (reply_to), réactions (add/remove). Incrément unread_count.
- **Envoi de messages** : texte (send_message, sauvegarde en arrière-plan), template (send_message_with_template_fallback), interactif (send_interactive_to_whatsapp), média (send_media_message_with_storage), image avec template queue (_send_image_with_template_queue). Message échoué (_save_failed_message).
- **Templates en attente** (`pending_template_service`) : insert/select/update/delete `pending_template_messages`, vérification statut Meta, envoi template approuvé, broadcast template, marquage message échoué, suppression template auto pour message lu.
- **Broadcast** (`broadcast_service`) : groupes (CRUD), destinataires (CRUD, liste avec join contacts), campagnes (CRUD, liste), envoi campagne (création messages fake, stats, compteurs), `create_recipient_stat`, `update_recipient_stat`, `update_recipient_stat_from_webhook`, `track_reply`, `update_campaign_counters`, `get_campaign_stats`, `get_campaign_heatmap`, `get_campaign_timeline`.
- **Template déduplication** (`template_deduplication`) : `find_existing_template`, `check_spam_risk`, inserts dans `pending_template_messages` (réutilisation template APPROVED/PENDING).
- **Contacts** (`contact_service`) : `list_contacts`.
- **Comptes** (`account_service`) : `get_all_accounts`, `get_account_by_verify_token`, `get_account_by_phone_number_id`, `ensure_default_account`, `create_account`, `update_account`, `delete_account`.
- **Stockage** (`storage_service`) : mise à jour `messages.storage_url` après upload média, `cleanup_old_media` (select + update messages), `upload_template_media` (upsert `template_media`), `get_template_media_url`. Les appels à Supabase Storage (upload/delete de fichiers) restent en thread pool.
- **Auth / Users** : mise à jour profil (`PUT /me`, `POST /me/profile-picture`) via `app_users` ; suppression utilisateur (`DELETE /admin/users/{id}`) via `app_user_roles`, `app_user_overrides`, `app_users`. Les invitations utilisent l’API Supabase Auth (admin) et ne passent pas par Postgres direct.

## Vérification

Au démarrage, les logs affichent soit :

- `PostgreSQL pool created (min=5, max=20)` si `DATABASE_URL` est défini et valide,
- `DATABASE_URL not set, skipping PostgreSQL pool init` sinon.

En cas d’erreur de connexion au pool, un warning est logué et le backend bascule automatiquement sur l’API Supabase.
