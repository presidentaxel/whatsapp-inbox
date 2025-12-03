import { useEffect, useMemo, useRef, useState } from "react";
import { FiChevronDown, FiChevronUp } from "react-icons/fi";

export default function MobileAccountSelector({
  accounts = [],
  value,
  onChange,
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
    document.addEventListener("touchstart", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, []);

  const normalizedAccounts = useMemo(
    () => (Array.isArray(accounts) ? accounts : []),
    [accounts]
  );

  const selected = useMemo(() => {
    if (!normalizedAccounts.length) return null;
    return normalizedAccounts.find((acc) => acc.id === value) ?? normalizedAccounts[0];
  }, [normalizedAccounts, value]);

  if (!normalizedAccounts.length || normalizedAccounts.length <= 1) {
    return null;
  }

  const handleSelect = (accountId) => {
    onChange(accountId);
    setOpen(false);
  };

  return (
    <div className="mobile-account-selector" ref={containerRef}>
      <button
        type="button"
        className="mobile-account-selector__button"
        onClick={() => setOpen((prev) => !prev)}
      >
        <div className="mobile-account-selector__text">
          <span className="mobile-account-selector__name">{selected?.name}</span>
          {selected?.phone_number && (
            <span className="mobile-account-selector__phone">{selected.phone_number}</span>
          )}
        </div>
        <div className="mobile-account-selector__icon">
          {open ? <FiChevronUp /> : <FiChevronDown />}
        </div>
      </button>

      {open && (
        <div className="mobile-account-selector__menu">
          {normalizedAccounts.map((acc) => (
            <button
              type="button"
              key={acc.id}
              className={`mobile-account-selector__option ${
                acc.id === selected?.id ? "active" : ""
              }`}
              onClick={() => handleSelect(acc.id)}
            >
              <div className="mobile-account-selector__option-content">
                <span className="mobile-account-selector__option-name">{acc.name}</span>
                {acc.phone_number && (
                  <span className="mobile-account-selector__option-phone">
                    {acc.phone_number}
                  </span>
                )}
              </div>
              {acc.id === selected?.id && (
                <span className="mobile-account-selector__check">✓</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

