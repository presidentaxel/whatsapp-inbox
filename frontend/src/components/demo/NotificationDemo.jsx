import { useState } from 'react';
import { 
  showNotification, 
  showMessageNotification,
  askForNotificationPermission,
  areNotificationsEnabled
} from '../../utils/notifications';

/**
 * Composant de démonstration pour tester les notifications
 * À supprimer ou désactiver en production
 */
export default function NotificationDemo() {
  const [status, setStatus] = useState('');

  const handleBasicNotification = async () => {
    if (!areNotificationsEnabled()) {
      const granted = await askForNotificationPermission();
      if (!granted) {
        setStatus('❌ Permission refusée');
        return;
      }
    }

    await showNotification('Notification simple', {
      body: 'Ceci est une notification de test basique'
    });
    setStatus('✅ Notification envoyée');
  };

  const handleVibrationNotification = async () => {
    await showNotification('Vibration', {
      body: 'Cette notification fait vibrer le téléphone',
      vibrate: [200, 100, 200, 100, 200]
    });
    setStatus('✅ Notification avec vibration envoyée');
  };

  const handlePersistentNotification = async () => {
    await showNotification('Notification persistante', {
      body: 'Cette notification reste affichée jusqu\'au clic',
      requireInteraction: true
    });
    setStatus('✅ Notification persistante envoyée');
  };

  const handleImageNotification = async () => {
    await showNotification('Notification avec image', {
      body: 'Cette notification contient une image',
      image: '/512x512.svg'
    });
    setStatus('✅ Notification avec image envoyée');
  };

  const handleMessageNotification = async () => {
    const mockConversation = {
      id: 'demo-123',
      contacts: {
        display_name: 'John Doe'
      }
    };
    
    await showMessageNotification(
      'John Doe',
      'Bonjour ! Ceci est un message de test pour la notification.',
      mockConversation.id
    );
    setStatus('✅ Notification de message envoyée');
  };

  const handleMultipleNotifications = async () => {
    // Envoyer plusieurs notifications rapidement
    await showNotification('Message 1', { body: 'Premier message', tag: 'msg-1' });
    setTimeout(async () => {
      await showNotification('Message 2', { body: 'Deuxième message', tag: 'msg-2' });
    }, 1000);
    setTimeout(async () => {
      await showNotification('Message 3', { body: 'Troisième message', tag: 'msg-3' });
    }, 2000);
    setStatus('✅ Plusieurs notifications envoyées');
  };

  const handleSilentNotification = async () => {
    await showNotification('Notification silencieuse', {
      body: 'Cette notification n\'émet pas de son',
      silent: true
    });
    setStatus('✅ Notification silencieuse envoyée');
  };

  const handleActionNotification = async () => {
    await showNotification('Actions disponibles', {
      body: 'Cliquez sur "Ouvrir" ou "Fermer"',
      actions: [
        { action: 'open', title: '👁️ Ouvrir' },
        { action: 'close', title: '❌ Fermer' }
      ],
      data: { url: '/' }
    });
    setStatus('✅ Notification avec actions envoyée');
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>🧪 Démo des Notifications</h2>
      <p style={styles.description}>
        Testez les différents types de notifications disponibles
      </p>

      {status && (
        <div style={styles.statusBox}>
          {status}
        </div>
      )}

      <div style={styles.grid}>
        <button onClick={handleBasicNotification} style={styles.button}>
          📱 Notification simple
        </button>

        <button onClick={handleVibrationNotification} style={styles.button}>
          📳 Avec vibration
        </button>

        <button onClick={handlePersistentNotification} style={styles.button}>
          📌 Persistante
        </button>

        <button onClick={handleImageNotification} style={styles.button}>
          🖼️ Avec image
        </button>

        <button onClick={handleMessageNotification} style={styles.button}>
          💬 Message WhatsApp
        </button>

        <button onClick={handleMultipleNotifications} style={styles.button}>
          📚 Notifications multiples
        </button>

        <button onClick={handleSilentNotification} style={styles.button}>
          🔇 Silencieuse
        </button>

        <button onClick={handleActionNotification} style={styles.button}>
          ⚡ Avec actions
        </button>
      </div>

      <div style={styles.info}>
        <strong>💡 Astuce :</strong> Mettez l'application en arrière-plan pour voir les notifications en action !
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '20px',
    maxWidth: '800px',
    margin: '0 auto'
  },
  title: {
    fontSize: '28px',
    fontWeight: 'bold',
    marginBottom: '10px',
    color: '#1f2937'
  },
  description: {
    color: '#6b7280',
    marginBottom: '20px'
  },
  statusBox: {
    padding: '12px',
    backgroundColor: '#f0fdf4',
    border: '1px solid #86efac',
    borderRadius: '8px',
    marginBottom: '20px',
    textAlign: 'center',
    fontWeight: '600'
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '12px',
    marginBottom: '20px'
  },
  button: {
    padding: '16px 20px',
    fontSize: '16px',
    fontWeight: '600',
    backgroundColor: '#3b82f6',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    transition: 'all 0.2s',
    textAlign: 'center'
  },
  info: {
    padding: '16px',
    backgroundColor: '#fef3c7',
    border: '1px solid #fbbf24',
    borderRadius: '8px',
    color: '#92400e',
    textAlign: 'center'
  }
};

