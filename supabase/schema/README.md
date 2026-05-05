# Schéma SQL - source de vérité

Les fichiers historiques `001_*.sql` … `015_*.sql` qui vivaient ici ont été **déplacés** vers [`../archive/legacy-schema-sql/`](../archive/legacy-schema-sql/) : ils avaient déjà été fusionnés dans la migration [`../migrations/001_baseline_legacy_schema.sql`](../migrations/001_baseline_legacy_schema.sql) (voir l’en-tête de ce fichier).

**À utiliser pour reproduire ou faire évoluer la base :**

- [`../migrations/`](../migrations/) - chaîne officielle appliquée par `supabase db reset` / CI.
- [`../policies/`](../policies/) - politiques RLS documentées (certaines sont aussi appliquées via des migrations).

Pour la cartographie des tables **WhatsApp Inbox** sur le projet Supabase **LMDCVTC**, voir [`../../docs/equipe/schema-lmdcvtc-inbox.md`](../../docs/equipe/schema-lmdcvtc-inbox.md).

Pour une refonte complète des migrations (squash, alignement remote), voir [`../../docs/equipe/supabase-source-of-truth.md`](../../docs/equipe/supabase-source-of-truth.md).
