/**
 * Périmètre « tous les comptes » côté Axelia — doit rester identique à
 * `AXELIA_CONTEXT_ALL` dans `AxeliaChat.jsx`.
 */
export const AXELIA_ACCOUNT_SCOPE_ALL = "__all__";

/**
 * Choisit une ligne de discussion dont `account_context` correspond au périmètre voulu.
 * Ne retourne pas `rows[0]` si le contexte ne correspond pas (évite fil coop affiché + API en mode multi-compte).
 */
export function pickConversationRowForAccountContext(rows, resolvedContext) {
  const want = String(resolvedContext ?? AXELIA_ACCOUNT_SCOPE_ALL);
  const row = (rows || []).find(
    (r) =>
      String(r.account_context ?? AXELIA_ACCOUNT_SCOPE_ALL) === want,
  );
  return row ?? null;
}

export function resolveInitialAxeliaAccountContext(initialAccountId, accessibleAccounts) {
  if (!accessibleAccounts?.length) return AXELIA_ACCOUNT_SCOPE_ALL;
  if (
    initialAccountId &&
    accessibleAccounts.some((a) => a?.id === initialAccountId)
  ) {
    return initialAccountId;
  }
  /* Une seule ligne accessible : même périmètre qu’une coop sans ambiguïté « tous les comptes ». */
  if (accessibleAccounts.length === 1 && accessibleAccounts[0]?.id) {
    return accessibleAccounts[0].id;
  }
  return AXELIA_ACCOUNT_SCOPE_ALL;
}
