import { useEffect, useMemo, useRef, useState } from "react";
import { FiChevronDown, FiChevronUp } from "react-icons/fi";

export default function AccountSelector({
  accounts = [],
  value,
  onChange,
  label = "Compte WhatsApp",
  conversations = [],
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const normalizedAccounts = useMemo(
    () => (Array.isArray(accounts) ? accounts : []),
    [accounts]
  );

  const selected = useMemo(() => {
    if (!normalizedAccounts.length) return null;
    return normalizedAccounts.find((acc) => acc.id === value) ?? normalizedAccounts[0];
  }, [normalizedAccounts, value]);

  // Calculer le nombre total de messages non lus par compte
  const unreadCountsByAccount = useMemo(() => {
    const counts = {};
    (Array.isArray(conversations) ? conversations : []).forEach((conv) => {
      const accountId = conv.account_id;
      if (accountId) {
        counts[accountId] = (counts[accountId] || 0) + (conv.unread_count || 0);
      }
    });
    return counts;
  }, [conversations]);

  if (!normalizedAccounts.length) {
    return (
      <div className="account-selector">
        <span>{label}</span>
        <em>Ajoute un compte dans Supabase pour commencer.</em>
      </div>
    );
  }

  const handleSelect = (accountId) => {
    onChange(accountId);
    setOpen(false);
  };

  return (
    <div className="account-selector" ref={containerRef}>
      <span className="account-selector__label">{label}</span>
      <button
        type="button"
        className="account-selector__button"
        onClick={() => setOpen((prev) => !prev)}
      >
        <div className="account-selector__text">
          <strong>{selected?.name}</strong>
          {selected?.phone_number && <small>{selected.phone_number}</small>}
        </div>
        <div className="account-selector__badges">
          {selected && unreadCountsByAccount[selected.id] > 0 && (
            <span className="account-selector__badge">
              {unreadCountsByAccount[selected.id] > 99 ? '99+' : unreadCountsByAccount[selected.id]}
            </span>
          )}
          {open ? <FiChevronUp /> : <FiChevronDown />}
        </div>
      </button>

      {open && (
        <div className="account-selector__menu">
          {normalizedAccounts.map((acc) => (
            <button
              type="button"
              key={acc.id}
              className={`account-selector__option ${
                acc.id === selected?.id ? "active" : ""
              }`}
              onClick={() => handleSelect(acc.id)}
            >
              <div>
                <strong>{acc.name}</strong>
                {acc.phone_number && <small>{acc.phone_number}</small>}
              </div>
              {unreadCountsByAccount[acc.id] > 0 && (
                <span className="account-selector__badge">
                  {unreadCountsByAccount[acc.id] > 99 ? '99+' : unreadCountsByAccount[acc.id]}
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

