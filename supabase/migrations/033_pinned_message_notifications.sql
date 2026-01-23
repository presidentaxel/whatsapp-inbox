-- Migration: Créer la table pour les notifications d'épinglage en attente
-- Ces notifications sont mises en file d'attente quand on épingle un message hors de la fenêtre gratuite
-- et sont envoyées automatiquement quand la fenêtre gratuite revient

CREATE TABLE IF NOT EXISTS pinned_message_notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  notification_text TEXT NOT NULL,
  reply_to_message_id UUID REFERENCES messages(id),
  created_at TIMESTAMP DEFAULT NOW(),
  sent_at TIMESTAMP,
  status TEXT DEFAULT 'pending', -- 'pending', 'sent', 'failed'
  error_message TEXT,
  retry_count INT DEFAULT 0,
  last_retry_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pinned_notifications_pending 
  ON pinned_message_notifications(conversation_id, status) 
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pinned_notifications_message 
  ON pinned_message_notifications(message_id);

CREATE INDEX IF NOT EXISTS idx_pinned_notifications_created_at 
  ON pinned_message_notifications(created_at);

COMMENT ON TABLE pinned_message_notifications IS 
  'Notifications d''épinglage en attente d''envoi quand la fenêtre gratuite revient';

COMMENT ON COLUMN pinned_message_notifications.status IS 
  'Statut: pending (en attente), sent (envoyé), failed (échoué)';

