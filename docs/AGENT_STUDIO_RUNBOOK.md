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

### 2.1 Récap « IA clients » (mode Agent sur une conversation)

1. **Quand** : la conversation est en **mode agent** (réponses alignées sur la fiche **Agent Studio** du compte, agent **par défaut**, déploiement **`active` ou `canary`**). Ce n’est **pas** le playbook classique `bot_profiles` (mode bot « playbook »).
2. **Chaîne** : webhook WhatsApp → `message_service` → `generate_agent_studio_inbox_reply_with_confidence` (`bot_service.py`).
3. **Contexte modèle** : un **playbook texte** est construit par `_format_agent_studio_inbox_playbook` (objectif, public, intents, politiques, outils éventuels) + **indication de route** pour le message courant : `simulate_agent_route` dans `agent_studio_service.py` (même logique **heuristique** que l’onglet Tests : mots du **key** ou mots > 3 lettres de la **description** dans le texte client).
4. **Skill natif transfert** : le serveur injecte **toujours** le bloc `AGENT_STUDIO_NATIVE_HANDOFF_SKILL_PLAYBOOK` (fin de playbook) pour que le modèle sache qu’il n’y a **pas d’outil** « bouton transfert » : l’escalade est **côté serveur après envoi** du message au client.
5. **Génération** : appel Gemini avec l’historique de conversation (texte seul par défaut ; boucle **M2/M3** si `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` et outils noyau autorisés sur la fiche).
6. **Confiance** : score interne ; si trop bas → message fallback générique + escalade (comportement existant).
7. **Escalade humaine après envoi réussi** (`message_service`, mode agent) si **au moins une** condition :
   - **Route heuristique** : `agent_route_hint_triggers_human_handoff` — intent reconnue **autre que** `fallback` avec `handler: human` (le fallback `human` seul ne déclenche **pas** une escalade sur chaque message sans intent, pour éviter le bruit).
   - **Texte de la réponse** : `agent_reply_suggests_human_handoff` — formulations **explicites** de transfert vers un humain dans le message **effectivement envoyé** au client (ex. « Je vous transfère… », « un collègue prendra le relais… »), avec filtres sur les négations.
8. **Effet de l’escalade** : `set_conversation_bot_mode(False)` et notification optionnelle vers `HUMAN_BACKUP_NUMBER` (WhatsApp) si la variable d’environnement est définie.
9. **Aperçu graphe** (`map_config_to_runtime_graph`) : visualisation **simplifiée** (nœud Gemini + handoff + arêtes `fallback` et par intent `human`) ; le moteur WhatsApp ne « joue » pas ce graphe nœud par nœud comme un flow Playground.

## 3. Deux modes de génération

### 3.1 Mode texte seul (défaut)

Si `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` est **faux** (défaut), le playbook Agent Studio est injecté en **référence métier** : le modèle ne doit pas invoquer d’outils depuis le prompt classique ; génération directe type chat.

### 3.2 Mode boucle Gemini + outils (M2 / M3)

Si `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` est **vrai** et que la politique d’outils permet au moins un outil **du noyau lecture seule v1**, le backend utilise `run_agent_outbound_inbox_gemini_with_tools` (`backend/app/services/agent_outbound/loop.py`) :

- **M2** : premier passage modèle avec schéma `reply` + `tool_calls` ; exécution des appels via le noyau ; second passage pour la réponse client.
- **M3** (optionnel) : si `AGENT_OUTBOUND_REFLECTION_ENABLED` est **vrai**, un court passage « réflexion » qualité après les résultats d’outils, avant la synthèse finale.

Timeouts configurables : `AGENT_OUTBOUND_GEMINI_READ_TIMEOUT_S`, `AGENT_OUTBOUND_REFLECTION_READ_TIMEOUT_S`.

## 4. Politique d’outils (M0 / M4) et anti-fuite

- **`ALLOWED_AGENT_TOOLS`** (`agent_studio_service.py`) : catalogue produit des slugs autorisés sur la fiche. **`AGENT_STUDIO_ALLOWLIST_SLUGS`** et **`AGENT_KERNEL_V1_READ_TOOLS`** dans `registry.py` restent alignés ; seul le **sous-ensemble lecture seule** (`AGENT_KERNEL_V1_READ_TOOLS`) est exécutable dans la boucle outbound WhatsApp (pas `create_template`, `prepare_template_image_header`, `meta_block_contact`).
- **`normalize_agent_config`** retire tout slug inconnu ; **`validate_agent_config`** contrôle aussi les listes **brutes** avant normalisation pour rejeter les typos / slugs obsolètes.
- **Anti-fuite** : après exécution des outils, `sanitize_kernel_tool_results_for_model` (`agent_outbound/sanitize.py`) masque clés sensibles (`*token*`, `password`, `api_key`, etc.), e-mails et chaînes type JWT dans le JSON injecté au **second** passage Gemini ; le prompt de synthèse rappelle de ne pas divulguer d’autres clients ni d’identifiants internes. Cela **complète** le cloisonnement par `account_id` côté services, mais ne remplace pas une politique métier stricte sur la fiche agent.

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
| `backend/app/services/agent_outbound/` | Catalogue, parsing JSON, noyau d’exécution, boucle Gemini, **sanitation** des résultats. |
| `backend/app/services/bot_service.py` | `generate_agent_studio_inbox_reply_with_confidence`, formatage playbook. |
| `backend/app/api/routes_agent_studio.py` | API REST Agent Studio. |
| `backend/app/services/message_service.py` | Envoi bot, seuil de confiance, escalades (dont post-envoi Agent Studio). |

## 7. Tests

- `backend/tests/test_agent_outbound_m0.py` … `m4.py` : jalons noyau, parsing, boucle mockée, sécurité args.
- `backend/tests/test_agent_outbound_sanitize.py` : masquage des champs sensibles avant prompt synthèse.
- `backend/tests/test_agent_studio_service.py` : alignement allowlist / `ALLOWED_AGENT_TOOLS`.

En CI (`pytest`), l’environnement inclut `python-dotenv` : le test d’intégration minimal de `test_agent_outbound_m2.py` ne doit pas être ignoré pour cette raison. Si vous lancez les tests dans un environnement minimal sans dépendances du `requirements.txt`, un skip peut s’appliquer (import `settings`).

## 8. Qualité continue

- Le workflow GitHub **Tests and Validation** exécute notamment **pytest** sur `backend/tests/` après installation de `requirements.txt` (voir `.github/workflows/test.yml`).
- La cible locale `make check` / `npm run ci:check` reproduit les mêmes étapes via `scripts/ci-check.mjs`.
