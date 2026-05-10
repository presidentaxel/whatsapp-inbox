# Runbook Agent Studio et mode Agent (inbox outbound)

Ce document décrit **Agent Studio** (fiche agent, déploiement, permissions) et le **noyau outbound** utilisé pour les réponses automatiques WhatsApp lorsque la boucle Gemini + outils est activée. Ce périmètre est **distinct d’Axelia** (hub conversationnel riche) : même moteur Gemini possible, mais orchestration, outils et garde-fous dédiés.

## 1. Interface et données

- **Route UI** : `/agent-studio` (desktop). Voir aussi `docs/pages/desktop-agent-studio.md`.
- **Permission** : `agent_studio.access` (menu et API associées).
- **Schéma** : migrations `060_agent_studio.sql` et suivantes dans `supabase/migrations/` (RLS, accès compte).

L’opérateur configure objectifs, ton, intents, **liste d’outils autorisés** (`capabilities.allowed_tools` dans la config JSON). Seul un agent **marqué défaut** et dont le déploiement est **`active` ou `canary`** est pris en compte pour les réponses inbox pilotées par Agent Studio.

## 2. Réponses inbox (WhatsApp)

Le backend appelle `generate_agent_studio_inbox_reply_with_confidence` dans `backend/app/services/bot_service.py` lorsque la conversation est en mode agent aligné sur la fiche compte (voir enchaînement dans `message_service`).

Prérequis côté serveur :

- `GEMINI_API_KEY` défini.
- Message utilisateur non vide.
- Ligne **agent par défaut** pour le compte, déploiement actif / canary.

Sinon la fonction renvoie une structure vide avec `confidence_reasons` explicites (pas d’agent, agent inactif, etc.).

## 3. Deux modes de génération

### 3.1 Mode texte seul (défaut)

Si `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` est **faux** (défaut), le playbook Agent Studio est injecté en **référence métier** : le modèle ne doit pas invoquer d’outils depuis le prompt classique ; génération directe type chat.

### 3.2 Mode boucle Gemini + outils (M2 / M3)

Si `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` est **vrai** et que la politique d’outils permet au moins un outil **du noyau lecture seule v1**, le backend utilise `run_agent_outbound_inbox_gemini_with_tools` (`backend/app/services/agent_outbound/loop.py`) :

- **M2** : premier passage modèle avec schéma `reply` + `tool_calls` ; exécution des appels via le noyau ; second passage pour la réponse client.
- **M3** (optionnel) : si `AGENT_OUTBOUND_REFLECTION_ENABLED` est **vrai**, un court passage « réflexion » qualité après les résultats d’outils, avant la synthèse finale.

Timeouts configurables : `AGENT_OUTBOUND_GEMINI_READ_TIMEOUT_S`, `AGENT_OUTBOUND_REFLECTION_READ_TIMEOUT_S`.

## 4. Politique d’outils (alignement M0 / M4)

- Le fichier `backend/app/services/agent_outbound/registry.py` définit **`AGENT_STUDIO_ALLOWLIST_SLUGS`**, qui doit rester **strictement aligné** sur `ALLOWED_AGENT_TOOLS` dans `agent_studio_service.py` (test de non-régression : `test_agent_outbound_allowlist_matches_agent_studio_allowed_tools`).
- **`AGENT_KERNEL_V1_READ_TOOLS`** : sous-ensemble **lecture seule** (exclut création de template, préparation d’en-tête image, blocage Meta, etc.). L’intersection avec `capabilities.allowed_tools` de la fiche donne la **liste effective** exposée au modèle en mode outils.
- **M4** : validation des arguments (forme, entiers stricts, slugs coercés), codes d’erreur stables `AgentOutboundToolErrorCode` pour logs et réinjection modèle.

Les outils sensibles côté métier (`SENSITIVE_AGENT_TOOLS` dans `agent_studio_service`) restent pertinents pour la **simulation / validation** Agent Studio ; le noyau outbound ne les exécute pas dans le périmètre lecture v1.

## 5. Variables d’environnement (backend)

Documentées dans `backend/.env.example` :

| Variable | Rôle |
| -------- | ---- |
| `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` | Active la boucle M2/M3 côté inbox Agent Studio. |
| `AGENT_OUTBOUND_GEMINI_READ_TIMEOUT_S` | Timeout lecture HTTP Gemini pour la boucle outils. |
| `AGENT_OUTBOUND_REFLECTION_ENABLED` | Active la passe réflexion M3. |
| `AGENT_OUTBOUND_REFLECTION_READ_TIMEOUT_S` | Timeout pour l’appel réflexion. |

## 6. Arborescence code utile

| Chemin | Rôle |
| ------ | ---- |
| `backend/app/services/agent_studio_service.py` | Config agent, outils autorisés côté produit, simulation de route. |
| `backend/app/services/agent_outbound/` | Catalogue, parsing JSON, noyau d’exécution, boucle Gemini. |
| `backend/app/services/bot_service.py` | `generate_agent_studio_inbox_reply_with_confidence`, formatage playbook. |
| `backend/app/api/routes_agent_studio.py` | API REST Agent Studio. |

## 7. Tests

- `backend/tests/test_agent_outbound_m0.py` … `m4.py` : jalons noyau, parsing, boucle mockée, sécurité args.
- `backend/tests/test_agent_studio_service.py` : alignement allowlist / `ALLOWED_AGENT_TOOLS`.

En CI (`pytest`), l’environnement inclut `python-dotenv` : le test d’intégration minimal de `test_agent_outbound_m2.py` ne doit pas être ignoré pour cette raison. Si vous lancez les tests dans un environnement minimal sans dépendances du `requirements.txt`, un skip peut s’appliquer (import `settings`).

## 8. Qualité continue

- Le workflow GitHub **Tests and Validation** exécute notamment **pytest** sur `backend/tests/` après installation de `requirements.txt` (voir `.github/workflows/test.yml`).
- La cible locale `make check` / `npm run ci:check` reproduit les mêmes étapes via `scripts/ci-check.mjs`.
