# Anciennes politiques RLS agrégées (`rls_policies.sql`)

Ce fichier est conservé **à titre historique**. Il contenait toutes les
politiques RLS WhatsApp Inbox sous forme d'un script unique à copier-coller
dans le SQL Editor du Dashboard.

**Cette pratique est dépréciée.** Le contenu a été intégré directement dans
`supabase/migrations/013_enable_rls_policies.sql`, qui est désormais la source
de vérité. Les évolutions ultérieures sont distribuées dans des migrations
dédiées (`014_message_reactions.sql`, `026_pending_template_messages_rls.sql`,
`035_broadcast_and_pinned_rls.sql`, `057_enable_rls_critical_tables.sql`, …).

Ne pas réappliquer ce fichier sur une base déjà migrée — risques de conflits.
