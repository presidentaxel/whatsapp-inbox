import { useMemo, useState, useEffect } from "react";
import { FiSearch, FiUserPlus } from "react-icons/fi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { filterContactsBySearch } from "../../utils/contactSearch";
import MobileContactForm from "./MobileContactForm";
import MobileContactDetail from "./MobileContactDetail";

export default function MobileContactsPanel({
  contacts,
  activeAccount,
  onRefresh,
  initialContact,
  metaBlockedNormalizedIds = [],
  canModerateWaAny = false,
  metaBlockBusyId = null,
  onMetaBlockOpen,
  onContactsSearchQuery,
}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [selectedContact, setSelectedContact] = useState(initialContact || null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(searchTerm), 320);
    return () => window.clearTimeout(t);
  }, [searchTerm]);

  useEffect(() => {
    onContactsSearchQuery?.(debouncedSearch);
  }, [debouncedSearch, onContactsSearchQuery]);

  const blockedSet =
    metaBlockedNormalizedIds instanceof Set
      ? metaBlockedNormalizedIds
      : new Set(metaBlockedNormalizedIds || []);

  const normalizeWaDigits = (phone) => String(phone || "").replace(/\D/g, "");

  const isMetaBlocked = (contact) =>
    blockedSet.has(normalizeWaDigits(contact?.whatsapp_number));

  const filteredContacts = useMemo(
    () => filterContactsBySearch(contacts, searchTerm),
    [contacts, searchTerm]
  );

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
        metaBlocked={isMetaBlocked(selectedContact)}
        canModerateWaAny={canModerateWaAny}
        metaBlockBusy={metaBlockBusyId === selectedContact.id}
        onMetaBlockOpen={(action) => onMetaBlockOpen?.(selectedContact, action)}
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

      <div className="mobile-panel-search mobile-panel-search--contacts">
        <div className="search-box search-box--contacts">
          <FiSearch aria-hidden />
          <input
            type="search"
            placeholder="Nom, prénom, numéro…"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            autoComplete="off"
            spellCheck={false}
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
                  {isMetaBlocked(contact) ? " · Bloqué" : ""}
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

