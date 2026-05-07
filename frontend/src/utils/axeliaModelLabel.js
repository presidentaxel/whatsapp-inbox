export function toAxeliaModelLabel(modelId) {
  const raw = String(modelId || "").trim();
  if (!raw) return "";
  const low = raw.toLowerCase();
  if (low.includes("2.5-pro")) return "Axelia Pro";
  if (low.includes("2.5-flash")) return "Axelia Fast";
  if (low.includes("flash")) return "Axelia Fast";
  if (low.includes("pro")) return "Axelia Pro";
  return "Axelia";
}

