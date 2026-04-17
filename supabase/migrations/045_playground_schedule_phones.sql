-- Lancement planifié : cible soit un groupe, soit une liste de numéros (sans groupe obligatoire).
ALTER TABLE playground_scheduled_flow_launches
  ALTER COLUMN broadcast_group_id DROP NOT NULL;

ALTER TABLE playground_scheduled_flow_launches
  ADD COLUMN IF NOT EXISTS schedule_recipient_phones jsonb;

COMMENT ON COLUMN playground_scheduled_flow_launches.schedule_recipient_phones IS
  'Si renseigné : tableau de numéros normalisés ; sinon utiliser broadcast_group_id.';

COMMENT ON TABLE playground_scheduled_flow_launches IS
  'À scheduled_for : exécute try_run_playground_flow(scheduled_flow_launch) pour chaque destinataire (groupe ou liste).';
