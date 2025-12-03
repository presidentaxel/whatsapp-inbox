import { useState, useEffect } from "react";
import { FiArrowLeft, FiSmartphone, FiCheck } from "react-icons/fi";
import { getAccounts } from "../../api/accountsApi";

export default function MobileConnectedDevices({ accounts, activeAccount, onBack }) {
  const [devices, setDevices] = useState([]);

  useEffect(() => {
    // Les "appareils connectés" sont en fait les comptes WhatsApp actifs
    if (accounts && accounts.length > 0) {
      setDevices(accounts.map(acc => ({
        id: acc.id,
        name: acc.name || acc.phone_number || "Compte WhatsApp",
        phoneNumber: acc.phone_number || "Non renseigné",
        isActive: acc.is_active !== false,
        isCurrent: acc.id === activeAccount
      })));
    }
  }, [accounts, activeAccount]);

  return (
    <div className="mobile-connected-devices">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Appareils connectés</h1>
      </header>

      <div className="mobile-connected-devices__content">
        {devices.length === 0 ? (
          <div className="mobile-panel-empty">
            <p>Aucun appareil connecté</p>
          </div>
        ) : (
          devices.map((device) => (
            <div 
              key={device.id} 
              className={`mobile-connected-device ${device.isCurrent ? "mobile-connected-device--current" : ""}`}
            >
              <div className="mobile-connected-device__icon">
                <FiSmartphone />
              </div>
              <div className="mobile-connected-device__info">
                <div className="mobile-connected-device__name">
                  {device.name}
                  {device.isCurrent && (
                    <span className="mobile-connected-device__badge">
                      <FiCheck /> Actuel
                    </span>
                  )}
                </div>
                <div className="mobile-connected-device__phone">
                  {device.phoneNumber}
                </div>
              </div>
              {device.isActive && (
                <div className="mobile-connected-device__status">
                  <span className="mobile-connected-device__status-dot"></span>
                  Connecté
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

