/**
 * Estimation de durée pour la barre de progression de l’assistant Playground.
 *
 * Historique des durées :
 * - Ce n’est pas une moyenne arithmétique simple : on utilise une **EMA** (moyenne mobile
 *   exponentielle, coefficient EMA_ALPHA) : chaque nouvelle mesure tire l’estimation vers
 *   la durée observée, en donnant plus de poids aux tours récents qu’aux anciens.
 * - Persisté dans localStorage (clé STORAGE_KEY).
 *
 * Ajustement contextuel : texte utilisateur + taille du graphe (boosts modérés).
 */

const STORAGE_KEY = "whatsapp-inbox.playground-assist-timing-v1";
/** Poids des nouvelles mesures dans l’EMA (0–1). Plus bas = lissage plus fort sur l’historique. */
const EMA_ALPHA = 0.28;
const MAX_SAMPLES = 14;

/** @typedef {{ askMs: number, agentMs: number, askN: number, agentN: number }} TimingState */

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const j = JSON.parse(raw);
    if (typeof j?.askMs !== "number" || typeof j?.agentMs !== "number") return null;
    return {
      askMs: Math.max(3500, Math.min(180000, j.askMs)),
      agentMs: Math.max(6000, Math.min(240000, j.agentMs)),
      askN: typeof j.askN === "number" ? j.askN : 0,
      agentN: typeof j.agentN === "number" ? j.agentN : 0,
    };
  } catch {
    return null;
  }
}

function saveState(/** @type {TimingState} */ s) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* private mode */
  }
}

function defaultState() {
  /* Valeurs initiales conservatrices : la barre avance lentement jusqu’à ce que l’EMA apprenne. */
  return { askMs: 9000, agentMs: 22000, askN: 0, agentN: 0 };
}

/**
 * Met à jour l’EMA avec une nouvelle durée observée (ms).
 * @param {'ask'|'agent'} mode
 * @param {number} durationMs
 */
export function recordAssistDuration(mode, durationMs) {
  if (!Number.isFinite(durationMs) || durationMs < 200) return;
  const d = Math.min(300000, durationMs);
  const prev = loadState() || defaultState();
  if (mode === "ask") {
    const nextN = Math.min(MAX_SAMPLES, prev.askN + 1);
    const nextMs =
      prev.askN === 0 ? d : prev.askMs * (1 - EMA_ALPHA) + d * EMA_ALPHA;
    saveState({ ...prev, askMs: nextMs, askN: nextN });
  } else {
    const nextN = Math.min(MAX_SAMPLES, prev.agentN + 1);
    const nextMs =
      prev.agentN === 0 ? d : prev.agentMs * (1 - EMA_ALPHA) + d * EMA_ALPHA;
    saveState({ ...prev, agentMs: nextMs, agentN: nextN });
  }
}

/**
 * Durée attendue (ms) pour l’animation de progression.
 * @param {'ask'|'agent'} mode
 * @param {{ userTextLength?: number, graphJsonBytes?: number, nodeCount?: number }} factors
 */
export function getExpectedAssistDurationMs(mode, factors = {}) {
  const s = loadState() || defaultState();
  const base = mode === "ask" ? s.askMs : s.agentMs;
  const textLen = Math.max(0, Number(factors.userTextLength) || 0);
  const graphBytes = Math.max(0, Number(factors.graphJsonBytes) || 0);
  const nodes = Math.max(0, Number(factors.nodeCount) || 0);

  // Charge « contenu » : texte + graphe (log pour éviter d’exploser)
  const textBoost = 1 + Math.min(0.85, Math.log1p(textLen) / 12);
  const graphBoost = 1 + Math.min(0.95, graphBytes / (48 * 1024) + nodes / 55);

  const raw = base * textBoost * graphBoost;
  /* Plancher élevé : évite que la barre remonte trop vite quand l’EMA est encore courte. */
  return Math.max(7500, Math.min(150000, Math.round(raw)));
}

/**
 * Courbe d’affichage du pourcentage : exposant > 1 = montée lente au début,
 * pour ne pas donner l’impression que la réponse est presque prête tout de suite.
 */
export const ASSIST_PROGRESS_SHAPE_EXP = 1.55;
