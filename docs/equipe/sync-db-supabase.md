# Synchroniser le code avec la DB Supabase distante

Ce guide explique comment **réconcilier les migrations locales avec l'état réel
de la base Supabase distante**, par exemple après un travail effectué via le
Dashboard ou par un autre dev.

> **Projet** : `txsblxqismjlsgsojdvc` (cf. `supabase/config.toml`).

## 1. Pourquoi c'est subtil

Au fil du temps, le projet a accumulé plusieurs sources de divergence :

1. **Migrations appliquées hors `supabase/migrations/`** (Dashboard, scripts ad
   hoc). Elles sont dans la base mais pas dans le repo, ou inversement.
2. **Doublons de numéros** : deux fichiers `026_*` ou `051_*` sur disque, un
   seul enregistré dans `schema_migrations` côté remote.
3. **Tables d'autres applications** dans le même schéma `public` (Bolt, Tesla,
   Heetch, Uber…). Elles ne doivent **pas** être versionnées dans ce repo.

La règle fondamentale (cf. `docs/GUIDE_BONNES_PRATIQUES.md`) reste :

> Les fichiers dans `supabase/migrations/` sont **la source de vérité** du
> schéma applicatif. Le Dashboard est strictement réservé à l'inspection.

## 2. Branche dédiée + outils

```bash
git checkout -b chore/sync-db-from-remote
```

**Outils :**

- **Supabase CLI** (`npx supabase ...`) pour `db pull`, `migration repair`,
  `db push`. Nécessite `supabase login` et `supabase link --project-ref ...`.
- **MCP Supabase** (`plugin-supabase-supabase`) pour inspection read-only en
  cours de session :
  - `list_tables`, `list_migrations`, `get_advisors`, `execute_sql`.
- **MCP `apply_migration`** : applique un fichier SQL en l'enregistrant comme
  migration côté remote. À réserver aux cas où la CLI n'est pas pratique
  (réparation rapide, test).

## 3. Inspection avant tout changement

Avant de toucher à quoi que ce soit, vérifier l'état remote :

```bash
# Liste des migrations enregistrées côté remote
# (via MCP : list_migrations)

# Comparer avec le local :
ls supabase/migrations/ | sort
```

Lancer aussi les advisors Supabase (security + performance) - ils signalent les
tables sans RLS, les fonctions `SECURITY DEFINER` exposées, etc.

## 4. Renommer les collisions de numéros

Si plusieurs fichiers locaux partagent le même préfixe (`026_a.sql`,
`026_b.sql`), il faut conserver celui qui correspond au nom enregistré dans
`schema_migrations` distant et renommer les autres avec un numéro libre :

```bash
git mv supabase/migrations/026_template_deduplication.sql \
       supabase/migrations/055_template_deduplication.sql
git mv supabase/migrations/051_axelia_search_indexes.sql \
       supabase/migrations/056_axelia_search_indexes.sql
```

> Si la migration renommée a déjà été **appliquée** hors `supabase/migrations`
> (cas fréquent quand un dev a copié le SQL dans le Dashboard), il faut la
> marquer comme `applied` côté remote pour éviter qu'elle se rejoue :
>
> ```bash
> npx supabase migration repair --status applied 055 056
> ```

## 5. Détecter les divergences réelles

Une fois les collisions résolues, lance :

```bash
npx supabase login
npx supabase link --project-ref txsblxqismjlsgsojdvc
npx supabase db pull --schema public
```

`db pull` génère **un nouveau fichier** `supabase/migrations/<timestamp>_remote_schema.sql`
contenant le diff entre les migrations connues du remote et l'état réel du
schéma. Ce fichier peut être **gros** (52 tables sur ce projet).

**Filtrer ce qui n'est pas WhatsApp** :

Ce repo ne doit versionner que les tables de l'inbox WhatsApp. Les tables
suivantes appartiennent à d'autres apps et **doivent être supprimées** du diff
généré avant commit :

```
bolt_*, tesla_*, vehicles, vehicle_data_cache,
heetch_*, uber_*, comptes_uber,
daily_analytics, driver_*, user_analytics, users, tokens
```

Conserver dans le diff uniquement les tables WhatsApp Inbox :

```
app_*, audit_log, axelia_*, bot_profiles, broadcast_*,
contacts, conversations, internal_contact_blocks, message_reactions,
messages, pending_template_messages, pinned_message_notifications,
playground_*, qa_pairs, role_permissions, template_media,
user_account_access, user_chat_settings, webhook_events, whatsapp_accounts
```

## 6. Sécurité : tables sans RLS

L'advisor signale plusieurs tables `public.*` sans RLS (ERROR niveau sécurité).
Pour les tables WhatsApp Inbox, la migration
`057_enable_rls_critical_tables.sql` corrige ce point sur :

- `audit_log`
- `qa_pairs`
- `playground_flows`
- `playground_assist_threads`
- `playground_scheduled_flow_launches`

> **Avant déploiement** : tester sur un environnement staging. Une RLS
> activée sans policy bloque toutes les requêtes côté `anon`/`authenticated`.

## 7. Déploiement

```bash
# Sécurité : prod-dump avant push
npx supabase db dump --linked --schema public > _backup_$(date +%F).sql

# Push de la migration RLS et des fichiers renommés
npx supabase db push
```

Si une migration locale a déjà été appliquée hors `supabase/migrations`, la
marquer plutôt avec `migration repair --status applied <version>` que de la
rejouer.

## 8. Checklist post-sync

- [ ] `git status` : aucune migration en `??` ou `M` non commitée
- [ ] `npx supabase migration list` : versions locales == versions remote
- [ ] Advisors security : 0 ERROR sur tables WhatsApp
- [ ] CI/CD : `supabase db push --dry-run` passe
- [ ] Tests backend : `pytest` vert
- [ ] Frontend : pas de régression sur la console (RLS bloque pas l'UI)
