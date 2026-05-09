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
import { platformAlert } from '../../platform/platformDialogs';

const STORAGE_KEY = 'notif_prefs_v1';

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore
  }
}

const NOTIFICATION_TYPES = [
  { key: 'messages', label: 'Notifications des messages', description: 'Recevoir une notification pour chaque nouveau message' },
  { key: 'previews', label: 'Voir les aperçus', description: 'Afficher un aperçu du message dans la notification' },
  { key: 'reactions', label: 'Notifications des réactions', description: 'Recevoir une notification pour les réactions aux messages' },
  { key: 'status', label: 'Réactions au statut', description: 'Recevoir des notifications pour les réactions aux statuts' },
];

export default function NotificationSettings({ accounts = [] }) {
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [prefs, setPrefs] = useState(() => loadPrefs());

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
      await platformAlert(
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
      await platformAlert('⚠️ Activez d\'abord les notifications');
      return;
    }

    await showTestNotification();
  };

  const updatePref = (accountId, field, value) => {
    setPrefs((prev) => {
      const next = {
        ...prev,
        [accountId]: {
          messages: true,
          previews: true,
          reactions: true,
          status: true,
          ...(prev[accountId] || {}),
          [field]: value,
        },
      };
      savePrefs(next);
      return next;
    });
  };

  const getPref = (accountId, field) => prefs[accountId]?.[field] ?? true;

  return (
    <div className="notif-settings-table">
      <div className="notif-settings-table__header">
        <div>
          <p className="notif-settings-table__eyebrow">Notifications</p>
          <h3 className="notif-settings-table__title">Paramètres de notifications</h3>
          <p className="notif-settings-table__subtitle">
            Configurez les notifications pour chaque compte WhatsApp.
          </p>
        </div>
        <div className="notif-settings-table__global-status">
          <div className={`notif-settings-table__badge notif-settings-table__badge--${status.tone}`}>
            <span className="notif-settings-table__badge-icon">
              <status.Icon />
            </span>
            <span>{status.text}</span>
          </div>
          <div className="notif-settings-table__actions">
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
              Tester
            </button>
          </div>
        </div>
      </div>

      {!('Notification' in window) && (
        <div className="notif-settings-table__warning">
          <p>Votre navigateur ne supporte pas les notifications.</p>
        </div>
      )}

      {Notification.permission === 'denied' && (
        <div className="notif-settings-table__warning">
          <p className="notif-settings-table__warning-title">Notifications bloquées</p>
          <ul>
            <li>Chrome : cadenas 🔒 → Notifications → Autoriser</li>
            <li>Firefox : bouclier 🛡️ → Permissions → Notifications → Autoriser</li>
            <li>Safari : Préférences → Sites web → Notifications → Autoriser</li>
          </ul>
        </div>
      )}

      {accounts.length === 0 ? (
        <div className="notif-settings-table__empty">
          Aucun compte WhatsApp configuré.
        </div>
      ) : (
        <div className="notif-settings-table__wrapper">
          <table className="notif-settings-table__table">
            <thead>
              <tr>
                <th className="notif-settings-table__account-col">Compte WhatsApp</th>
                {NOTIFICATION_TYPES.map((type) => (
                  <th key={type.key} className="notif-settings-table__type-col">
                    <div className="notif-settings-table__type-header">
                      <strong>{type.label}</strong>
                      <small>{type.description}</small>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td className="notif-settings-table__account-cell">
                    <div className="notif-settings-table__account-info">
                      <strong>{account.name || account.phone_number}</strong>
                      {account.phone_number && (
                        <small>{account.phone_number}</small>
                      )}
                    </div>
                  </td>
                  {NOTIFICATION_TYPES.map((type) => {
                    const isEnabled = getPref(account.id, type.key);
                    return (
                      <td key={type.key} className="notif-settings-table__toggle-cell">
                        <label className="notif-settings-table__toggle">
                          <input
                            type="checkbox"
                            checked={isEnabled}
                            onChange={(e) => updatePref(account.id, type.key, e.target.checked)}
                            disabled={!notificationsEnabled}
                          />
                          <span
                            className={`notif-settings-table__toggle-switch ${
                              isEnabled ? 'notif-settings-table__toggle-switch--on' : ''
                            } ${!notificationsEnabled ? 'notif-settings-table__toggle-switch--disabled' : ''}`}
                          >
                            <span className="notif-settings-table__toggle-label">
                              {isEnabled ? 'Oui' : 'Non'}
                            </span>
                          </span>
                        </label>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
