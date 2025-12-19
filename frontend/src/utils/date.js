/**
 * Parse une date en s'assurant qu'elle est correctement interprétée comme UTC
 * puis convertie en heure locale pour les comparaisons
 */
function parseDate(value) {
  if (!value) return null;
  
  let d;
  if (typeof value === "string") {
    // Si la string se termine par 'Z' ou contient '+00:00', c'est UTC
    // Sinon, on assume que c'est UTC si c'est au format ISO
    if (value.endsWith('Z') || value.includes('+00:00') || value.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)) {
      // C'est une date UTC, la parser correctement
      d = new Date(value);
    } else {
      // Parser comme date locale
      d = new Date(value);
    }
  } else if (typeof value === "number") {
    d = new Date(value);
  } else {
    d = value;
  }
  
  // Vérifier que la date est valide
  if (isNaN(d.getTime())) {
    return null;
  }
  
  return d;
}

export function formatRelativeDate(value) {
  const d = parseDate(value);
  if (!d) return "";
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  // Convertir les dates en heure locale (Europe/Paris) pour les comparaisons
  // Utiliser toLocaleString pour obtenir les composants de date en heure locale
  const dLocalStr = d.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" });
  const nowLocalStr = now.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" });
  
  // Parser les dates locales pour comparaison
  const [dDay, dMonth, dYear] = dLocalStr.split('/').map(Number);
  const [nowDay, nowMonth, nowYear] = nowLocalStr.split('/').map(Number);
  
  const dLocal = new Date(dYear, dMonth - 1, dDay);
  const nowLocal = new Date(nowYear, nowMonth - 1, nowDay);
  const yesterdayLocal = new Date(nowLocal.getTime() - oneDay);

  const isToday = dLocal.getTime() === nowLocal.getTime();
  const isYesterday = dLocal.getTime() === yesterdayLocal.getTime();

  if (isToday) {
    // Afficher l'heure en heure locale (France)
    return d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: "Europe/Paris" // Fuseau horaire de la France avec changement d'heure automatique
    });
  }
  if (isYesterday) {
    return "Hier";
  }

  // Dans la semaine
  const diffDays = Math.floor((nowLocal.getTime() - dLocal.getTime()) / oneDay);
  if (diffDays < 7) {
    return d.toLocaleDateString("fr-FR", { 
      weekday: "short",
      timeZone: "Europe/Paris"
    });
  }

  // Sinon date courte
  return d.toLocaleDateString("fr-FR", { 
    day: "2-digit", 
    month: "2-digit", 
    year: "numeric",
    timeZone: "Europe/Paris"
  });
}

export function formatRelativeDateTime(value) {
  const d = parseDate(value);
  if (!d) return "";
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  // Convertir les dates en heure locale (Europe/Paris) pour les comparaisons
  // Utiliser toLocaleString pour obtenir les composants de date en heure locale
  const dLocalStr = d.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" });
  const nowLocalStr = now.toLocaleDateString("fr-FR", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" });
  
  // Parser les dates locales pour comparaison
  const [dDay, dMonth, dYear] = dLocalStr.split('/').map(Number);
  const [nowDay, nowMonth, nowYear] = nowLocalStr.split('/').map(Number);
  
  const dLocal = new Date(dYear, dMonth - 1, dDay);
  const nowLocal = new Date(nowYear, nowMonth - 1, nowDay);
  const yesterdayLocal = new Date(nowLocal.getTime() - oneDay);

  const isToday = dLocal.getTime() === nowLocal.getTime();
  const isYesterday = dLocal.getTime() === yesterdayLocal.getTime();

  // Options pour l'affichage en heure locale (France)
  const timeOptions = {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris" // Fuseau horaire de la France avec changement d'heure automatique
  };

  const dateOptions = {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "Europe/Paris"
  };

  if (isToday) {
    return d.toLocaleTimeString("fr-FR", timeOptions);
  }
  if (isYesterday) {
    return "Hier " + d.toLocaleTimeString("fr-FR", timeOptions);
  }

  const diffDays = Math.floor((nowLocal.getTime() - dLocal.getTime()) / oneDay);
  if (diffDays < 7) {
    return `${d.toLocaleDateString("fr-FR", { weekday: "short", timeZone: "Europe/Paris" })} ${d.toLocaleTimeString("fr-FR", timeOptions)}`;
  }

  return d.toLocaleDateString("fr-FR", dateOptions) + " " + d.toLocaleTimeString("fr-FR", timeOptions);
}

