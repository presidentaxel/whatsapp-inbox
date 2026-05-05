/** Logs de debug : actifs uniquement en dev (pas dans le bundle prod bruyant). */
export function devLog(...args) {
  if (import.meta.env.DEV) {
    console.log(...args);
  }
}
