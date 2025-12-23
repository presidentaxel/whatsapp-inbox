import { useState, useEffect } from 'react';
import { FiArrowLeft, FiMail, FiUser, FiSend, FiRefreshCw } from 'react-icons/fi';
import { api } from '../../api/axiosClient';
import '../../styles/mobile-invite-user.css';

export default function MobileInviteUser({ onBack }) {
  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [loadingInvites, setLoadingInvites] = useState(false);

  const handleInvite = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    if (!email) {
      setError('Veuillez entrer une adresse email');
      return;
    }

    setLoading(true);
    try {
      const response = await api.post('/invitations/invite', {
        email,
        display_name: displayName || null
      });

      if (response.data.success) {
        setSuccess(true);
        setEmail('');
        setDisplayName('');
        loadPendingInvites();
      }
    } catch (err) {
      console.error('Error inviting user:', err);
      if (err.response?.data?.detail === 'user_already_exists') {
        setError('Cet utilisateur existe déjà');
      } else {
        setError(err.response?.data?.detail || 'Erreur lors de l\'envoi de l\'invitation');
      }
    } finally {
      setLoading(false);
    }
  };

  const loadPendingInvites = async () => {
    setLoadingInvites(true);
    try {
      const response = await api.get('/invitations/pending-invites');
      if (response.data.success) {
        setPendingInvites(response.data.invites || []);
      }
    } catch (err) {
      console.error('Error loading pending invites:', err);
    } finally {
      setLoadingInvites(false);
    }
  };

  const handleResendInvite = async (inviteEmail) => {
    setLoading(true);
    try {
      const response = await api.post('/invitations/resend-invite', {
        email: inviteEmail
      });

      if (response.data.success) {
        setSuccess(true);
        setTimeout(() => setSuccess(false), 3000);
      }
    } catch (err) {
      console.error('Error resending invite:', err);
      setError(err.response?.data?.detail || 'Erreur lors du renvoi de l\'invitation');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPendingInvites();
  }, []);

  return (
    <div className="mobile-invite-user">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Inviter un contact</h1>
      </header>

      <div className="mobile-invite-user__content">
        <form onSubmit={handleInvite} className="mobile-invite-user__form">
          <div className="mobile-invite-user__field">
            <label>
              <FiMail /> Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@example.com"
              required
            />
          </div>

          <div className="mobile-invite-user__field">
            <label>
              <FiUser /> Nom d'affichage (optionnel)
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Nom de l'utilisateur"
            />
          </div>

          {error && (
            <div className="mobile-invite-user__error">
              {error}
            </div>
          )}

          {success && (
            <div className="mobile-invite-user__success">
              Invitation envoyée avec succès !
            </div>
          )}

          <button
            type="submit"
            className="mobile-invite-user__submit"
            disabled={loading}
          >
            <FiSend />
            {loading ? 'Envoi...' : 'Envoyer l\'invitation'}
          </button>
        </form>

        {pendingInvites.length > 0 && (
          <div className="mobile-invite-user__pending">
            <h2>Invitations en attente</h2>
            <div className="mobile-invite-user__list">
              {pendingInvites.map((invite, index) => (
                <div key={index} className="mobile-invite-user__item">
                  <div className="mobile-invite-user__item-info">
                    <div className="mobile-invite-user__item-email">{invite.email}</div>
                    <div className="mobile-invite-user__item-date">
                      Invité le {(() => {
                        const timestamp = invite.invited_at;
                        // Interpréter comme UTC si pas de timezone explicite
                        const dateStr = typeof timestamp === 'string' && !timestamp.match(/[Z+-]\d{2}:\d{2}$/) 
                          ? timestamp + 'Z' 
                          : timestamp;
                        return new Date(dateStr).toLocaleDateString('fr-FR', { timeZone: 'Europe/Paris' });
                      })()}
                    </div>
                  </div>
                  <button
                    className="mobile-invite-user__resend-btn"
                    onClick={() => handleResendInvite(invite.email)}
                    disabled={loading}
                    title="Renvoyer l'invitation"
                  >
                    <FiRefreshCw />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

