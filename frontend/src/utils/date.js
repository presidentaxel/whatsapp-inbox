export function formatRelativeDate(value) {
  if (!value) return "";
  let d;
  if (typeof value === "string") {
    d = new Date(value);
  } else if (typeof value === "number") {
    d = new Date(value);
  } else {
    d = value;
  }
  
  // Vérifier que la date est valide
  if (isNaN(d.getTime())) {
    return "";
  }
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();

  const yesterday = new Date(now.getTime() - oneDay);
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();

  if (isToday) {
    return d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
  }
  if (isYesterday) {
    return "Hier";
  }

  // Dans la semaine
  const diffDays = Math.floor((now - d) / oneDay);
  if (diffDays < 7) {
    return d.toLocaleDateString("fr-FR", { weekday: "short" });
  }

  // Sinon date courte
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function formatRelativeDateTime(value) {
  if (!value) return "";
  let d;
  if (typeof value === "string") {
    d = new Date(value);
  } else if (typeof value === "number") {
    d = new Date(value);
  } else {
    d = value;
  }
  
  // Vérifier que la date est valide
  if (isNaN(d.getTime())) {
    return "";
  }
  
  const now = new Date();
  const oneDay = 24 * 60 * 60 * 1000;

  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();

  const yesterday = new Date(now.getTime() - oneDay);
  const isYesterday =
    d.getFullYear() === yesterday.getFullYear() &&
    d.getMonth() === yesterday.getMonth() &&
    d.getDate() === yesterday.getDate();

  if (isToday) {
    return d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
  }
  if (isYesterday) {
    return "Hier " + d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
  }

  const diffDays = Math.floor((now - d) / oneDay);
  if (diffDays < 7) {
    return `${d.toLocaleDateString("fr-FR", { weekday: "short" })} ${d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    })}`;
  }

  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }) + " " +
    d.toLocaleTimeString("fr-FR", { 
      hour: "2-digit", 
      minute: "2-digit",
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
    });
}

