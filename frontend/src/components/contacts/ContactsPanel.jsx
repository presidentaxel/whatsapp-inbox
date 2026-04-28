import { formatPhoneNumber } from "../../utils/formatPhone";

function normalizeWaDigits(phone) {
  return String(phone || "").replace(/\D/g, "");
}

export default function ContactsPanel({
  contacts = [],
  selected,
  onSelect,
  selectedContacts = new Set(),
  onToggleSelect,
  multiSelect = false,
  metaBlockedNormalizedIds = [],
  canModerateWaAny = false,
  metaBlockBusyId = null,
  onMetaBlockOpen,
}) {
  const blockedSet =
    metaBlockedNormalizedIds instanceof Set
      ? metaBlockedNormalizedIds
      : new Set(metaBlockedNormalizedIds || []);

  const isMetaBlocked = (contact) =>
    blockedSet.has(normalizeWaDigits(contact?.whatsapp_number));

  if (!contacts.length) {
    return (
      <div className="contacts-panel empty">
        <p>Aucun contact pour le moment.</p>
      </div>
    );
  }

  const handleContactClick = (contact, e) => {
    if (multiSelect && e.target.type !== "checkbox") {
      onToggleSelect?.(contact.id);
    } else if (!multiSelect) {
      onSelect?.(contact);
    }
  };

  const handleCheckboxChange = (contactId, e) => {
    e.stopPropagation();
    onToggleSelect?.(contactId);
  };

  return (
    <div className="contacts-panel">
      <div className="contacts-list">
        {contacts.map((c) => {
          const isSelected = multiSelect
            ? selectedContacts.has(c.id)
            : selected?.id === c.id;
          const isMultiSelected = multiSelect && selectedContacts.has(c.id);
          const blocked = isMetaBlocked(c);

          return (
            <div
              key={c.id}
              className={`contact-item ${isSelected ? "active" : ""} ${isMultiSelected ? "multi-selected" : ""} ${blocked ? "contact-item--meta-blocked" : ""}`}
              onClick={(e) => handleContactClick(c, e)}
            >
              {multiSelect && (
                <input
                  type="checkbox"
                  checked={isMultiSelected}
                  onChange={(e) => handleCheckboxChange(c.id, e)}
                  onClick={(e) => e.stopPropagation()}
                  className="contact-checkbox"
                />
              )}
              <div className="avatar">{(c.display_name || c.whatsapp_number || "?")[0]}</div>
              <div className="contact-info">
                <strong>{c.display_name || formatPhoneNumber(c.whatsapp_number)}</strong>
                <small>
                  {formatPhoneNumber(c.whatsapp_number)}
                  {blocked ? " · Bloqué (app)" : ""}
                </small>
              </div>
            </div>
          );
        })}
      </div>
      <div className="contacts-details">
        {selected ? (
          <>
            <h3>
              {selected.display_name
                ? `${selected.display_name} - ${formatPhoneNumber(selected.whatsapp_number)}`
                : formatPhoneNumber(selected.whatsapp_number)}
            </h3>
            {isMetaBlocked(selected) && (
              <p className="contacts-details__blocked-note">
                Ce numéro est bloqué sur au moins une ligne dans l’application (envoi désactivé pour les
                opérateurs ; les messages entrants restent enregistrés).
              </p>
            )}
            <div className="info-row">
              <span>Numéro</span>
              <strong>{formatPhoneNumber(selected.whatsapp_number)}</strong>
            </div>
            <div className="info-row">
              <span>Créé le</span>
              <strong>
                {selected.created_at
                  ? (() => {
                      const timestamp = selected.created_at;
                      const dateStr =
                        typeof timestamp === "string" && !timestamp.match(/[Z+-]\d{2}:\d{2}$/)
                          ? timestamp + "Z"
                          : timestamp;
                      return new Date(dateStr).toLocaleString("fr-FR", {
                        timeZone: "Europe/Paris",
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      });
                    })()
                  : "-"}
              </strong>
            </div>
            {canModerateWaAny && !multiSelect && (
              <div className="contacts-details__meta-actions">
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={metaBlockBusyId === selected.id}
                  onClick={() => onMetaBlockOpen?.(selected, "block")}
                >
                  Bloquer sur cette ligne
                </button>
                {isMetaBlocked(selected) && (
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    disabled={metaBlockBusyId === selected.id}
                    onClick={() => onMetaBlockOpen?.(selected, "unblock")}
                  >
                    Débloquer sur cette ligne
                  </button>
                )}
              </div>
            )}
          </>
        ) : (
          <p>Sélectionne un contact pour afficher les détails.</p>
        )}
      </div>
    </div>
  );
}
