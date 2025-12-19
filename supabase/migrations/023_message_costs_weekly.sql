-- Migration pour ajouter le suivi des coûts des messages et un index par semaine
-- Permet de calculer les coûts totaux des envois groupés par semaine

-- Ajouter le champ cost à la table messages
ALTER TABLE messages
  ADD COLUMN IF NOT EXISTS cost DECIMAL(10, 6) DEFAULT 0.0,
  ADD COLUMN IF NOT EXISTS cost_currency TEXT DEFAULT 'USD';

-- Commentaire pour documenter
COMMENT ON COLUMN messages.cost IS 'Coût du message en USD (généralement 0 pour les messages conversationnels, 0.005-0.09 pour les templates selon le pays)';
COMMENT ON COLUMN messages.cost_currency IS 'Devise du coût (généralement USD)';

-- Créer un index sur la semaine pour optimiser les requêtes de coûts par semaine
-- Utilise date_trunc pour grouper par semaine (lundi comme premier jour de la semaine)
CREATE INDEX IF NOT EXISTS idx_messages_week_cost 
ON messages (
  date_trunc('week', timestamp),
  direction,
  cost
)
WHERE direction = 'outgoing' AND cost > 0;

-- Créer une vue pour calculer les coûts totaux par semaine
CREATE OR REPLACE VIEW message_costs_weekly AS
SELECT 
  date_trunc('week', timestamp)::date AS week_start,
  DATE_PART('year', date_trunc('week', timestamp)) AS year,
  DATE_PART('week', date_trunc('week', timestamp)) AS week_number,
  COUNT(*) FILTER (WHERE direction = 'outgoing') AS total_messages_sent,
  COUNT(*) FILTER (WHERE direction = 'outgoing' AND cost > 0) AS paid_messages_count,
  COALESCE(SUM(cost) FILTER (WHERE direction = 'outgoing'), 0) AS total_cost,
  COALESCE(AVG(cost) FILTER (WHERE direction = 'outgoing' AND cost > 0), 0) AS avg_cost_per_message,
  MIN(cost) FILTER (WHERE direction = 'outgoing' AND cost > 0) AS min_cost,
  MAX(cost) FILTER (WHERE direction = 'outgoing' AND cost > 0) AS max_cost
FROM messages
WHERE direction = 'outgoing'
GROUP BY date_trunc('week', timestamp)
ORDER BY week_start DESC;

-- Créer une vue pour les coûts par compte et par semaine
CREATE OR REPLACE VIEW message_costs_weekly_by_account AS
SELECT 
  c.account_id,
  wa.name AS account_name,
  date_trunc('week', m.timestamp)::date AS week_start,
  DATE_PART('year', date_trunc('week', m.timestamp)) AS year,
  DATE_PART('week', date_trunc('week', m.timestamp)) AS week_number,
  COUNT(*) FILTER (WHERE m.direction = 'outgoing') AS total_messages_sent,
  COUNT(*) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0) AS paid_messages_count,
  COALESCE(SUM(m.cost) FILTER (WHERE m.direction = 'outgoing'), 0) AS total_cost,
  COALESCE(AVG(m.cost) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0), 0) AS avg_cost_per_message
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
JOIN whatsapp_accounts wa ON c.account_id = wa.id
WHERE m.direction = 'outgoing'
GROUP BY c.account_id, wa.name, date_trunc('week', m.timestamp)
ORDER BY week_start DESC, account_name;

-- Fonction pour obtenir les coûts d'une semaine spécifique
CREATE OR REPLACE FUNCTION get_weekly_costs(
  p_week_start DATE DEFAULT NULL,
  p_account_id UUID DEFAULT NULL
)
RETURNS TABLE (
  week_start DATE,
  year INTEGER,
  week_number INTEGER,
  account_id UUID,
  account_name TEXT,
  total_messages_sent BIGINT,
  paid_messages_count BIGINT,
  total_cost DECIMAL,
  avg_cost_per_message DECIMAL
) AS $$
BEGIN
  IF p_account_id IS NOT NULL THEN
    RETURN QUERY
    SELECT 
      date_trunc('week', m.timestamp)::date AS week_start,
      DATE_PART('year', date_trunc('week', m.timestamp))::INTEGER AS year,
      DATE_PART('week', date_trunc('week', m.timestamp))::INTEGER AS week_number,
      c.account_id,
      wa.name AS account_name,
      COUNT(*) FILTER (WHERE m.direction = 'outgoing')::BIGINT AS total_messages_sent,
      COUNT(*) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0)::BIGINT AS paid_messages_count,
      COALESCE(SUM(m.cost) FILTER (WHERE m.direction = 'outgoing'), 0) AS total_cost,
      COALESCE(AVG(m.cost) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0), 0) AS avg_cost_per_message
    FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    JOIN whatsapp_accounts wa ON c.account_id = wa.id
    WHERE m.direction = 'outgoing'
      AND (p_week_start IS NULL OR date_trunc('week', m.timestamp)::date = p_week_start)
      AND c.account_id = p_account_id
    GROUP BY date_trunc('week', m.timestamp), c.account_id, wa.name
    ORDER BY week_start DESC;
  ELSE
    RETURN QUERY
    SELECT 
      date_trunc('week', m.timestamp)::date AS week_start,
      DATE_PART('year', date_trunc('week', m.timestamp))::INTEGER AS year,
      DATE_PART('week', date_trunc('week', m.timestamp))::INTEGER AS week_number,
      c.account_id,
      wa.name AS account_name,
      COUNT(*) FILTER (WHERE m.direction = 'outgoing')::BIGINT AS total_messages_sent,
      COUNT(*) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0)::BIGINT AS paid_messages_count,
      COALESCE(SUM(m.cost) FILTER (WHERE m.direction = 'outgoing'), 0) AS total_cost,
      COALESCE(AVG(m.cost) FILTER (WHERE m.direction = 'outgoing' AND m.cost > 0), 0) AS avg_cost_per_message
    FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    JOIN whatsapp_accounts wa ON c.account_id = wa.id
    WHERE m.direction = 'outgoing'
      AND (p_week_start IS NULL OR date_trunc('week', m.timestamp)::date = p_week_start)
    GROUP BY date_trunc('week', m.timestamp), c.account_id, wa.name
    ORDER BY week_start DESC;
  END IF;
END;
$$ LANGUAGE plpgsql;

-- Commentaires pour documenter les vues et fonctions
COMMENT ON VIEW message_costs_weekly IS 'Vue agrégée des coûts totaux des messages par semaine (tous comptes confondus)';
COMMENT ON VIEW message_costs_weekly_by_account IS 'Vue agrégée des coûts totaux des messages par semaine et par compte';
COMMENT ON FUNCTION get_weekly_costs IS 'Fonction pour obtenir les coûts hebdomadaires avec filtres optionnels par semaine et/ou compte';

