# Runbook Agent Studio

Ce runbook donne les opérations minimales pour activer, surveiller et dépanner `Agent Studio`.

## 1) Activer l'accès utilisateur

- Ouvrir `Paramètres` > accès Axelia/Playground/Agent Studio.
- Cocher `Accès Agent Studio` pour les utilisateurs autorisés.
- Vérifier côté UI que l'entrée `/agent-studio` apparaît dans le menu.

## 2) Déployer un agent en sécurité

- Sauvegarder le brouillon.
- Lancer `Valider (backend)`.
- Corriger les erreurs bloquantes (`severity=error`).
- Déployer en `canary` (ex: 10%).
- Vérifier les métriques (`/agent-studio/metrics`).
- Activer en `active` si les signaux sont bons.

## 3) Vérifier la santé

Endpoint:

- `GET /agent-studio/metrics`

Signaux clés:

- `validate_error_rate`: doit rester bas.
- `simulate_fallback_rate`: hausse = routage trop imprécis.
- `rollback_failure_rate`: doit rester proche de 0.

## 4) Dépannage rapide

Symptôme: menu `/agent-studio` absent.

- Vérifier permission effective: `agent_studio.access`.
- Vérifier rôle + overrides utilisateur.
- Vérifier que les migrations `061` et `062` sont appliquées.

Symptôme: activation/canary refusée.

- Lire le payload `config_not_deployable`.
- Corriger les erreurs de validation (tools unknown, approbations incohérentes, objectif manquant, etc.).

Symptôme: simulation tombe souvent en fallback.

- Revoir les `intents` (clés/description/handler).
- Ajuster `confidenceThreshold`.
- Ajouter des cas de test plus représentatifs.

