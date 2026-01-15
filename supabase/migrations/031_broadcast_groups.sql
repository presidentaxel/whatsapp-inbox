-- Migration: Tables pour les groupes de diffusion et statistiques
-- Date: 2024

-- Table pour les groupes de diffusion
CREATE TABLE IF NOT EXISTS broadcast_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid REFERENCES whatsapp_accounts(id) ON DELETE CASCADE NOT NULL,
  name text NOT NULL,
  description text,
  created_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  created_at timestamp DEFAULT now(),
  updated_at timestamp DEFAULT now()
);

-- Table pour les destinataires d'un groupe
CREATE TABLE IF NOT EXISTS broadcast_group_recipients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id uuid REFERENCES broadcast_groups(id) ON DELETE CASCADE NOT NULL,
  contact_id uuid REFERENCES contacts(id) ON DELETE SET NULL,
  phone_number text NOT NULL,
  display_name text,
  created_at timestamp DEFAULT now(),
  UNIQUE(group_id, phone_number)
);

-- Table pour chaque campagne d'envoi groupé
CREATE TABLE IF NOT EXISTS broadcast_campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id uuid REFERENCES broadcast_groups(id) ON DELETE CASCADE NOT NULL,
  account_id uuid REFERENCES whatsapp_accounts(id) ON DELETE CASCADE NOT NULL,
  content_text text NOT NULL,
  message_type text DEFAULT 'text',
  media_url text,
  sent_by uuid REFERENCES app_users(user_id) ON DELETE SET NULL,
  sent_at timestamp DEFAULT now(),
  total_recipients int DEFAULT 0,
  -- Stats calculées (mis à jour en temps réel)
  sent_count int DEFAULT 0,
  delivered_count int DEFAULT 0,
  read_count int DEFAULT 0,
  replied_count int DEFAULT 0,
  failed_count int DEFAULT 0
);

-- Table pour le suivi individuel de chaque destinataire
CREATE TABLE IF NOT EXISTS broadcast_recipient_stats (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campaign_id uuid REFERENCES broadcast_campaigns(id) ON DELETE CASCADE NOT NULL,
  recipient_id uuid REFERENCES broadcast_group_recipients(id) ON DELETE CASCADE NOT NULL,
  phone_number text NOT NULL,
  message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
  -- Statuts WhatsApp
  sent_at timestamp,
  delivered_at timestamp,
  read_at timestamp,
  failed_at timestamp,
  error_message text,
  -- Réponse
  replied_at timestamp,
  reply_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
  -- Métriques calculées
  time_to_read interval,
  time_to_reply interval,
  created_at timestamp DEFAULT now()
);

-- Index pour performance
CREATE INDEX IF NOT EXISTS idx_broadcast_groups_account ON broadcast_groups(account_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_groups_created_by ON broadcast_groups(created_by);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_group ON broadcast_group_recipients(group_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipients_phone ON broadcast_group_recipients(phone_number);
CREATE INDEX IF NOT EXISTS idx_broadcast_campaigns_group ON broadcast_campaigns(group_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_campaigns_account ON broadcast_campaigns(account_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_campaigns_sent_at ON broadcast_campaigns(sent_at);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_campaign ON broadcast_recipient_stats(campaign_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_recipient ON broadcast_recipient_stats(recipient_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_phone ON broadcast_recipient_stats(phone_number);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_message ON broadcast_recipient_stats(message_id);
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_read ON broadcast_recipient_stats(read_at) WHERE read_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_broadcast_recipient_stats_replied ON broadcast_recipient_stats(replied_at) WHERE replied_at IS NOT NULL;

-- Commentaires pour documentation
COMMENT ON TABLE broadcast_groups IS 'Groupes de diffusion pour envoi groupé de messages';
COMMENT ON TABLE broadcast_group_recipients IS 'Destinataires associés à un groupe de diffusion';
COMMENT ON TABLE broadcast_campaigns IS 'Campagnes d''envoi groupé avec statistiques agrégées';
COMMENT ON TABLE broadcast_recipient_stats IS 'Statistiques individuelles pour chaque destinataire d''une campagne';

