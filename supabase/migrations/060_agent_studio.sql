-- Agent Studio: configuration orientée opérations + releases
-- Source de vérité SQL pour la nouvelle page /agent-studio.

CREATE TABLE IF NOT EXISTS agent_studio_configs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  version text NOT NULL DEFAULT 'v1',
  config jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_default boolean NOT NULL DEFAULT false,
  created_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  updated_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_studio_default_per_account
  ON agent_studio_configs(account_id)
  WHERE is_default = true;

CREATE INDEX IF NOT EXISTS idx_agent_studio_configs_account_updated
  ON agent_studio_configs(account_id, updated_at DESC);

COMMENT ON TABLE agent_studio_configs IS
  'Configurations Agent Studio (version v1) pilotées par compte.';

CREATE TABLE IF NOT EXISTS agent_studio_releases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  agent_config_id uuid NOT NULL REFERENCES agent_studio_configs(id) ON DELETE CASCADE,
  release_mode text NOT NULL CHECK (release_mode IN ('canary', 'activate', 'pause')),
  config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  notes text NOT NULL DEFAULT '',
  created_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_studio_releases_config_created
  ON agent_studio_releases(agent_config_id, created_at DESC);

ALTER TABLE agent_studio_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_studio_releases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent_studio_configs_select" ON agent_studio_configs;
CREATE POLICY "agent_studio_configs_select" ON agent_studio_configs
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "agent_studio_configs_insert" ON agent_studio_configs;
CREATE POLICY "agent_studio_configs_insert" ON agent_studio_configs
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "agent_studio_configs_update" ON agent_studio_configs;
CREATE POLICY "agent_studio_configs_update" ON agent_studio_configs
  FOR UPDATE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "agent_studio_configs_delete" ON agent_studio_configs;
CREATE POLICY "agent_studio_configs_delete" ON agent_studio_configs
  FOR DELETE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "agent_studio_releases_select" ON agent_studio_releases;
CREATE POLICY "agent_studio_releases_select" ON agent_studio_releases
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "agent_studio_releases_insert" ON agent_studio_releases;
CREATE POLICY "agent_studio_releases_insert" ON agent_studio_releases
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );
