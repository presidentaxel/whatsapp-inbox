import { formatPhoneNumber } from "../../utils/formatPhone";

export default function ContactsPanel({
  contacts = [],
  selected,
  onSelect,
  selectedContacts = new Set(),
  onToggleSelect,
  multiSelect = false,
}) {
  if (!contacts.length) {
    return (
      <div className="contacts-panel empty">
        <p>Aucun contact pour le moment.</p>
      </div>
    );
  }

  const handleContactClick = (contact, e) => {
    if (multiSelect && e.target.type !== 'checkbox') {
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
          
          return (
            <div
              key={c.id}
              className={`contact-item ${isSelected ? "active" : ""} ${isMultiSelected ? "multi-selected" : ""}`}
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
                <small>{formatPhoneNumber(c.whatsapp_number)}</small>
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
                : formatPhoneNumber(selected.whatsapp_number)
              }
            </h3>
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
                      // Interpréter comme UTC si pas de timezone explicite
                      const dateStr = typeof timestamp === 'string' && !timestamp.match(/[Z+-]\d{2}:\d{2}$/) 
                        ? timestamp + 'Z' 
                        : timestamp;
                      return new Date(dateStr).toLocaleString("fr-FR", {
                        timeZone: "Europe/Paris",
                        year: "numeric",
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit"
                      });
                    })()
                  : "—"}
              </strong>
            </div>
          </>
        ) : (
          <p>Sélectionne un contact pour afficher les détails.</p>
        )}
      </div>
    </div>
  );
}

