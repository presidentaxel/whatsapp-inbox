# Page Desktop Agent Studio

- Route : `/agent-studio`.
- Conteneur : `InboxPage` (mode `agentStudio`).
- Permission : `agent_studio.access`.
- Composant : `AgentStudioPage`.
- Références :
  - Runbook produit + inbox / mode Agent (flags, noyau outbound, tests) : [`docs/AGENT_STUDIO_RUNBOOK.md`](../AGENT_STUDIO_RUNBOOK.md).
- Vérification :
  - entrée menu visible selon la permission ;
  - `accountId` actif bien transmis au composant.

## Inbox (réponses auto)

Les réponses WhatsApp pilotées par la fiche par défaut passent par le backend (`generate_agent_studio_inbox_reply_with_confidence`). La boucle **Gemini + outils** est **désactivée par défaut** ; elle dépend de `AGENT_OUTBOUND_GEMINI_TOOLS_ENABLED` et de la liste d’outils autorisés sur la fiche (voir le runbook).
