import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { setPlatformDialogOpener } from "./platformDialogs";

/**
 * @param {{
 *   kind: 'alert' | 'confirm' | 'prompt',
 *   message: string,
 *   title?: string,
 *   defaultValue?: string,
 *   variant?: 'default' | 'danger',
 *   confirmLabel?: string,
 *   cancelLabel?: string,
 *   resolve: (value: unknown) => void,
 * }} spec
 */
function DialogSurface({ spec, onDismiss }) {
  const inputRef = useRef(null);
  const [promptValue, setPromptValue] = useState(spec.defaultValue ?? "");

  useLayoutEffect(() => {
    setPromptValue(spec.defaultValue ?? "");
  }, [spec.kind, spec.defaultValue]);

  useEffect(() => {
    if (spec.kind !== "prompt") return;
    const id = window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.select?.();
    });
    return () => window.cancelAnimationFrame(id);
  }, [spec.kind]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        if (spec.kind === "alert") onDismiss(undefined);
        else if (spec.kind === "confirm") onDismiss(false);
        else onDismiss(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [spec.kind, onDismiss]);

  const title =
    spec.title ||
    (spec.kind === "alert"
      ? "Information"
      : spec.kind === "prompt"
        ? "Saisie"
        : "Confirmation");

  const cancelLabel = spec.cancelLabel ?? "Annuler";
  const confirmLabel =
    spec.confirmLabel ?? (spec.kind === "prompt" ? "OK" : "Confirmer");

  const primaryIsDanger = spec.variant === "danger";

  return (
    <div
      className="platform-dialog-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) e.preventDefault();
      }}
    >
      <div
        className="platform-dialog-panel"
        role={
          spec.kind === "alert"
            ? "alertdialog"
            : spec.kind === "confirm"
              ? "alertdialog"
              : "dialog"
        }
        aria-modal="true"
        aria-labelledby="platform-dialog-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="platform-dialog-title" className="platform-dialog-title">
          {title}
        </h2>
        <p className="platform-dialog-message">{spec.message}</p>
        {spec.kind === "prompt" ? (
          <input
            ref={inputRef}
            type="text"
            className="platform-dialog-input"
            value={promptValue}
            onChange={(e) => setPromptValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                onDismiss(promptValue);
              }
            }}
          />
        ) : null}
        <div className="platform-dialog-actions">
          {spec.kind === "alert" ? (
            <button
              type="button"
              className="platform-dialog-btn platform-dialog-btn--primary"
              onClick={() => onDismiss(undefined)}
            >
              OK
            </button>
          ) : (
            <>
              <button
                type="button"
                className="platform-dialog-btn platform-dialog-btn--ghost"
                onClick={() =>
                  onDismiss(spec.kind === "confirm" ? false : null)
                }
              >
                {cancelLabel}
              </button>
              <button
                type="button"
                className={
                  primaryIsDanger
                    ? "platform-dialog-btn platform-dialog-btn--danger"
                    : "platform-dialog-btn platform-dialog-btn--primary"
                }
                onClick={() =>
                  onDismiss(spec.kind === "confirm" ? true : promptValue)
                }
              >
                {confirmLabel}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function PlatformDialogProvider({ children }) {
  const [active, setActive] = useState(null);

  const open = useCallback((spec) => {
    return new Promise((resolve) => {
      setActive({
        ...spec,
        resolve,
      });
    });
  }, []);

  useEffect(() => {
    setPlatformDialogOpener(open);
    return () => setPlatformDialogOpener(null);
  }, [open]);

  const finish = useCallback((value) => {
    setActive((cur) => {
      if (cur?.resolve) cur.resolve(value);
      return null;
    });
  }, []);

  const portal =
    active &&
    createPortal(
      <DialogSurface spec={active} onDismiss={(value) => finish(value)} />,
      document.body
    );

  return (
    <>
      {children}
      {portal}
    </>
  );
}
