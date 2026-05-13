-- État de session du moteur nodal (playground) par conversation + flux publié par compte

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS bot_flow_state jsonb DEFAULT NULL;

COMMENT ON COLUMN conversations.bot_flow_state IS
  'Session du bot nodal: current_node_id, awaiting_interactive_node_id, after_interactive_target, continue_from_node_id, last_interaction_at, waba_opt_in, variables';

ALTER TABLE bot_profiles
  ADD COLUMN IF NOT EXISTS published_playground_flow jsonb DEFAULT NULL;

COMMENT ON COLUMN bot_profiles.published_playground_flow IS
  'Graphe React Flow publié { nodes, edges } pour exécution webhook';
