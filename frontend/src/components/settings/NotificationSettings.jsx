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

        <div className="notif-settings__accounts">
          {accounts.length === 0 && (
            <div className="notif-settings__empty">Aucun compte WhatsApp configuré.</div>
          )}
          {accounts.map((acc) => {
            const id = acc.id;
            return (
              <div key={id} className="notif-settings__account-row">
                <div className="notif-settings__account-meta">
                  <p className="notif-settings__account-name">{acc.name || acc.phone_number}</p>
                  <p className="notif-settings__hint">ID: {acc.id}</p>
                </div>
                <div className="notif-settings__toggles">
                  <label className="notif-toggle">
                    <input
                      type="checkbox"
                      checked={getPref(id, 'messages')}
                      onChange={(e) => updatePref(id, 'messages', e.target.checked)}
                    />
                    <span>Notifications des messages</span>
                  </label>
                  <label className="notif-toggle">
                    <input
                      type="checkbox"
                      checked={getPref(id, 'previews')}
                      onChange={(e) => updatePref(id, 'previews', e.target.checked)}
                    />
                    <span>Voir les aperçus</span>
                  </label>
                  <label className="notif-toggle">
                    <input
                      type="checkbox"
                      checked={getPref(id, 'reactions')}
                      onChange={(e) => updatePref(id, 'reactions', e.target.checked)}
                    />
                    <span>Notifications des réactions</span>
                  </label>
                  <label className="notif-toggle">
                    <input
                      type="checkbox"
                      checked={getPref(id, 'status')}
                      onChange={(e) => updatePref(id, 'status', e.target.checked)}
                    />
                    <span>Réactions au statut</span>
                  </label>
                </div>
              </div>
            );
          })}
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

