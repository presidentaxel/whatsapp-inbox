import { useState, useEffect } from 'react';
import { 
  askForNotificationPermission, 
  areNotificationsEnabled, 
  showTestNotification 
} from '../../utils/notifications';

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
        icon: '⚠️'
      };
    }

    switch (Notification.permission) {
      case 'granted':
        return {
          text: 'Activées',
          color: '#10b981',
          icon: '✅'
        };
      case 'denied':
        return {
          text: 'Bloquées',
          color: '#ef4444',
          icon: '❌'
        };
      default:
        return {
          text: 'Non configurées',
          color: '#f59e0b',
          icon: '⏸️'
        };
    }
  };

  const status = getNotificationStatus();

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h2 style={styles.title}>🔔 Notifications</h2>
        <p style={styles.subtitle}>
          Recevez des notifications pour les nouveaux messages
        </p>
      </div>

      <div style={styles.statusCard}>
        <div style={styles.statusRow}>
          <span style={styles.statusIcon}>{status.icon}</span>
          <span style={{ ...styles.statusText, color: status.color }}>
            {status.text}
          </span>
        </div>
      </div>

      <div style={styles.buttonGroup}>
        <button
          onClick={handleToggleNotifications}
          disabled={loading || Notification.permission === 'denied'}
          style={{
            ...styles.button,
            ...styles.primaryButton,
            ...(loading || Notification.permission === 'denied' ? styles.buttonDisabled : {})
          }}
        >
          {loading ? '⏳ Chargement...' : notificationsEnabled ? '✅ Activées' : '🔔 Activer les notifications'}
        </button>

        {notificationsEnabled && (
          <button
            onClick={handleTestNotification}
            style={{ ...styles.button, ...styles.secondaryButton }}
          >
            🧪 Tester une notification
          </button>
        )}
      </div>

      {Notification.permission === 'denied' && (
        <div style={styles.warningBox}>
          <strong>⚠️ Notifications bloquées</strong>
          <p style={styles.warningText}>
            Pour les réactiver, allez dans les paramètres de votre navigateur.
          </p>
        </div>
      )}

      <div style={styles.infoBox}>
        <h4 style={styles.infoTitle}>ℹ️ À propos</h4>
        <ul style={styles.list}>
          <li>✅ Fonctionne sur Android</li>
          <li>⚠️ Support limité sur iOS</li>
          <li>🔔 Notifications en temps réel</li>
          <li>📱 Optimisé pour mobile</li>
        </ul>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '20px',
    paddingBottom: '100px', // Espace pour la nav en bas
    minHeight: '100vh',
    backgroundColor: '#0b141a',
    color: '#e9edef'
  },
  header: {
    marginBottom: '24px'
  },
  title: {
    fontSize: '24px',
    fontWeight: 'bold',
    marginBottom: '8px',
    color: '#e9edef'
  },
  subtitle: {
    fontSize: '14px',
    color: '#8696a0',
    margin: 0
  },
  statusCard: {
    backgroundColor: '#202c33',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '20px'
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px'
  },
  statusIcon: {
    fontSize: '24px'
  },
  statusText: {
    fontSize: '18px',
    fontWeight: '600'
  },
  buttonGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    marginBottom: '20px'
  },
  button: {
    padding: '16px 24px',
    fontSize: '16px',
    fontWeight: '600',
    border: 'none',
    borderRadius: '12px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    width: '100%',
    color: 'white'
  },
  primaryButton: {
    backgroundColor: '#25d366'
  },
  secondaryButton: {
    backgroundColor: '#00a884'
  },
  buttonDisabled: {
    backgroundColor: '#2a3942',
    cursor: 'not-allowed',
    opacity: 0.6
  },
  warningBox: {
    backgroundColor: '#2a3942',
    border: '1px solid #f59e0b',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '20px'
  },
  warningText: {
    margin: '8px 0 0 0',
    fontSize: '14px',
    color: '#8696a0'
  },
  infoBox: {
    backgroundColor: '#202c33',
    borderRadius: '12px',
    padding: '16px'
  },
  infoTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: '600',
    color: '#e9edef'
  },
  list: {
    margin: '8px 0',
    paddingLeft: '20px',
    color: '#8696a0',
    fontSize: '14px',
    lineHeight: '1.8'
  }
};

