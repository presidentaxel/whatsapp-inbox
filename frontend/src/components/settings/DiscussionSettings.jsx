import { useState, useEffect } from 'react';
import { FiSun, FiMoon, FiMonitor, FiImage, FiCheck } from 'react-icons/fi';
import { useTheme } from '../../hooks/useTheme';

const STORAGE_KEY = 'discussion_prefs_v1';

const THEMES = [
  { value: 'system', label: 'Thème par défaut du système', icon: FiMonitor },
  { value: 'light', label: 'Clair', icon: FiSun },
  { value: 'dark', label: 'Sombre', icon: FiMoon },
];

const WALLPAPER_COLORS = [
  { id: 'default', label: 'Par défaut', color: null },
  { id: 'teal', label: 'Teal', color: '#075e54' },
  { id: 'blue', label: 'Bleu', color: '#1a2332' },
  { id: 'grey', label: 'Gris', color: '#2a2a2a' },
  { id: 'purple', label: 'Violet', color: '#3d2a4d' },
  { id: 'brown', label: 'Marron', color: '#3a2a1a' },
  { id: 'red', label: 'Rouge', color: '#4a1a1a' },
  { id: 'dark-teal', label: 'Teal foncé', color: '#0a3d2a' },
];

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {
      theme: 'system',
      wallpaper: 'default',
      wallpaperDoodles: true,
      spellCheck: true,
      emojiReplace: true,
      enterToSend: true,
    };
  } catch {
    return {
      theme: 'system',
      wallpaper: 'default',
      wallpaperDoodles: true,
      spellCheck: true,
      emojiReplace: true,
      enterToSend: true,
    };
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    // Appliquer le thème immédiatement
    applyTheme(prefs.theme);
    // Appliquer le fond d'écran
    applyWallpaper(prefs.wallpaper, prefs.wallpaperDoodles);
  } catch {
    // ignore
  }
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  } else {
    root.setAttribute('data-theme', theme);
  }
}

function applyWallpaper(wallpaper, withDoodles) {
  const root = document.documentElement;
  if (wallpaper === 'default') {
    root.style.setProperty('--chat-wallpaper-color', 'transparent');
    root.style.setProperty('--chat-wallpaper-opacity', '0');
    root.style.setProperty('--chat-wallpaper-pattern', 'none');
  } else {
    const color = WALLPAPER_COLORS.find(w => w.id === wallpaper)?.color;
    if (color) {
      root.style.setProperty('--chat-wallpaper-color', color);
      root.style.setProperty('--chat-wallpaper-opacity', '0.15');
      
      if (withDoodles) {
        root.style.setProperty('--chat-wallpaper-pattern', 'url("data:image/svg+xml,%3Csvg width=\'100\' height=\'100\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cdefs%3E%3Cpattern id=\'doodles\' patternUnits=\'userSpaceOnUse\' width=\'100\' height=\'100\'%3E%3Ccircle cx=\'20\' cy=\'20\' r=\'2\' fill=\'rgba(255,255,255,0.08)\'/%3E%3Ccircle cx=\'80\' cy=\'40\' r=\'1.5\' fill=\'rgba(255,255,255,0.06)\'/%3E%3Ccircle cx=\'50\' cy=\'70\' r=\'1\' fill=\'rgba(255,255,255,0.04)\'/%3E%3Ccircle cx=\'30\' cy=\'90\' r=\'1.5\' fill=\'rgba(255,255,255,0.05)\'/%3E%3Ccircle cx=\'70\' cy=\'10\' r=\'1\' fill=\'rgba(255,255,255,0.04)\'/%3E%3C/pattern%3E%3C/defs%3E%3Crect width=\'100\' height=\'100\' fill=\'url(%23doodles)\'/%3E%3C/svg%3E")');
      } else {
        root.style.setProperty('--chat-wallpaper-pattern', 'none');
      }
    }
  }
}

