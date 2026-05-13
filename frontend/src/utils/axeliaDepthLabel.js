const DEPTH_LABELS = {
  brief: "Mode Bref",
  standard: "Mode Standard",
  expert: "Mode Expert",
};

export function toAxeliaDepthLabel(depth) {
  return DEPTH_LABELS[depth] || "Mode Standard";
}

