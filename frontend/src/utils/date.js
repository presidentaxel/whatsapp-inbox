export function formatRelativeDate(value) {
  if (!value) return "";
  const d = typeof value === "string" ? new Date(value) : value;
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
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (isYesterday) {
    return "Hier";
  }

  // Dans la semaine
  const diffDays = Math.floor((now - d) / oneDay);
  if (diffDays < 7) {
    return d.toLocaleDateString([], { weekday: "short" });
  }

  // Sinon date courte
  return d.toLocaleDateString([], { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function formatRelativeDateTime(value) {
  if (!value) return "";
  const d = typeof value === "string" ? new Date(value) : value;
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
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (isYesterday) {
    return "Hier " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  const diffDays = Math.floor((now - d) / oneDay);
  if (diffDays < 7) {
    return `${d.toLocaleDateString([], { weekday: "short" })} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  }

  return d.toLocaleDateString([], { day: "2-digit", month: "2-digit", year: "numeric" }) + " " +
    d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

