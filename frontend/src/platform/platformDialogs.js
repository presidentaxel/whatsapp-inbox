/** @type {null | ((spec: Record<string, unknown>) => Promise<unknown>)} */
let openDialogImpl = null;

/** Enregistré par PlatformDialogProvider au montage. */
export function setPlatformDialogOpener(fn) {
  openDialogImpl = fn;
}

/**
 * @param {string} message
 * @param {{ title?: string, variant?: 'default' | 'danger' }} [options]
 * @returns {Promise<void>}
 */
export function platformAlert(message, options = {}) {
  if (!openDialogImpl) {
    if (typeof window !== "undefined" && window.alert) window.alert(message);
    return Promise.resolve();
  }
  return /** @type {Promise<void>} */ (
    openDialogImpl({
      kind: "alert",
      message,
      title: options.title,
      variant: options.variant ?? "default",
    })
  );
}

/**
 * @param {string} message
 * @param {{ title?: string, variant?: 'default' | 'danger', confirmLabel?: string, cancelLabel?: string }} [options]
 * @returns {Promise<boolean>}
 */
export function platformConfirm(message, options = {}) {
  if (!openDialogImpl) {
    return Promise.resolve(
      Boolean(
        typeof window !== "undefined" &&
          window.confirm &&
          window.confirm(message)
      )
    );
  }
  return /** @type {Promise<boolean>} */ (
    openDialogImpl({
      kind: "confirm",
      message,
      title: options.title,
      variant: options.variant ?? "default",
      confirmLabel: options.confirmLabel,
      cancelLabel: options.cancelLabel,
    })
  );
}

/**
 * @param {string} message
 * @param {string} [defaultValue]
 * @param {{ title?: string, variant?: 'default' | 'danger', confirmLabel?: string, cancelLabel?: string }} [options]
 * @returns {Promise<string | null>}
 */
export function platformPrompt(message, defaultValue = "", options = {}) {
  if (!openDialogImpl) {
    if (typeof window !== "undefined" && window.prompt) {
      return Promise.resolve(window.prompt(message, defaultValue));
    }
    return Promise.resolve(null);
  }
  return /** @type {Promise<string | null>} */ (
    openDialogImpl({
      kind: "prompt",
      message,
      defaultValue,
      title: options.title,
      variant: options.variant ?? "default",
      confirmLabel: options.confirmLabel,
      cancelLabel: options.cancelLabel,
    })
  );
}
