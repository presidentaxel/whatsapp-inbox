-- Blocage interne (app uniquement) par contact × compte WhatsApp - n'appelle pas Meta.
CREATE TABLE IF NOT EXISTS internal_contact_blocks (
  contact_id uuid NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (contact_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_internal_contact_blocks_account_id
  ON internal_contact_blocks(account_id);

COMMENT ON TABLE internal_contact_blocks IS
  'Ban in-app: les messages entrants restent stockés; l’UI ne permet pas de répondre.';
