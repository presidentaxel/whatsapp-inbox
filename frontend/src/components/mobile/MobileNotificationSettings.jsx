import { useState, useEffect } from 'react';
import { FiCheck, FiX, FiAlertTriangle, FiPause, FiBell, FiAlertCircle } from 'react-icons/fi';
import { 
  askForNotificationPermission, 
  areNotificationsEnabled, 
  showTestNotification 
} from '../../utils/notifications';
import '../../styles/mobile-notification-settings.css';

/**
 * Composant mobile pour gérer les paramètres de notifications
 * Version mobile optimisée
 */
export default function MobileNotificationSettings() {
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setNotificationsEnabled(areNotificationsEnabled());
  }, []);

  const handleToggleNotifications = async () => {
    if (notificationsEnabled) {
      alert(
        '⚠️ Pour désactiver les notifications, allez dans les paramètres de votre navigateur.\n\n' +
        'Chrome: Paramètres > Confidentialité > Notifications\n' +
        'Firefox: Paramètres > Vie privée > Notifications'
      );
      return;
    }

    setLoading(true);
    const granted = await askForNotificationPermission();
    setNotificationsEnabled(granted);
    setLoading(false);

    if (granted) {
      setTimeout(() => {
        showTestNotification();
      }, 500);
    }
  };

  const handleTestNotification = async () => {
    if (!notificationsEnabled) {
      alert('⚠️ Activez d\'abord les notifications');
      return;
    }

    await showTestNotification();
  };

  const getNotificationStatus = () => {
    if (!('Notification' in window)) {
      return {
        text: 'Non supportées',
        color: '#94a3b8',
        icon: <FiAlertCircle />
      };
    }

    switch (Notification.permission) {
      case 'granted':
        return {
          text: 'Activées',
          color: '#10b981',
          icon: <FiCheck />
        };
      case 'denied':
        return {
          text: 'Bloquées',
          color: '#ef4444',
          icon: <FiX />
        };
      default:
        return {
          text: 'Non configurées',
          color: '#f59e0b',
          icon: <FiPause />
        };
    }
  };

  const status = getNotificationStatus();

  return (
    <div className="mobile-notification-settings">
      <div className="mobile-notification-settings__section">
        <h2 className="mobile-notification-settings__section-title">État</h2>
        <div className="mobile-notification-settings__status-item">
          <div className="mobile-notification-settings__status-info">
            <span className="mobile-notification-settings__status-label">Notifications</span>
            <span className="mobile-notification-settings__status-value" style={{ color: status.color }}>
              <span className="mobile-notification-settings__status-icon">{status.icon}</span>
              {status.text}
            </span>
          </div>
        </div>
      </div>

      <div className="mobile-notification-settings__section">
        <h2 className="mobile-notification-settings__section-title">Paramètres</h2>
        <div className="mobile-notification-settings__toggle">
          <div className="mobile-notification-settings__toggle-info">
            <span className="mobile-notification-settings__toggle-label">Activer les notifications</span>
            <span className="mobile-notification-settings__toggle-description">
              Recevez des notifications pour les nouveaux messages
            </span>
          </div>
          <button
            className={`mobile-notification-settings__toggle-btn ${notificationsEnabled ? 'active' : ''}`}
            onClick={handleToggleNotifications}
            disabled={loading || Notification.permission === 'denied'}
          >
            <span className="mobile-notification-settings__toggle-slider"></span>
          </button>
        </div>
      </div>

      {notificationsEnabled && (
        <div className="mobile-notification-settings__section">
          <h2 className="mobile-notification-settings__section-title">Actions</h2>
          <div className="mobile-notification-settings__action" onClick={handleTestNotification}>
            <span>Tester une notification</span>
            <button className="mobile-notification-settings__action-btn">Tester</button>
          </div>
        </div>
      )}

      {Notification.permission === 'denied' && (
        <div className="mobile-notification-settings__section">
          <div className="mobile-notification-settings__status-item">
            <div className="mobile-notification-settings__status-info">
              <span className="mobile-notification-settings__status-label" style={{ color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FiAlertTriangle /> Notifications bloquées
              </span>
              <span className="mobile-notification-settings__status-value">
                Pour les réactiver, allez dans les paramètres de votre navigateur.
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

