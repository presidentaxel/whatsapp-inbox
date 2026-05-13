-- Lancement programmé du graphe playground pour les membres d'un groupe (sans message « broadcast » séparé).
CREATE TABLE IF NOT EXISTS playground_scheduled_flow_launches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  playground_flow_id uuid NOT NULL REFERENCES playground_flows(id) ON DELETE CASCADE,
  broadcast_group_id uuid NOT NULL REFERENCES broadcast_groups(id) ON DELETE CASCADE,
  entry_node_id text NOT NULL,
  scheduled_for timestamptz NOT NULL,
  schedule_status text NOT NULL DEFAULT 'scheduled',
  created_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pg_sched_flow_launch_due
  ON playground_scheduled_flow_launches (scheduled_for)
  WHERE schedule_status = 'scheduled';

COMMENT ON TABLE playground_scheduled_flow_launches IS 'À scheduled_for : exécute try_run_playground_flow(scheduled_flow_launch) pour chaque destinataire du groupe.';
