# Supabase : source de vérité et « remise à zéro » des migrations

## Où est la vérité dans ce dépôt ?


| Emplacement                               | Rôle                                                                                                         |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `**supabase/migrations/*.sql**`           | Historique **officiel** appliqué par `supabase db reset`, déploiements et CI. Source unique de vérité (schéma + RLS). |
| `**supabase/archive/legacy-schema-sql/`** | Anciens scripts qui étaient dans `supabase/schema/` - **ne plus exécuter** sur une base déjà migrée.         |
| `**supabase/archive/legacy-policies/`**   | Ancien `rls_policies.sql` agrégé - intégré dans `migrations/013_enable_rls_policies.sql`.                    |
| `**supabase/schema/README.md`**           | Point d’entrée : renvoie vers migrations + doc schéma.                                                       |


Les anciens fichiers `supabase/schema/*.sql` dupliquaient le contenu déjà fusionné dans `001_baseline_legacy_schema.sql` ; ils ont été archivés pour éviter toute ambiguïté (« quel fichier appliquer ? »).

### Correctif d’ordre (2026-02)

La migration `**016_add_header_media_id.sql`** modifiait `pending_template_messages` **avant** la migration `**025_pending_template_messages.sql`** (ordre lexicographique des noms de fichiers). Sur une base vide, cela pouvait faire échouer `db reset`. La colonne `header_media_id` a été **fusionnée dans `025_pending_template_messages.sql`** et le fichier `016_add_header_media_id.sql` a été supprimé.

---

## « Remettre à zéro » les migrations **dans le code** (squash)

Objectif typique : une seule migration initiale lisible, ou se réaligner sur un état Postgres connu.

**Préambule important** : le projet Supabase **LMDCVTC** héberge aussi des tables **VTC / Bolt / Uber / Heetch / Tesla** (voir [schema-lmdcvtc-inbox.md](./schema-lmdcvtc-inbox.md)). Un `supabase db pull` ou un `pg_dump` **sans filtre** mélangerait tout dans le dépôt **whatsapp-inbox**. Ne squash que ce qui correspond au **périmètre inbox** (ou acceptez d’élargir le périmètre produit du repo).

### Procédure recommandée (machine locale)

1. **Branche Git** dédiée (`chore/squash-supabase-migrations`).
2. Lier le projet si besoin : `supabase link --project-ref <ref>`.
3. Partir d’une base **vide** locale et rejouer l’historique actuel jusqu’à vérifier que tout passe :
  `supabase db reset`  
   Corriger toute erreur d’ordre ou de dépendance avant de squasher.
4. Produire un dump **schéma seulement** depuis cette base locale à jour (exemple avec `pg_dump`, variables `PGHOST` / mot de passe depuis le dashboard Supabase **local** après reset) :
  `pg_dump --schema-only --no-owner --no-privileges -n public … > baseline.sql`  
   Puis **éditer** `baseline.sql` pour retirer tout objet hors périmètre (tables Bolt, etc.) si la base locale les contenait.
5. Déplacer l’ancien dossier `supabase/migrations/` vers `supabase/migrations_archive/<date>-pre-squash/` (conserver l’historique Git si vous supprimez des fichiers : le squash est plus lisible dans un commit dédié).
6. Créer **une** nouvelle migration datée :
  `supabase migration new baseline_whatsapp_inbox`  
   Coller le SQL nettoyé, puis vérifier : `supabase db reset` sur clone propre.
7. Mettre à jour la doc ([schema-lmdcvtc-inbox.md](./schema-lmdcvtc-inbox.md)) si des colonnes ou tables changent.

### Ce qu’il ne faut pas faire sans réfléchir

- `**supabase db reset` sur la production** : détruit les données sauf si vous savez exactement ce que vous faites.
- **Supprimer l’historique des migrations** sur une branche déjà mergée sans coordonner l’équipe : les environnements qui ont appliqué l’ancien historique ne peuvent pas « revenir » en arrière proprement sans migration de transition.
- **Copier tout le schéma LMDCVTC** dans ce repo si vous ne voulez pas maintenir les tables VTC ici.

---

## Aligner le **remote** sur le code (ou l’inverse)

- **Code → remote** : `supabase db push` (ou pipelines internes) après avoir validé `db reset` localement.
- **Remote → code** : préférer un dump **filtré** ou des migrations générées à la main pour les écarts ponctuels ; un `pull` global d’un projet multi-domaine enferme plusieurs produits dans le même dépôt.

Pour toute opération destructive sur le projet cloud, passer par une **sauvegarde** (point-in-time, export) depuis le dashboard Supabase avant.