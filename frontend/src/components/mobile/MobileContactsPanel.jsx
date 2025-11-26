import { useState } from "react";
import { FiSearch, FiUserPlus } from "react-icons/fi";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function MobileContactsPanel({ contacts, onRefresh }) {
  const [searchTerm, setSearchTerm] = useState("");

  const filteredContacts = contacts.filter(contact => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (contact.display_name || "").toLowerCase();
    const phone = (contact.whatsapp_number || "").toLowerCase();
    return name.includes(term) || phone.includes(term);
  });

  return (
    <div className="mobile-contacts">
      <header className="mobile-panel-header">
        <h1>Contacts</h1>
        <button className="icon-btn" title="Nouveau contact">
          <FiUserPlus />
        </button>
      </header>

      <div className="mobile-panel-search">
        <div className="search-box">
          <FiSearch />
          <input
            type="text"
            placeholder="Rechercher un contact..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="mobile-contacts__list">
        {filteredContacts.length === 0 ? (
          <div className="mobile-panel-empty">
            <p>Aucun contact</p>
          </div>
        ) : (
          filteredContacts.map((contact) => (
            <div key={contact.id} className="mobile-contact-item">
              <div className="mobile-contact-item__avatar">
                {(contact.display_name || "?").charAt(0).toUpperCase()}
              </div>
              <div className="mobile-contact-item__info">
                <span className="mobile-contact-item__name">
                  {contact.display_name || "Sans nom"}
                </span>
                <span className="mobile-contact-item__phone">
                  {formatPhoneNumber(contact.whatsapp_number)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

