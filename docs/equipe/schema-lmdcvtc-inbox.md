# Schéma Supabase - projet **LMDCVTC** (tables **WhatsApp Inbox**)

Document généré à partir du schéma **`public`** du projet Supabase nommé **LMDCVTC** (`project_ref` / id : `txsblxqismjlsgsojdvc`, région `eu-north-1`, Postgres **17**).  
Les détails colonnes / PK / FK proviennent de l’inspection API (équivalent `list_tables` verbose).

> **Attention** : la même base `public` contient aussi des tables **VTC / agrégats** (Bolt, Uber, Heetch, Tesla, etc.) listées en fin de page. Elles ne font **pas** partie du périmètre applicatif de ce dépôt **whatsapp-inbox** ; ne les confondez pas avec le modèle inbox.

---

## Tables cœur **conversation WhatsApp**

| Table | RLS | Lignes (ordre de grandeur au moment de l’export) | Rôle |
|--------|-----|--------------------------------------------------|------|
| `whatsapp_accounts` | oui | ~10 | Lignes Business (tokens, `phone_number_id`, `waba_id`, intégrations optionnelles Google Drive / Evolution). |
| `contacts` | oui | ~1,6k | Contacts uniques par numéro WhatsApp. |
| `conversations` | oui | ~1,7k | Fils par `account_id` + `client_number`, bot, flux playground, favoris, non-lus. |
| `messages` | oui | ~20k | Messages (direction, `wa_message_id`, médias, templates, coûts, `sent_via`, transcription audio, etc.). |
| `message_reactions` | oui | ~337 | Réactions emoji. |

**FK principales** : `conversations` → `contacts`, `whatsapp_accounts` ; `messages` → `conversations` ; réactions → `messages`.

---

## Rôles, permissions, accès multi-compte

| Table | RLS | Rôle |
|--------|-----|------|
| `app_users` | oui | Profil opérateur (`user_id` = auth). |
| `app_roles`, `app_permissions`, `role_permissions` | oui | RBAC. |
| `app_user_roles`, `app_user_overrides` | oui | Rôle et overrides par compte WhatsApp. |
| `user_account_access` | oui | Niveau d’accès `full` / `lecture` / `aucun` par utilisateur et compte. |
| `user_chat_settings` | oui | Préférences UI (thème, etc.). |

---

## Bot, playground, Axelia, FAQ

| Table | RLS | Rôle |
|--------|-----|------|
| `bot_profiles` | oui | Contexte entreprise, base de connaissances, graphe playground publié, `default_playground_flow_id`, `style_guide`. |
| `playground_flows` | non | Graphes JSON par compte. |
| `playground_assist_threads` | non | Discussions assistant éditeur de flux. |
| `playground_scheduled_flow_launches` | non | Lancement planifié de flux sur un groupe broadcast. |
| `qa_pairs` | non | Paires Q/R + embedding vector (RAG) par compte. |
| `axelia_conversations`, `axelia_messages` | oui | Fils assistant Axelia (Gemini), votes, `focus_tag`. |

---

## Templates, médias, broadcast

| Table | RLS | Rôle |
|--------|-----|------|
| `pending_template_messages` | oui | Templates en attente Meta (statut, hash, campagne, `header_media_id`, etc.). |
| `template_media` | oui | Fichiers d’en-tête template en Storage. |
| `broadcast_groups`, `broadcast_group_recipients` | oui | Groupes et destinataires. |
| `broadcast_campaigns`, `broadcast_recipient_stats` | oui | Campagnes et stats par destinataire. |
| `pinned_message_notifications` | oui | Notifications d’épinglage différées. |

---

## Webhook, audit, blocage

| Table | RLS | Rôle |
|--------|-----|------|
| `webhook_events` | oui | File durable des webhooks (statut, retries, dédup `signature_id`). |
| `audit_log` | non | Journal d’actions (traçabilité). |
| `internal_contact_blocks` | oui | Ban in-app par contact + compte. |

---

## Tables présentes sur **LMDCVTC** mais hors périmètre **whatsapp-inbox**

À ne pas traiter comme « schéma officiel » de ce dépôt sauf décision produit explicite :

- **Bolt** : `bolt_drivers`, `bolt_orders`, `bolt_organizations`, `bolt_state_logs`, `bolt_vehicles`, `bolt_earnings`, `bolt_trips`
- **Tesla** : `tesla_accounts`, `vehicles`, `vehicle_data_cache`, `tokens`
- **Heetch** : `heetch_drivers`, `heetch_earnings`, `heetch_session_cookies`
- **Uber** : `uber_drivers`, `uber_organizations`, `uber_vehicles`, `comptes_uber`
- **Analytics / plateforme** : `users` (comptes plateforme avec `org_id`), `daily_analytics`, `user_analytics`, `driver_daily_metrics`, `driver_payments`

Ces tables partagent souvent la notion d’**`org_id`** (multi-organisation VTC), distincte des comptes **`whatsapp_accounts`**.

---

## Revoir le détail colonne par colonne

1. Dashboard Supabase → **Table Editor** sur le projet LMDCVTC.  
2. Ou en local après `supabase db reset` : introspection via `information_schema` / outils IDE.  
3. Chaîne de migrations dans ce dépôt : [`../../supabase/migrations/`](../../supabase/migrations/).

Pour la politique migrations / squash / risques : [supabase-source-of-truth.md](./supabase-source-of-truth.md).
