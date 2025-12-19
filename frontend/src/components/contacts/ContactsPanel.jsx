import { formatPhoneNumber } from "../../utils/formatPhone";

export default function ContactsPanel({
  contacts = [],
  selected,
  onSelect,
}) {
  if (!contacts.length) {
    return (
      <div className="contacts-panel empty">
        <p>Aucun contact pour le moment.</p>
      </div>
    );
  }

  return (
    <div className="contacts-panel">
      <div className="contacts-list">
        {contacts.map((c) => (
          <div
            key={c.id}
            className={`contact-item ${selected?.id === c.id ? "active" : ""}`}
            onClick={() => onSelect?.(c)}
          >
            <div className="avatar">{(c.display_name || c.whatsapp_number || "?")[0]}</div>
            <div className="contact-info">
              <strong>{c.display_name || formatPhoneNumber(c.whatsapp_number)}</strong>
              <small>{formatPhoneNumber(c.whatsapp_number)}</small>
            </div>
          </div>
        ))}
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
                  ? new Date(selected.created_at).toLocaleString("fr-FR", {
                      timeZone: "Europe/Paris",
                      year: "numeric",
                      month: "2-digit",
                      day: "2-digit",
                      hour: "2-digit",
                      minute: "2-digit"
                    })
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

