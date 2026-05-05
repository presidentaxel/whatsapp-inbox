import { useState } from 'react';
import {
  FiUser,
  FiMessageSquare,
  FiBell,
  FiGlobe,
  FiUsers,
  FiSettings,
  FiLogOut,
} from "react-icons/fi";
import MobileAccountSettings from './MobileAccountSettings';
import MobileChatSettings from './MobileChatSettings';
import MobileNotificationSettingsPage from './MobileNotificationSettingsPage';
import MobileAppUpdates from './MobileAppUpdates';
import MobileInviteUser from './MobileInviteUser';
import MobileLanguageSettings from './MobileLanguageSettings';
import MobileSettingsHome from './MobileSettingsHome';
import '../../styles/mobile-settings.css';

export default function MobileSettings({ onBack, onLogout }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeView, setActiveView] = useState('list');

  const settingsCategories = [
    {
      icon: <FiUser />,
      title: "Compte",
      subtitle: "Notifications de sécurité, changer de numéro",
      onClick: () => setActiveView("account"),
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
      onClick: () => setActiveView('language')
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
    },
    ...(typeof onLogout === "function"
      ? [
          {
            icon: <FiLogOut />,
            title: "Se déconnecter",
            subtitle: "Quitter la session sur cet appareil",
            onClick: onLogout,
          },
        ]
      : []),
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
    return <MobileNotificationSettingsPage onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'language') {
    return <MobileLanguageSettings onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'updates') {
    return <MobileAppUpdates onBack={() => setActiveView('list')} />;
  }

  if (activeView === 'invite') {
    return <MobileInviteUser onBack={() => setActiveView('list')} />;
  }

  return (
    <MobileSettingsHome
      onBack={onBack}
      searchTerm={searchTerm}
      onSearchChange={setSearchTerm}
      categories={filteredCategories}
    />
  );
}

