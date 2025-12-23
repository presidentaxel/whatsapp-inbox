/**
 * Parse une date en s'assurant qu'elle est interprétée comme UTC
 * Les dates stockées dans Supabase sont en UTC
 * 
 * Si une date n'a pas de timezone explicite, on l'interprète comme UTC
 */
export function parseDateAsUTC(value) {
  if (!value) return null;
  
  let d;
  
  if (typeof value === "string") {
    // Si la string se termine par 'Z' ou contient un timezone explicite (+XX:XX ou -XX:XX)
    if (value.endsWith('Z') || value.match(/[+-]\d{2}:\d{2}$/)) {
      // C'est une date avec timezone explicite, la parser correctement
      d = new Date(value);
    } else if (value.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)) {
      // Format ISO sans timezone : on l'interprète comme UTC
      // On ajoute 'Z' pour forcer l'interprétation UTC
      d = new Date(value + 'Z');
    } else {
      // Parser comme date locale (fallback)
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

/**
 * Parse une date en s'assurant qu'elle est interprétée comme UTC
 * Les dates stockées dans Supabase sont en UTC
 * 
 * Si une date n'a pas de timezone explicite, on l'interprète comme UTC
 */
function parseDate(value) {
  return parseDateAsUTC(value);
}

/**
 * Formate l'heure d'une date en heure française (Europe/Paris)
 * La date est en UTC, on la convertit vers l'heure française pour l'affichage
 */
function formatTime(date, options = {}) {
  if (!date) return "";
  
  // Convertir UTC vers Europe/Paris pour l'affichage
  return date.toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
    ...options
  });
}

/**
 * Formate la date en heure française (Europe/Paris)
 * La date est en UTC, on la convertit vers l'heure française pour l'affichage
 */
function formatDateOnly(date, options = {}) {
  if (!date) return "";
  
  // Convertir UTC vers Europe/Paris pour l'affichage
  return date.toLocaleDateString("fr-FR", {
    timeZone: "Europe/Paris",
    ...options
  });
}

export function formatRelativeDate(value) {
  const d = parseDate(value);
  if (!d) return "";
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  // Convertir les dates en heure locale (Europe/Paris) pour les comparaisons
  // Utiliser toLocaleString pour obtenir les composants de date en heure locale
  const dLocalStr = formatDateOnly(d, { year: "numeric", month: "2-digit", day: "2-digit" });
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
    return formatTime(d);
  }
  if (isYesterday) {
    return "Hier";
  }

  // Dans la semaine
  const diffDays = Math.floor((nowLocal.getTime() - dLocal.getTime()) / oneDay);
  if (diffDays < 7) {
    return formatDateOnly(d, { weekday: "short" });
  }

  // Sinon date courte
  return formatDateOnly(d, { 
    day: "2-digit", 
    month: "2-digit", 
    year: "numeric"
  });
}

export function formatRelativeDateTime(value) {
  const d = parseDate(value);
  if (!d) return "";
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  // Convertir les dates en heure locale (Europe/Paris) pour les comparaisons
  // Utiliser toLocaleString pour obtenir les composants de date en heure locale
  const dLocalStr = formatDateOnly(d, { year: "numeric", month: "2-digit", day: "2-digit" });
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
    return formatTime(d);
  }
  if (isYesterday) {
    return "Hier " + formatTime(d);
  }

  const diffDays = Math.floor((nowLocal.getTime() - dLocal.getTime()) / oneDay);
  if (diffDays < 7) {
    return `${formatDateOnly(d, { weekday: "short" })} ${formatTime(d)}`;
  }

  return formatDateOnly(d, { 
    day: "2-digit", 
    month: "2-digit", 
    year: "numeric"
  }) + " " + formatTime(d);
}

