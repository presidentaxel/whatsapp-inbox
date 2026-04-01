const keyFor = (accountId) => `playground_flow_${accountId}`;

export function loadFlow(accountId) {
  if (!accountId) return null;
  try {
    const raw = localStorage.getItem(keyFor(accountId));
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function saveFlow(accountId, payload) {
  if (!accountId) return;
  try {
    localStorage.setItem(keyFor(accountId), JSON.stringify(payload));
  } catch {
    /* quota / private mode */
  }
}
