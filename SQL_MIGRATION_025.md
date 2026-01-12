# Migration SQL 025 - Pending Template Messages

## Fichier de migration
`supabase/migrations/025_pending_template_messages.sql`

## SQL à exécuter dans Supabase

Copiez-collez ce SQL dans l'éditeur SQL de Supabase :

```sql
-- Migration pour gérer les templates en attente de validation Meta
-- Permet de créer automatiquement des templates et d'attendre leur validation

-- Table pour suivre les templates en attente
CREATE TABLE IF NOT EXISTS pending_template_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  account_id UUID REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  template_name TEXT NOT NULL,
  template_status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
  text_content TEXT NOT NULL,
  meta_template_id TEXT, -- ID retourné par Meta
  rejection_reason TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Index pour les recherches fréquentes
CREATE INDEX IF NOT EXISTS idx_pending_templates_status 
ON pending_template_messages(template_status) 
WHERE template_status = 'PENDING';

CREATE INDEX IF NOT EXISTS idx_pending_templates_message 
ON pending_template_messages(message_id);

CREATE INDEX IF NOT EXISTS idx_pending_templates_meta_id 
ON pending_template_messages(meta_template_id) 
WHERE meta_template_id IS NOT NULL;

-- S'assurer que error_message existe dans messages (au cas où la migration 014 n'a pas été appliquée)
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Commentaires pour la documentation
COMMENT ON TABLE pending_template_messages IS 'Table pour suivre les templates créés automatiquement en attente de validation Meta';
COMMENT ON COLUMN pending_template_messages.template_status IS 'Statut du template: PENDING (en attente), APPROVED (approuvé), REJECTED (rejeté)';
COMMENT ON COLUMN pending_template_messages.meta_template_id IS 'ID du template retourné par l''API Meta';
COMMENT ON COLUMN pending_template_messages.rejection_reason IS 'Raison du rejet si le template est rejeté par Meta';
```

## Vérification

Après avoir exécuté la migration, vérifiez que la table existe :

```sql
SELECT * FROM pending_template_messages LIMIT 1;
```

Si vous obtenez une erreur "relation does not exist", la table n'a pas été créée. Vérifiez les logs d'erreur dans Supabase.

## Notes importantes

- Cette migration est idempotente (peut être exécutée plusieurs fois sans problème)
- La colonne `error_message` sera ajoutée à `messages` si elle n'existe pas déjà
- Les index sont créés uniquement s'ils n'existent pas déjà

