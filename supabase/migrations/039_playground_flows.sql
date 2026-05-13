-- Flux Playground multiples par compte WABA + défaut + liaison conversation

CREATE TABLE IF NOT EXISTS playground_flows (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  name text NOT NULL DEFAULT 'Sans titre',
  graph jsonb NOT NULL DEFAULT '{"nodes":[],"edges":[],"v":2}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_playground_flows_account ON playground_flows(account_id);

COMMENT ON TABLE playground_flows IS 'Graphes React Flow (nodes/edges) par compte WhatsApp ; plusieurs logiques / starters par compte';

ALTER TABLE bot_profiles
  ADD COLUMN IF NOT EXISTS default_playground_flow_id uuid REFERENCES playground_flows(id) ON DELETE SET NULL;

COMMENT ON COLUMN bot_profiles.default_playground_flow_id IS 'Flux playground utilisé par défaut pour les conv sans playground_flow_id';

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS playground_flow_id uuid REFERENCES playground_flows(id) ON DELETE SET NULL;

COMMENT ON COLUMN conversations.playground_flow_id IS 'Flux playground dédié à cette conversation (sinon défaut du compte)';

-- Rétrocompat : migrer published_playground_flow vers une ligne playground_flows
DO $$
DECLARE
  r RECORD;
  new_id uuid;
BEGIN
  FOR r IN
    SELECT account_id, published_playground_flow
    FROM bot_profiles
    WHERE published_playground_flow IS NOT NULL
      AND default_playground_flow_id IS NULL
      AND jsonb_typeof(published_playground_flow) = 'object'
      AND published_playground_flow ? 'nodes'
  LOOP
    INSERT INTO playground_flows (account_id, name, graph)
    VALUES (r.account_id, 'Flux principal', r.published_playground_flow)
    RETURNING id INTO new_id;

    UPDATE bot_profiles
    SET default_playground_flow_id = new_id
    WHERE account_id = r.account_id;
  END LOOP;
END $$;
