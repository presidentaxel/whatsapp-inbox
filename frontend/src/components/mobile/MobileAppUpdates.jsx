import { useState, useEffect } from 'react';
import { FiArrowLeft, FiGitCommit, FiCalendar, FiTag } from 'react-icons/fi';
import '../../styles/mobile-app-updates.css';

/**
 * Composant pour afficher l'historique des mises à jour de l'application
 * Peut être alimenté manuellement ou via une API GitHub
 */
export default function MobileAppUpdates({ onBack }) {
  const [updates, setUpdates] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadUpdates();
  }, []);

  const loadUpdates = async () => {
    try {
      // Option 1: Charger depuis une API GitHub (si configurée)
      const githubRepo = import.meta.env.VITE_GITHUB_REPO; // Format: "owner/repo"
      if (githubRepo) {
        try {
          const response = await fetch(`https://api.github.com/repos/${githubRepo}/commits?per_page=20`);
          if (response.ok) {
            const commits = await response.json();
            const formattedUpdates = commits.map(commit => ({
              version: commit.sha.substring(0, 7),
              date: new Date(commit.commit.author.date),
              message: commit.commit.message.split('\n')[0], // Première ligne du message
              author: commit.commit.author.name,
              url: commit.html_url
            }));
            setUpdates(formattedUpdates);
            setLoading(false);
            return;
          }
        } catch (error) {
          console.warn('Erreur lors du chargement depuis GitHub:', error);
        }
      }

      // Option 2: Charger depuis une API locale
      try {
        const { api } = await import('../../api/axiosClient');
        const response = await api.get('/app/updates');
        if (response.data && response.data.updates && response.data.updates.length > 0) {
          setUpdates(response.data.updates);
          setLoading(false);
          return;
        }
      } catch (error) {
        // Ignorer silencieusement si l'endpoint n'existe pas
        if (error.response?.status !== 404) {
          console.warn('Erreur lors du chargement depuis l\'API locale:', error);
        }
      }

      // Option 3: Données statiques par défaut (à remplacer par vos vraies mises à jour)
      setUpdates([
        {
          version: '1.0.0',
          date: new Date(),
          message: 'Version initiale de l\'application',
          author: 'Équipe de développement',
          changes: [
            'Interface mobile complète',
            'Gestion des conversations WhatsApp',
            'Paramètres utilisateur',
            'Notifications push'
          ]
        }
      ]);
      setLoading(false);
    } catch (error) {
      console.error('Erreur lors du chargement des mises à jour:', error);
      setLoading(false);
    }
  };

  const formatDate = (date) => {
    if (!date) return '';
    const d = new Date(date);
    const now = new Date();
    const diff = now - d;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return "Aujourd'hui";
    if (days === 1) return "Hier";
    if (days < 7) return `Il y a ${days} jours`;
    if (days < 30) return `Il y a ${Math.floor(days / 7)} semaines`;
    if (days < 365) return `Il y a ${Math.floor(days / 30)} mois`;
    return d.toLocaleDateString('fr-FR', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  if (loading) {
    return (
      <div className="mobile-app-updates">
        <header className="mobile-panel-header">
          <button className="icon-btn" onClick={onBack} title="Retour">
            <FiArrowLeft />
          </button>
          <h1>Mises à jour</h1>
        </header>
        <div className="mobile-app-updates__loading">
          <p>Chargement des mises à jour...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mobile-app-updates">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Mises à jour</h1>
      </header>

      <div className="mobile-app-updates__content">
        {updates.length === 0 ? (
          <div className="mobile-app-updates__empty">
            <p>Aucune mise à jour disponible</p>
          </div>
        ) : (
          <div className="mobile-app-updates__list">
            {updates.map((update, index) => (
              <div key={index} className="mobile-app-updates__item">
                <div className="mobile-app-updates__header">
                  <div className="mobile-app-updates__version">
                    <FiTag />
                    <span>{update.version}</span>
                  </div>
                  <div className="mobile-app-updates__date">
                    <FiCalendar />
                    <span>{formatDate(update.date)}</span>
                  </div>
                </div>
                <div className="mobile-app-updates__message">
                  {update.message}
                </div>
                {update.changes && update.changes.length > 0 && (
                  <ul className="mobile-app-updates__changes">
                    {update.changes.map((change, idx) => (
                      <li key={idx}>{change}</li>
                    ))}
                  </ul>
                )}
                {update.author && (
                  <div className="mobile-app-updates__author">
                    <FiGitCommit />
                    <span>{update.author}</span>
                  </div>
                )}
                {update.url && (
                  <a 
                    href={update.url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="mobile-app-updates__link"
                  >
                    Voir sur GitHub →
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

