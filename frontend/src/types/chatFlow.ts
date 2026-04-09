/**
 * Contrat métier aligné backend (JSON `conversations.bot_flow_state`) et playground.
 * Les clés sont en camelCase dans la base pour rester cohérents avec Meta / le front.
 */

export type StatutVTC = "Independant" | "Societe" | "Rattache" | null;
export type BesoinVTC = "Vehicule" | "Revenus" | "Admin" | "Multiple" | null;

export interface ChatSessionVariables {
  firstName?: string;
  statut?: StatutVTC;
  besoin?: BesoinVTC;
  interetCoop?: boolean;
  /** Réponses des nœuds (ex. clés `réponse_entrée`, `réponse_…`) */
  [key: string]: unknown;
}

/** Session persistée (Supabase `conversations.bot_flow_state`) */
export interface ChatSession {
  phoneNumber: string;
  /** Nœud où l’utilisateur est en attente (ex. interactif) - null si on enchaîne via `continueFromNodeId` */
  currentNodeId: string | null;
  lastInteractionAt: string | null;
  wabaOptIn: boolean;
  variables: ChatSessionVariables;
  /** Reprise du graphe quand aucun interactif n’est en attente */
  continueFromNodeId?: string | null;
  /** Cible après réponse à l’interactif courant (souvent un routeur) */
  afterInteractiveTarget?: string | null;
}

export interface BaseNode {
  id: string;
  type: "TEMPLATE" | "INTERACTIVE" | "ROUTER" | "GEMINI" | "DELAY" | "HANDOFF";
  name: string;
}

export interface TemplateNode extends BaseNode {
  type: "TEMPLATE";
  templateName: string;
  language: string;
  components: Array<{
    type: "body" | "header";
    parameters: Array<{ type: "text"; text: string }>;
  }>;
  nextNodeId: string;
}

export interface InteractiveNode extends BaseNode {
  type: "INTERACTIVE";
  bodyText: string;
  interactiveType: "button" | "list";
  options: Array<{
    id: string;
    title: string;
    targetNodeId: string;
    saveToVariable?: string;
  }>;
  fallbackNodeId: string;
}

export interface RouterNode extends BaseNode {
  type: "ROUTER";
  conditions: Array<{
    variable: string;
    operator: "equals" | "contains" | "exists";
    value: unknown;
    targetNodeId: string;
  }>;
  defaultTargetNodeId: string;
}

export interface GeminiNode extends BaseNode {
  type: "GEMINI";
  systemPrompt: string;
  expectedOutputs: Array<{
    keyword: string;
    targetNodeId: string;
  }>;
  unrecognizedTargetNodeId: string;
}

/** Exemple payload Meta - boutons (documenté pour l’équipe / tests) */
export const META_INTERACTIVE_BUTTONS_EXAMPLE = {
  messaging_product: "whatsapp",
  recipient_type: "individual",
  to: "{{PHONE_NUMBER}}",
  type: "interactive",
  interactive: {
    type: "button",
    body: {
      text:
        "Vous êtes plutôt :\n1️⃣ Indépendant\n2️⃣ En société\n3️⃣ Rattaché à une société",
    },
    action: {
      buttons: [
        { type: "reply", reply: { id: "btn_indep", title: "Indépendant" } },
        { type: "reply", reply: { id: "btn_societe", title: "En société" } },
        { type: "reply", reply: { id: "btn_rattache", title: "Rattaché" } },
      ],
    },
  },
} as const;