export default function DiscussionSettings() {
  const themePrefs = useTheme(); // Utiliser le hook pour synchroniser avec l'application
  const [prefs, setPrefs] = useState(themePrefs);
  const [showThemeDialog, setShowThemeDialog] = useState(false);
  const [showWallpaperDialog, setShowWallpaperDialog] = useState(false);

  // Synchroniser avec les préférences du hook
  useEffect(() => {
    setPrefs(themePrefs);
  }, [themePrefs]);

  const updatePref = (key, value) => {
    const newPrefs = { ...prefs, [key]: value };
    setPrefs(newPrefs);
    savePrefs(newPrefs);
    // Appliquer immédiatement
    if (key === 'theme') {
      applyTheme(value);
    } else if (key === 'wallpaper' || key === 'wallpaperDoodles') {
      applyWallpaper(newPrefs.wallpaper, newPrefs.wallpaperDoodles);
    }
    // Déclencher un événement pour notifier les autres composants
    window.dispatchEvent(new Event('prefsUpdated'));
  };

  const handleThemeSelect = (theme) => {
    updatePref('theme', theme);
    setShowThemeDialog(false);
  };

  const handleWallpaperSelect = (wallpaperId) => {
    updatePref('wallpaper', wallpaperId);
  };

  const currentThemeLabel = THEMES.find(t => t.value === prefs.theme)?.label || 'Thème par défaut du système';
  const currentThemeIcon = THEMES.find(t => t.value === prefs.theme)?.icon || FiMonitor;

  return (
    <div className="discussion-settings">
      <div className="discussion-settings__section">
        <h3 className="discussion-settings__section-title">Affichage</h3>
        
        <button
          className="discussion-settings__option"
          onClick={() => setShowThemeDialog(true)}
        >
          <div className="discussion-settings__option-content">
            <strong>Thème</strong>
            <small>{currentThemeLabel}</small>
          </div>
          <FiMonitor className="discussion-settings__option-arrow" />
        </button>

        <button
          className="discussion-settings__option"
          onClick={() => setShowWallpaperDialog(true)}
        >
          <div className="discussion-settings__option-content">
            <strong>Fond d'écran</strong>
          </div>
          <FiImage className="discussion-settings__option-arrow" />
        </button>
      </div>

      <div className="discussion-settings__divider" />

      <div className="discussion-settings__section">
        <h3 className="discussion-settings__section-title">Paramètres des discussions</h3>
        
        <label className="discussion-settings__toggle-option">
          <div className="discussion-settings__option-content">
            <strong>Vérification orthographique</strong>
            <small>Vérifier l'orthographe pendant la saisie</small>
          </div>
          <label className="discussion-settings__toggle-wrapper">
            <input
              type="checkbox"
              checked={prefs.spellCheck}
              onChange={(e) => updatePref('spellCheck', e.target.checked)}
            />
            <div className="discussion-settings__toggle-slider"></div>
          </label>
        </label>

        <label className="discussion-settings__toggle-option">
          <div className="discussion-settings__option-content">
            <strong>Remplacer le texte par un emoji</strong>
            <small>Les emojis remplaceront certaines parties de texte à mesure que vous écrivez</small>
          </div>
          <label className="discussion-settings__toggle-wrapper">
            <input
              type="checkbox"
              checked={prefs.emojiReplace}
              onChange={(e) => updatePref('emojiReplace', e.target.checked)}
            />
            <div className="discussion-settings__toggle-slider"></div>
          </label>
        </label>

        <label className="discussion-settings__toggle-option">
          <div className="discussion-settings__option-content">
            <strong>Entrée pour envoyer</strong>
            <small>La touche Entrée enverra votre message.</small>
          </div>
          <label className="discussion-settings__toggle-wrapper">
            <input
              type="checkbox"
              checked={prefs.enterToSend}
              onChange={(e) => updatePref('enterToSend', e.target.checked)}
            />
            <div className="discussion-settings__toggle-slider"></div>
          </label>
        </label>
      </div>

      {/* Dialog Thème */}
      {showThemeDialog && (
        <div className="discussion-settings__dialog-overlay" onClick={() => setShowThemeDialog(false)}>
          <div className="discussion-settings__dialog" onClick={(e) => e.stopPropagation()}>
            <h4 className="discussion-settings__dialog-title">Thème</h4>
            <div className="discussion-settings__dialog-options">
              {THEMES.map((theme) => {
                const Icon = theme.icon;
                return (
                  <label key={theme.value} className="discussion-settings__radio-option">
                    <input
                      type="radio"
                      name="theme"
                      value={theme.value}
                      checked={prefs.theme === theme.value}
                      onChange={() => handleThemeSelect(theme.value)}
                    />
                    <Icon className="discussion-settings__radio-icon" />
                    <span>{theme.label}</span>
                  </label>
                );
              })}
            </div>
            <div className="discussion-settings__dialog-actions">
              <button
                className="discussion-settings__dialog-btn-cancel"
                onClick={() => setShowThemeDialog(false)}
              >
                Annuler
              </button>
              <button
                className="discussion-settings__dialog-btn-ok"
                onClick={() => setShowThemeDialog(false)}
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dialog Fond d'écran */}
      {showWallpaperDialog && (
        <div className="discussion-settings__dialog-overlay" onClick={() => setShowWallpaperDialog(false)}>
          <div className="discussion-settings__dialog discussion-settings__dialog--wallpaper" onClick={(e) => e.stopPropagation()}>
            <h4 className="discussion-settings__dialog-title">Fond d'écran de la discussion</h4>
            
            <label className="discussion-settings__checkbox-option">
              <input
                type="checkbox"
                checked={prefs.wallpaperDoodles}
                onChange={(e) => updatePref('wallpaperDoodles', e.target.checked)}
              />
              <span>Ajouter WhatsApp Doodles</span>
            </label>

            <div className="discussion-settings__wallpaper-grid">
              {WALLPAPER_COLORS.map((wallpaper) => (
                <button
                  key={wallpaper.id}
                  className={`discussion-settings__wallpaper-swatch ${
                    prefs.wallpaper === wallpaper.id ? 'discussion-settings__wallpaper-swatch--selected' : ''
                  }`}
                  onClick={() => handleWallpaperSelect(wallpaper.id)}
                  style={wallpaper.color ? { backgroundColor: wallpaper.color } : {}}
                >
                  {wallpaper.color ? null : (
                    <span className="discussion-settings__wallpaper-label">Par défaut</span>
                  )}
                  {prefs.wallpaper === wallpaper.id && (
                    <FiCheck className="discussion-settings__wallpaper-check" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

