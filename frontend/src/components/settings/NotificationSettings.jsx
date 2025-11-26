import { useState, useEffect } from 'react';
import { 
  askForNotificationPermission, 
  areNotificationsEnabled, 
  showTestNotification 
} from '../../utils/notifications';

/**
 * Composant pour gérer les paramètres de notifications
 * À intégrer dans le panneau de paramètres existant
 */
export default function NotificationSettings() {
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Vérifier l'état initial des notifications
    setNotificationsEnabled(areNotificationsEnabled());
  }, []);

  const handleToggleNotifications = async () => {
    if (notificationsEnabled) {
      // On ne peut pas désactiver les notifications programmatiquement
      // L'utilisateur doit le faire manuellement dans les paramètres du navigateur
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
      // Afficher une notification de confirmation
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
      <h3 style={styles.title}>🔔 Notifications Push</h3>
      
      <div style={styles.statusCard}>
        <div style={styles.statusHeader}>
          <span style={styles.statusIcon}>{status.icon}</span>
          <span style={{ ...styles.statusText, color: status.color }}>
            {status.text}
          </span>
        </div>
        
        <p style={styles.description}>
          Recevez des notifications pour les nouveaux messages, même quand l'application est en arrière-plan.
        </p>
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
            Vous avez bloqué les notifications pour ce site. Pour les réactiver :
          </p>
          <ul style={styles.list}>
            <li>Chrome : Cliquez sur le cadenas 🔒 dans la barre d'adresse → Notifications → Autoriser</li>
            <li>Firefox : Cliquez sur le bouclier 🛡️ → Permissions → Notifications → Autoriser</li>
            <li>Safari : Préférences → Sites web → Notifications → Autoriser</li>
          </ul>
        </div>
      )}

      <div style={styles.infoBox}>
        <h4 style={styles.infoTitle}>ℹ️ À propos des notifications</h4>
        <ul style={styles.list}>
          <li>✅ Fonctionne sur Android (Chrome, Firefox, Samsung Internet)</li>
          <li>⚠️ Support limité sur iOS Safari</li>
          <li>🔋 Faible consommation de batterie</li>
          <li>📱 Nécessite l'installation de la PWA pour les meilleures performances</li>
          <li>🔒 Vos données restent privées et sécurisées</li>
        </ul>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '20px',
    maxWidth: '600px',
    margin: '0 auto'
  },
  title: {
    fontSize: '24px',
    fontWeight: 'bold',
    marginBottom: '20px',
    color: '#1f2937'
  },
  statusCard: {
    backgroundColor: '#f9fafb',
    border: '1px solid #e5e7eb',
    borderRadius: '12px',
    padding: '16px',
    marginBottom: '20px'
  },
  statusHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginBottom: '12px'
  },
  statusIcon: {
    fontSize: '24px'
  },
  statusText: {
    fontSize: '18px',
    fontWeight: '600'
  },
  description: {
    margin: '0',
    color: '#6b7280',
    fontSize: '14px',
    lineHeight: '1.5'
  },
  buttonGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    marginBottom: '20px'
  },
  button: {
    padding: '12px 24px',
    fontSize: '16px',
    fontWeight: '600',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    width: '100%'
  },
  primaryButton: {
    backgroundColor: '#10b981',
    color: 'white'
  },
  secondaryButton: {
    backgroundColor: '#6366f1',
    color: 'white'
  },
  buttonDisabled: {
    backgroundColor: '#d1d5db',
    cursor: 'not-allowed',
    opacity: 0.6
  },
  warningBox: {
    backgroundColor: '#fef3c7',
    border: '1px solid #fbbf24',
    borderRadius: '8px',
    padding: '16px',
    marginBottom: '20px'
  },
  warningText: {
    margin: '8px 0',
    fontSize: '14px',
    color: '#92400e'
  },
  infoBox: {
    backgroundColor: '#eff6ff',
    border: '1px solid #93c5fd',
    borderRadius: '8px',
    padding: '16px'
  },
  infoTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: '600',
    color: '#1e3a8a'
  },
  list: {
    margin: '8px 0',
    paddingLeft: '20px',
    color: '#374151',
    fontSize: '14px',
    lineHeight: '1.6'
  }
};

