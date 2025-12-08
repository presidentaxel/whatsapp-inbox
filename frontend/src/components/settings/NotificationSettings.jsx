import { useState, useEffect, useMemo } from 'react';
import {
  FiBell,
  FiCheckCircle,
  FiXCircle,
  FiAlertTriangle,
  FiPlay,
  FiSlash,
} from 'react-icons/fi';
import {
  askForNotificationPermission,
  areNotificationsEnabled,
  showTestNotification,
} from '../../utils/notifications';

export default function NotificationSettings() {
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setNotificationsEnabled(areNotificationsEnabled());
  }, []);

  const status = useMemo(() => {
    const base = { Icon: FiBell };
    if (!('Notification' in window)) {
      return { ...base, text: 'Non supportées', tone: 'muted', Icon: FiSlash };
    }
    switch (Notification.permission) {
      case 'granted':
        return { ...base, text: 'Activées', tone: 'success', Icon: FiCheckCircle };
      case 'denied':
        return { ...base, text: 'Bloquées', tone: 'danger', Icon: FiXCircle };
      default:
        return { ...base, text: 'Non configurées', tone: 'warning', Icon: FiAlertTriangle };
    }
  }, [notificationsEnabled]);

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

  return (
    <div className="notif-settings">
      <div className="notif-settings__header">
        <div>
          <p className="notif-settings__eyebrow">Notifications</p>
          <h3 className="notif-settings__title">Push desktop</h3>
          <p className="notif-settings__subtitle">
            Alerte sur chaque message entrant (via webhook Supabase), même si l’onglet est en arrière-plan.
          </p>
        </div>
        <div className={`notif-settings__badge notif-settings__badge--${status.tone}`}>
          <span className="notif-settings__badge-icon">
            <status.Icon />
          </span>
          <span>{status.text}</span>
        </div>
      </div>

      <div className="notif-settings__card">
        <div className="notif-settings__card-row">
          <div>
            <p className="notif-settings__label">État navigateur</p>
            <p className="notif-settings__value">{status.text}</p>
            <p className="notif-settings__hint">
              Basé sur l’autorisation Notification API + Service Worker (Supabase triggers -> notif locale).
            </p>
          </div>
          <div className="notif-settings__actions">
            <button
              className="notif-btn notif-btn--primary"
              onClick={handleToggleNotifications}
              disabled={loading || Notification.permission === 'denied'}
            >
              {loading ? 'Demande en cours…' : notificationsEnabled ? 'Activées' : 'Activer'}
            </button>
            <button
              className="notif-btn notif-btn--ghost"
              onClick={handleTestNotification}
              disabled={!notificationsEnabled}
            >
              <FiPlay style={{ marginRight: 6 }} />
              Tester une notification
            </button>
          </div>
        </div>

        <div className="notif-settings__card-row">
          <div>
            <p className="notif-settings__label">Comptes WhatsApp (desktop)</p>
            <p className="notif-settings__hint">
              Notifications déclenchées pour tous les comptes sur réception webhook (INSERT messages).
              Filtrage par compte à venir (sélecteur).
            </p>
          </div>
        </div>

        {Notification.permission === 'denied' && (
          <div className="notif-settings__warning">
            <p className="notif-settings__warning-title">Notifications bloquées</p>
            <ul>
              <li>Chrome : cadenas 🔒 → Notifications → Autoriser</li>
              <li>Firefox : bouclier 🛡️ → Permissions → Notifications → Autoriser</li>
              <li>Safari : Préférences → Sites web → Notifications → Autoriser</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

