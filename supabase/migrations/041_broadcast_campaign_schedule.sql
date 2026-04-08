-- Planification d'envoi des campagnes broadcast
ALTER TABLE broadcast_campaigns
  ADD COLUMN IF NOT EXISTS scheduled_for timestamptz NULL;

ALTER TABLE broadcast_campaigns
  ADD COLUMN IF NOT EXISTS schedule_status text NOT NULL DEFAULT 'done';

COMMENT ON COLUMN broadcast_campaigns.scheduled_for IS 'Si défini avec schedule_status=scheduled, envoi déclenché quand scheduled_for <= maintenant (UTC).';
COMMENT ON COLUMN broadcast_campaigns.schedule_status IS 'done | scheduled | sending | failed';

CREATE INDEX IF NOT EXISTS idx_broadcast_campaigns_schedule_due
  ON broadcast_campaigns (scheduled_for)
  WHERE schedule_status = 'scheduled';
