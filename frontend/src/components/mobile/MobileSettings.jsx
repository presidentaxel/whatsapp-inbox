import { useState } from 'react';
import { FiArrowLeft, FiSearch, FiUser, FiMessageSquare, FiBell, FiGlobe, FiHelpCircle, FiUsers, FiSettings } from 'react-icons/fi';
import MobileAccountSettings from './MobileAccountSettings';
import MobileChatSettings from './MobileChatSettings';
import MobileNotificationSettings from './MobileNotificationSettings';
import MobileAppUpdates from './MobileAppUpdates';
import MobileInviteUser from './MobileInviteUser';
import '../../styles/mobile-settings.css';

export default function MobileSettings({ onBack }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeView, setActiveView] = useState('list');

  const settingsCategories = [
    {
      icon: <FiUser />,
      title: 'Compte',
      subtitle: 'Notifications de sécurité, changer de numéro',
      onClick: () => setActiveView('account')
    },
    {
      icon: <FiMessageSquare />,
      title: 'Discussions',
      subtitle: 'Thèmes, fonds d\'écran, historique des discussions',
      onClick: () => setActiveView('chat')
    },
    {
      icon: <FiBell />,
      title: 'Notifications',
      subtitle: 'Sonneries des messages, groupes et appels',
      onClick: () => setActiveView('notifications')
    },
    {
      icon: <FiGlobe />,
      title: 'Langue de l\'application',
      subtitle: 'Français (langue de l\'appareil)',
      onClick: () => {
        alert('La langue de l\'application est actuellement en français. Le support multilingue arrivera prochainement.');
      }
    },
    {
      icon: <FiHelpCircle />,
      title: 'Aide et commentaires',
      subtitle: 'Pages d\'aide, nous contacter, Politique de confidentialité',
      onClick: () => {
        alert('Cette fonctionnalité arrivera prochainement. Pour toute question, contactez le support.');
      }
    },
    {
      icon: <FiUsers />,
      title: 'Inviter un contact',
      onClick: () => setActiveView('invite')
    },
    {
      icon: <FiSettings />,
      title: 'Mises à jour de l\'application',
      onClick: () => setActiveView('updates')
    }
  ];

  const filteredCategories = settingsCategories.filter(category => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return category.title.toLowerCase().includes(term) || 
           (category.subtitle && category.subtitle.toLowerCase().includes(term));
  });

  if (activeView === 'account') {
    return <MobileAccountSettings onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'chat') {
    return <MobileChatSettings onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'notifications') {
    return (
      <div className="mobile-settings">
        <header className="mobile-settings__header">
          <button className="icon-btn" onClick={() => setActiveView('list')} title="Retour">
            <FiArrowLeft />
          </button>
          <h1>Notifications</h1>
        </header>
        <div className="mobile-settings__content" style={{ padding: '1rem' }}>
          <MobileNotificationSettings />
        </div>
      </div>
    );
  }

  if (activeView === 'updates') {
    return <MobileAppUpdates onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'invite') {
    return <MobileInviteUser onBack={() => setActiveView('list')} />;
  }

  return (
    <div className="mobile-settings">
      <header className="mobile-settings__header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Paramètres</h1>
      </header>

      <div className="mobile-settings__search">
        <div className="search-box">
          <FiSearch />
          <input
            type="text"
            placeholder="Rechercher dans les paramètres..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="mobile-settings__content">
        {filteredCategories.map((category, index) => (
          <div
            key={index}
            className="mobile-settings__item"
            onClick={category.onClick}
          >
            <div className="mobile-settings__item-icon">
              {category.icon}
            </div>
            <div className="mobile-settings__item-content">
              <div className="mobile-settings__item-title">{category.title}</div>
              {category.subtitle && (
                <div className="mobile-settings__item-subtitle">{category.subtitle}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

