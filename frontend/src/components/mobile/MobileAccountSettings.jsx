import { useState, useEffect, useRef } from 'react';
import { FiArrowLeft, FiSave, FiX, FiUser, FiMail, FiImage, FiEdit } from 'react-icons/fi';
import { supabaseClient } from '../../api/supabaseClient';
import { updateProfile, uploadProfilePicture } from '../../api/authApi';
import '../../styles/mobile-account-settings.css';

export default function MobileAccountSettings({ onBack }) {
  const [profile, setProfile] = useState(null);
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [profilePictureUrl, setProfilePictureUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const { data: { session } } = await supabaseClient.auth.getSession();
        if (session) {
          // Récupérer le profil depuis l'API
          const { api } = await import('../../api/axiosClient');
          const res = await api.get('/auth/me');
          if (res.data) {
            setProfile(res.data);
            setDisplayName(res.data.display_name || res.data.email?.split('@')[0] || '');
            setEmail(res.data.email || '');
            setProfilePictureUrl(res.data.profile_picture_url || res.data.profile?.profile_picture_url);
          }
        }
      } catch (error) {
        console.error('Erreur lors du chargement du profil:', error);
      }
    };
    loadProfile();
  }, []);

  const handleSave = async () => {
    setLoading(true);
    try {
      await updateProfile({ display_name: displayName || null });
      
      // Recharger le profil
      const { api } = await import('../../api/axiosClient');
      const res = await api.get('/auth/me');
      if (res.data) {
        setProfile(res.data);
        setDisplayName(res.data.display_name || res.data.email?.split('@')[0] || '');
        setProfilePictureUrl(res.data.profile_picture_url || res.data.profile?.profile_picture_url);
      }
      
      setIsEditing(false);
    } catch (error) {
      console.error('Erreur lors de la mise à jour du profil:', error);
      alert('Erreur lors de la mise à jour du profil');
    } finally {
      setLoading(false);
    }
  };

  const handlePhotoClick = () => {
    fileInputRef.current?.click();
  };

  const handlePhotoChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Vérifier le type
    if (!file.type.startsWith('image/')) {
      alert('Veuillez sélectionner une image');
      return;
    }

    // Vérifier la taille (5MB max)
    if (file.size > 5 * 1024 * 1024) {
      alert('L\'image est trop volumineuse (max 5MB)');
      return;
    }

    setUploading(true);
    try {
      const result = await uploadProfilePicture(file);
      setProfilePictureUrl(result.data.profile_picture_url);
      
      // Recharger le profil
      const { api } = await import('../../api/axiosClient');
      const res = await api.get('/auth/me');
      if (res.data) {
        setProfile(res.data);
        setProfilePictureUrl(res.data.profile_picture_url || res.data.profile?.profile_picture_url);
      }
    } catch (error) {
      console.error('Erreur lors de l\'upload de la photo:', error);
      alert('Erreur lors de l\'upload de la photo');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="mobile-account-settings">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Compte</h1>
        {isEditing ? (
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button 
              className="icon-btn" 
              onClick={() => { setIsEditing(false); setDisplayName(profile?.display_name || profile?.email?.split('@')[0] || ''); }}
              title="Annuler"
            >
              <FiX />
            </button>
            <button 
              className="icon-btn" 
              onClick={handleSave}
              disabled={loading}
              title="Enregistrer"
            >
              <FiSave />
            </button>
          </div>
        ) : (
          <button className="icon-btn" onClick={() => setIsEditing(true)} title="Modifier">
            <FiEdit />
          </button>
        )}
      </header>

      <div className="mobile-account-settings__content">
        <div className="mobile-account-settings__avatar-container">
          <div className="mobile-account-settings__avatar">
            {profilePictureUrl ? (
              <img 
                src={profilePictureUrl} 
                alt={displayName || email}
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.nextSibling.style.display = 'flex';
                }}
              />
            ) : null}
            <div className="mobile-account-settings__avatar-initial" style={{ display: profilePictureUrl ? 'none' : 'flex' }}>
              {(displayName || email || '?').charAt(0).toUpperCase()}
            </div>
          </div>
          <button 
            className="mobile-account-settings__avatar-edit"
            onClick={handlePhotoClick}
            disabled={uploading}
            title="Changer la photo"
          >
            <FiImage />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handlePhotoChange}
            style={{ display: 'none' }}
          />
        </div>

        <div className="mobile-account-settings__fields">
          <div className="mobile-account-settings__field">
            <label>
              <FiUser /> Nom d'affichage
            </label>
            {isEditing ? (
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Votre nom"
              />
            ) : (
              <div className="mobile-account-settings__value">
                {displayName || 'Non renseigné'}
              </div>
            )}
          </div>

          <div className="mobile-account-settings__field">
            <label>
              <FiMail /> Email
            </label>
            <div className="mobile-account-settings__value">
              {email || 'Non renseigné'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

