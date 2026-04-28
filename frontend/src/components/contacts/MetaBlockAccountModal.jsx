import { useEffect, useState } from "react";

export default function MetaBlockAccountModal({
  open,
  onClose,
  action,
  accounts = [],
  busy = false,
  onConfirm,
}) {
  const [pickedId, setPickedId] = useState(null);

  useEffect(() => {
    if (open) {
      setPickedId(accounts.length === 1 ? accounts[0].id : null);
    }
  }, [open, accounts]);

  if (!open) {
    return null;
  }

  const title =
    action === "block"
      ? "Bloquer sur quelle ligne ? (application)"
      : "Débloquer sur quelle ligne ? (application)";

  return (
    <div className="meta-block-modal-overlay" role="presentation" onClick={() => !busy && onClose?.()}>
      <div
        className="meta-block-modal"
        role="dialog"
        aria-labelledby="meta-block-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="meta-block-modal-title" className="meta-block-modal__title">
          {title}
        </h3>
        {accounts.length === 0 ? (
          <p className="meta-block-modal__empty">Aucun compte disponible pour cette action.</p>
        ) : (
          <ul className="meta-block-modal__list">
            {accounts.map((a) => (
              <li key={a.id}>
                <label className="meta-block-modal__option">
                  <input
                    type="radio"
                    name="meta-block-account"
                    checked={pickedId === a.id}
                    onChange={() => setPickedId(a.id)}
                    disabled={busy}
                  />
                  <span>
                    <strong>{a.name || "Compte"}</strong>
                    {a.phone_number ? <small>{a.phone_number}</small> : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="meta-block-modal__actions">
          <button type="button" className="btn-secondary btn-sm" disabled={busy} onClick={() => onClose?.()}>
            Annuler
          </button>
          <button
            type="button"
            className="btn-primary btn-sm"
            disabled={busy || !pickedId || accounts.length === 0}
            onClick={() => pickedId && onConfirm?.(pickedId)}
          >
            {busy ? "…" : action === "block" ? "Bloquer" : "Débloquer"}
          </button>
        </div>
      </div>
    </div>
  );
}
