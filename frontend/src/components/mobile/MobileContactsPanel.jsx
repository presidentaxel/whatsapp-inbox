import { useState, useEffect } from "react";
import { FiSearch, FiUserPlus } from "react-icons/fi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import MobileContactForm from "./MobileContactForm";
import MobileContactDetail from "./MobileContactDetail";

export default function MobileContactsPanel({ contacts, activeAccount, onRefresh, initialContact }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [selectedContact, setSelectedContact] = useState(initialContact || null);

  const filteredContacts = contacts.filter(contact => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (contact.display_name || "").toLowerCase();
    const phone = (contact.whatsapp_number || "").toLowerCase();
    return name.includes(term) || phone.includes(term);
  });

  const handleContactCreated = () => {
    setShowForm(false);
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleContactUpdated = () => {
    setSelectedContact(null);
    if (onRefresh) {
      onRefresh();
    }
  };

  const handleContactDeleted = () => {
    setSelectedContact(null);
    if (onRefresh) {
      onRefresh();
    }
  };

  // Si un contact initial est fourni, l'afficher
  useEffect(() => {
    if (initialContact) {
      setSelectedContact(initialContact);
    }
  }, [initialContact]);

  // Si un contact initial est fourni, l'afficher
  useEffect(() => {
    if (initialContact) {
      setSelectedContact(initialContact);
    }
  }, [initialContact]);

  if (showForm) {
    return (
      <MobileContactForm
        onBack={() => setShowForm(false)}
        onCreated={handleContactCreated}
      />
    );
  }

  if (selectedContact) {
    return (
      <MobileContactDetail
        contact={selectedContact}
        activeAccount={activeAccount}
        onBack={() => setSelectedContact(null)}
        onUpdate={handleContactUpdated}
        onDelete={handleContactDeleted}
      />
    );
  }

  return (
    <div className="mobile-contacts">
      <header className="mobile-panel-header">
        <h1>Contacts</h1>
        <button 
          className="icon-btn" 
          title="Nouveau contact"
          onClick={() => setShowForm(true)}
        >
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
            <div 
              key={contact.id} 
              className="mobile-contact-item"
              onClick={() => setSelectedContact(contact)}
            >
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

