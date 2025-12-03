import { useState, useEffect } from 'react';
import { FiArrowLeft, FiCheck } from 'react-icons/fi';
import '../../styles/mobile-chat-settings.css';

export default function MobileChatSettings({ onBack }) {
  const [theme, setTheme] = useState(localStorage.getItem('chatTheme') || 'default');
  const [wallpaper, setWallpaper] = useState(localStorage.getItem('chatWallpaper') || 'default');
  const [enterKeySends, setEnterKeySends] = useState(localStorage.getItem('enterKeySends') === 'true');
  const [mediaVisibility, setMediaVisibility] = useState(localStorage.getItem('mediaVisibility') !== 'false');
  const [fontSize, setFontSize] = useState(localStorage.getItem('fontSize') || 'medium');

  useEffect(() => {
    localStorage.setItem('chatTheme', theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem('chatWallpaper', wallpaper);
  }, [wallpaper]);

  useEffect(() => {
    localStorage.setItem('enterKeySends', enterKeySends.toString());
  }, [enterKeySends]);

  useEffect(() => {
    localStorage.setItem('mediaVisibility', mediaVisibility.toString());
  }, [mediaVisibility]);

  useEffect(() => {
    localStorage.setItem('fontSize', fontSize);
  }, [fontSize]);

  const themes = [
    { id: 'default', name: 'Par défaut' },
    { id: 'light', name: 'Clair' },
    { id: 'dark', name: 'Sombre' },
    { id: 'blue', name: 'Bleu' },
    { id: 'green', name: 'Vert' },
  ];

  const wallpapers = [
    { id: 'default', name: 'Par défaut' },
    { id: 'solid', name: 'Couleur unie' },
    { id: 'pattern1', name: 'Motif 1' },
    { id: 'pattern2', name: 'Motif 2' },
  ];

  const fontSizes = [
    { id: 'small', name: 'Petit', size: '0.875rem' },
    { id: 'medium', name: 'Moyen', size: '1rem' },
    { id: 'large', name: 'Grand', size: '1.125rem' },
  ];

  return (
    <div className="mobile-chat-settings">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Discussions</h1>
      </header>

      <div className="mobile-chat-settings__content">
        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Thème</h2>
          <div className="mobile-chat-settings__options">
            {themes.map((t) => (
              <div
                key={t.id}
                className={`mobile-chat-settings__option ${theme === t.id ? 'active' : ''}`}
                onClick={() => setTheme(t.id)}
              >
                <span>{t.name}</span>
                {theme === t.id && <FiCheck />}
              </div>
            ))}
          </div>
        </div>

        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Fond d'écran</h2>
          <div className="mobile-chat-settings__options">
            {wallpapers.map((w) => (
              <div
                key={w.id}
                className={`mobile-chat-settings__option ${wallpaper === w.id ? 'active' : ''}`}
                onClick={() => setWallpaper(w.id)}
              >
                <span>{w.name}</span>
                {wallpaper === w.id && <FiCheck />}
              </div>
            ))}
          </div>
        </div>

        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Envoi de messages</h2>
          <div className="mobile-chat-settings__toggle">
            <div className="mobile-chat-settings__toggle-info">
              <span className="mobile-chat-settings__toggle-label">Envoyer avec Entrée</span>
              <span className="mobile-chat-settings__toggle-description">
                Appuyez sur Entrée pour envoyer. Utilisez Maj+Entrée pour un nouveau ligne
              </span>
            </div>
            <button
              className={`mobile-chat-settings__toggle-btn ${enterKeySends ? 'active' : ''}`}
              onClick={() => setEnterKeySends(!enterKeySends)}
            >
              <span className="mobile-chat-settings__toggle-slider"></span>
            </button>
          </div>
        </div>

        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Médias et liens</h2>
          <div className="mobile-chat-settings__toggle">
            <div className="mobile-chat-settings__toggle-info">
              <span className="mobile-chat-settings__toggle-label">Aperçu des médias</span>
              <span className="mobile-chat-settings__toggle-description">
                Afficher automatiquement les images, vidéos et liens dans les discussions
              </span>
            </div>
            <button
              className={`mobile-chat-settings__toggle-btn ${mediaVisibility ? 'active' : ''}`}
              onClick={() => setMediaVisibility(!mediaVisibility)}
            >
              <span className="mobile-chat-settings__toggle-slider"></span>
            </button>
          </div>
        </div>

        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Taille de la police</h2>
          <div className="mobile-chat-settings__options">
            {fontSizes.map((f) => (
              <div
                key={f.id}
                className={`mobile-chat-settings__option ${fontSize === f.id ? 'active' : ''}`}
                onClick={() => setFontSize(f.id)}
              >
                <span>{f.name}</span>
                {fontSize === f.id && <FiCheck />}
              </div>
            ))}
          </div>
        </div>

        <div className="mobile-chat-settings__section">
          <h2 className="mobile-chat-settings__section-title">Historique des discussions</h2>
          <div className="mobile-chat-settings__action">
            <span>Effacer toutes les discussions</span>
            <button className="mobile-chat-settings__action-btn" onClick={() => {
              if (confirm('Êtes-vous sûr de vouloir effacer toutes les discussions ? Cette action est irréversible.')) {
                // TODO: Implémenter l'effacement des discussions
                alert('Fonctionnalité à implémenter');
              }
            }}>
              Effacer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

