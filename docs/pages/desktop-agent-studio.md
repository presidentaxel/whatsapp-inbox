# Page Desktop Agent Studio

- Route: `/agent-studio`.
- Container: `InboxPage` (mode `agentStudio`).
- Permission: `agent_studio.access`.
- Composant: `AgentStudioPage`.
- References:
  - runbook dedie: `docs/AGENT_STUDIO_RUNBOOK.md`.
- Verification:
  - entree menu visible selon permission;
  - `accountId` actif bien transmis au composant.
