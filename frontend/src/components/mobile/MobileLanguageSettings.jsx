import { FiArrowLeft, FiGlobe } from "react-icons/fi";

export default function MobileLanguageSettings({ onBack }) {
  return (
    <div className="mobile-settings">
      <header className="mobile-settings__header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Langue de l'application</h1>
      </header>

      <div className="mobile-settings__content">
        <div className="mobile-settings__item" role="status" aria-live="polite">
          <div className="mobile-settings__item-icon">
            <FiGlobe />
          </div>
          <div className="mobile-settings__item-content">
            <div className="mobile-settings__item-title">Francais</div>
            <div className="mobile-settings__item-subtitle">
              La langue de l'appareil est appliquée. Le support multilingue arrive bientôt.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
