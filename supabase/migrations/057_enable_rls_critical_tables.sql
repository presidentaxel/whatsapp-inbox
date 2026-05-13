-- ============================================
-- Migration 057 : Active RLS sur les tables critiques exposées
-- ============================================
-- Contexte : l'advisor Supabase signale ERROR « rls_disabled_in_public »
-- pour 4 tables WhatsApp Inbox publiquement exposées via PostgREST mais
-- sans RLS :
--   - audit_log               (4643 rows, journal d'audit)
--   - qa_pairs                (1413 rows, base de connaissances RAG)
--   - playground_flows        (9 rows, graphes React Flow)
--   - playground_assist_threads (40 rows, fils assistant IA)
--   - playground_scheduled_flow_launches (14 rows, planifications)
--
-- Cette migration active RLS et pose des policies cohérentes avec le
-- système RBAC existant (cf. 005_rbac.sql / 012_new_permission_system.sql).
--
-- Pattern : service_role bypass + auth.uid() pour propriétaire +
-- user_has_*_permission() pour le contrôle RBAC par compte.
--
-- IMPORTANT avant déploiement :
-- 1. Vérifier que toutes les requêtes frontend utilisent un JWT
--    authentifié (pas la clé `anon` brute).
-- 2. Tester sur staging d'abord - RLS activée sans policy = blocage total.
-- 3. Le backend (service_role) bypass RLS, donc les jobs n'auront pas de
--    régression.
-- ============================================

-- ============================================
-- 1. audit_log
-- ============================================
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- SELECT : service_role OU admin global (accounts.manage)
DROP POLICY IF EXISTS "audit_log_select" ON audit_log;
CREATE POLICY "audit_log_select" ON audit_log
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND user_has_global_permission('accounts.manage')
    )
  );

-- INSERT : service_role uniquement (le backend log les actions)
DROP POLICY IF EXISTS "audit_log_insert" ON audit_log;
CREATE POLICY "audit_log_insert" ON audit_log
  FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

-- Pas de policy UPDATE/DELETE => audit log immuable côté API.
-- Le service_role peut toujours bypass RLS pour les opérations
-- de maintenance/migration.

-- ============================================
-- 2. qa_pairs (base de connaissances Axelia)
-- ============================================
ALTER TABLE qa_pairs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "qa_pairs_select" ON qa_pairs;
CREATE POLICY "qa_pairs_select" ON qa_pairs
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('axelia.access')
        OR user_has_account_permission('axelia.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "qa_pairs_insert" ON qa_pairs;
CREATE POLICY "qa_pairs_insert" ON qa_pairs
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('axelia.access')
        OR user_has_account_permission('axelia.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "qa_pairs_update" ON qa_pairs;
CREATE POLICY "qa_pairs_update" ON qa_pairs
  FOR UPDATE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('axelia.access')
        OR user_has_account_permission('axelia.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "qa_pairs_delete" ON qa_pairs;
CREATE POLICY "qa_pairs_delete" ON qa_pairs
  FOR DELETE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND (
        user_has_global_permission('axelia.access')
        OR user_has_account_permission('axelia.access', account_id)
      )
    )
  );

-- ============================================
-- 3. playground_flows
-- ============================================
ALTER TABLE playground_flows ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "playground_flows_select" ON playground_flows;
CREATE POLICY "playground_flows_select" ON playground_flows
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

DROP POLICY IF EXISTS "playground_flows_insert" ON playground_flows;
CREATE POLICY "playground_flows_insert" ON playground_flows
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

DROP POLICY IF EXISTS "playground_flows_update" ON playground_flows;
CREATE POLICY "playground_flows_update" ON playground_flows
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

DROP POLICY IF EXISTS "playground_flows_delete" ON playground_flows;
CREATE POLICY "playground_flows_delete" ON playground_flows
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

-- ============================================
-- 4. playground_assist_threads
--    Threads d'assistant IA = privés à l'utilisateur qui les a créés.
-- ============================================
ALTER TABLE playground_assist_threads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "playground_assist_threads_select" ON playground_assist_threads;
CREATE POLICY "playground_assist_threads_select" ON playground_assist_threads
  FOR SELECT
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND user_id = auth.uid()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "playground_assist_threads_insert" ON playground_assist_threads;
CREATE POLICY "playground_assist_threads_insert" ON playground_assist_threads
  FOR INSERT
  WITH CHECK (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND user_id = auth.uid()
      AND (
        user_has_global_permission('playground.access')
        OR user_has_account_permission('playground.access', account_id)
      )
    )
  );

DROP POLICY IF EXISTS "playground_assist_threads_update" ON playground_assist_threads;
CREATE POLICY "playground_assist_threads_update" ON playground_assist_threads
  FOR UPDATE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS "playground_assist_threads_delete" ON playground_assist_threads;
CREATE POLICY "playground_assist_threads_delete" ON playground_assist_threads
  FOR DELETE
  USING (
    auth.role() = 'service_role'
    OR (
      is_user_active()
      AND user_id = auth.uid()
    )
  );

-- ============================================
-- 5. playground_scheduled_flow_launches
-- ============================================
ALTER TABLE playground_scheduled_flow_launches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "playground_scheduled_flow_launches_select" ON playground_scheduled_flow_launches;
CREATE POLICY "playground_scheduled_flow_launches_select" ON playground_scheduled_flow_launches
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

DROP POLICY IF EXISTS "playground_scheduled_flow_launches_insert" ON playground_scheduled_flow_launches;
CREATE POLICY "playground_scheduled_flow_launches_insert" ON playground_scheduled_flow_launches
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

DROP POLICY IF EXISTS "playground_scheduled_flow_launches_update" ON playground_scheduled_flow_launches;
CREATE POLICY "playground_scheduled_flow_launches_update" ON playground_scheduled_flow_launches
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

DROP POLICY IF EXISTS "playground_scheduled_flow_launches_delete" ON playground_scheduled_flow_launches;
CREATE POLICY "playground_scheduled_flow_launches_delete" ON playground_scheduled_flow_launches
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
