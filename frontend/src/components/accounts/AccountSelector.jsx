import { useEffect, useMemo, useRef, useState } from "react";
import { FiChevronDown, FiChevronUp } from "react-icons/fi";

export default function AccountSelector({
  accounts,
  value,
  onChange,
  label = "Compte WhatsApp",
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

  const selected = useMemo(() => {
    if (!accounts.length) return null;
    return accounts.find((acc) => acc.id === value) ?? accounts[0];
  }, [accounts, value]);

  if (!accounts.length) {
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
        {open ? <FiChevronUp /> : <FiChevronDown />}
      </button>

      {open && (
        <div className="account-selector__menu">
          {accounts.map((acc) => (
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
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

