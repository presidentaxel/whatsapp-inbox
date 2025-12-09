import { useState, useEffect } from "react";
import { FiGlobe, FiType } from "react-icons/fi";

const LANGUAGES = [
  { value: "system", label: "Défaut du système (Français)" },
  { value: "fr", label: "Français" },
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "de", label: "Deutsch" },
];

const FONT_SIZES = [
  { value: 75, label: "75 %" },
  { value: 90, label: "90 %" },
  { value: 100, label: "100 % (par défaut)" },
  { value: 110, label: "110 %" },
  { value: 125, label: "125 %" },
  { value: 150, label: "150 %" },
  { value: 175, label: "175 %" },
  { value: 200, label: "200 %" },
];

export default function GeneralSettings() {
  const [startOnLogin, setStartOnLogin] = useState(() => {
    return localStorage.getItem("general_startOnLogin") === "true";
  });
  
  const [minimizeToTray, setMinimizeToTray] = useState(() => {
    return localStorage.getItem("general_minimizeToTray") !== "false"; // Default true
  });
  
  const [language, setLanguage] = useState(() => {
    return localStorage.getItem("general_language") || "system";
  });
  
  const [fontSize, setFontSize] = useState(() => {
    return parseInt(localStorage.getItem("general_fontSize") || "100", 10);
  });

  useEffect(() => {
    localStorage.setItem("general_startOnLogin", startOnLogin.toString());
  }, [startOnLogin]);

  useEffect(() => {
    localStorage.setItem("general_minimizeToTray", minimizeToTray.toString());
  }, [minimizeToTray]);

  useEffect(() => {
    localStorage.setItem("general_language", language);
    // Appliquer la langue si nécessaire (pour l'instant, juste stocker)
    document.documentElement.setAttribute("lang", language === "system" ? navigator.language.split("-")[0] : language);
  }, [language]);

  useEffect(() => {
    localStorage.setItem("general_fontSize", fontSize.toString());
    // Appliquer la taille de police globalement
    document.documentElement.style.fontSize = `${fontSize}%`;
  }, [fontSize]);

  return (
    <div className="general-settings">
      <section className="settings-content__section">
        <h2 className="settings-content__section-title">Démarrer et fermer</h2>
        
        <div className="general-settings__option">
          <div className="general-settings__option-content">
            <div className="general-settings__option-title">Démarrer WhatsApp lors de la connexion</div>
          </div>
          <label className="general-settings__toggle">
            <input
              type="checkbox"
              checked={startOnLogin}
              onChange={(e) => setStartOnLogin(e.target.checked)}
            />
            <span className="general-settings__toggle-slider"></span>
          </label>
        </div>

        <div className="general-settings__option">
          <div className="general-settings__option-content">
            <div className="general-settings__option-title">Minimiser dans la barre des tâches</div>
            <div className="general-settings__option-description">
              Faites en sorte que WhatsApp continue de fonctionner après avoir fermé la fenêtre de l'application
            </div>
          </div>
          <label className="general-settings__toggle">
            <input
              type="checkbox"
              checked={minimizeToTray}
              onChange={(e) => setMinimizeToTray(e.target.checked)}
            />
            <span className="general-settings__toggle-slider"></span>
          </label>
        </div>
      </section>

      <section className="settings-content__section">
        <h2 className="settings-content__section-title">Langue</h2>
        
        <div className="general-settings__select-wrapper">
          <FiGlobe className="general-settings__select-icon" />
          <select
            className="general-settings__select"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          >
            {LANGUAGES.map((lang) => (
              <option key={lang.value} value={lang.value}>
                {lang.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="settings-content__section">
        <h2 className="settings-content__section-title">Taille de la police</h2>
        
        <div className="general-settings__select-wrapper">
          <FiType className="general-settings__select-icon" />
          <select
            className="general-settings__select"
            value={fontSize}
            onChange={(e) => setFontSize(parseInt(e.target.value, 10))}
          >
            {FONT_SIZES.map((size) => (
              <option key={size.value} value={size.value}>
                {size.label}
              </option>
            ))}
          </select>
        </div>
        <div className="general-settings__hint">
          Utilisez Ctrl +/- pour augmenter ou diminuer la taille du texte
        </div>
      </section>
    </div>
  );
}

