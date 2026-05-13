-- Correctif Agent Studio:
-- 1) sécurise les policies sur la permission dédiée `agent_studio.access`
-- 2) évite les notices "relation does not exist" en gardant des guards explicites
-- 3) rend la migration idempotente si exécutée dans un environnement partiellement migré

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

ALTER TABLE agent_studio_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_studio_releases ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF to_regclass('public.agent_studio_configs') IS NOT NULL THEN
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_configs_select" ON public.agent_studio_configs';
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_configs_insert" ON public.agent_studio_configs';
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_configs_update" ON public.agent_studio_configs';
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_configs_delete" ON public.agent_studio_configs';
  END IF;

  IF to_regclass('public.agent_studio_releases') IS NOT NULL THEN
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_releases_select" ON public.agent_studio_releases';
    EXECUTE 'DROP POLICY IF EXISTS "agent_studio_releases_insert" ON public.agent_studio_releases';
  END IF;
END $$;

CREATE POLICY "agent_studio_configs_select" ON agent_studio_configs
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

CREATE POLICY "agent_studio_configs_insert" ON agent_studio_configs
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

CREATE POLICY "agent_studio_configs_update" ON agent_studio_configs
  FOR UPDATE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

CREATE POLICY "agent_studio_configs_delete" ON agent_studio_configs
  FOR DELETE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

CREATE POLICY "agent_studio_releases_select" ON agent_studio_releases
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

CREATE POLICY "agent_studio_releases_insert" ON agent_studio_releases
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('agent_studio.access')
        OR user_has_account_permission('agent_studio.access', account_id)
      )
    )
  );

