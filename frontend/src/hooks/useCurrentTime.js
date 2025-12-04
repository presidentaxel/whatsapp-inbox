import { useState, useEffect } from "react";

/**
 * Hook qui retourne l'heure actuelle et se met à jour périodiquement
 * @param {number} intervalMs - Intervalle de mise à jour en millisecondes (défaut: 60000 = 1 minute)
 * @returns {Date} - Date actuelle
 */
export function useCurrentTime(intervalMs = 60000) {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    // Mettre à jour immédiatement
    setCurrentTime(new Date());

    // Mettre à jour périodiquement
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, intervalMs);

    return () => clearInterval(interval);
  }, [intervalMs]);

  return currentTime;
}

