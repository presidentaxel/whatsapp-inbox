-- Fils de discussion de l’assistant Playground (persistés par utilisateur / scénario)
-- hidden_at : masqué dans l’UI mais conservé pour audit / récupération

CREATE TABLE IF NOT EXISTS playground_assist_threads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  flow_id uuid NOT NULL REFERENCES playground_flows(id) ON DELETE CASCADE,
  title text NOT NULL DEFAULT 'Nouvelle discussion',
  messages jsonb NOT NULL DEFAULT '[]'::jsonb,
  hidden_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_playground_assist_threads_user_flow
  ON playground_assist_threads(user_id, flow_id)
  WHERE hidden_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_playground_assist_threads_flow
  ON playground_assist_threads(flow_id);

COMMENT ON TABLE playground_assist_threads IS 'Historique assistant IA éditeur Playground ; hidden_at masque sans supprimer';
COMMENT ON COLUMN playground_assist_threads.hidden_at IS 'Non null = retiré de la liste principale ; données conservées';
