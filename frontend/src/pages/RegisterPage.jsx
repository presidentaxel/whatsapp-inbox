import { useState, useEffect } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import '../styles/register-page.css';

export default function RegisterPage() {
  // Récupérer les paramètres de l'URL
  const getSearchParams = () => {
    const params = new URLSearchParams(window.location.search);
    return {
      token: params.get('token'),
      token_hash: params.get('token_hash'),
      type: params.get('type')
    };
  };
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [tokenValid, setTokenValid] = useState(false);
  const [checkingToken, setCheckingToken] = useState(true);

  useEffect(() => {
    // Vérifier si on a un token d'invitation dans l'URL
    const token = searchParams.get('token');
    const type = searchParams.get('type');
    
    if (!token || type !== 'invite') {
      setError('Lien d\'invitation invalide ou expiré');
      setCheckingToken(false);
      return;
    }

    // Vérifier la validité du token
    const checkToken = async () => {
      try {
        // Essayer de récupérer les informations de l'utilisateur avec le token
        const { data, error: tokenError } = await supabaseClient.auth.getUser(token);
        
        if (tokenError || !data.user) {
          setError('Lien d\'invitation invalide ou expiré. Veuillez demander un nouveau lien.');
          setCheckingToken(false);
          return;
        }

        setEmail(data.user.email || '');
        setTokenValid(true);
        setCheckingToken(false);
      } catch (err) {
        console.error('Error checking token:', err);
        setError('Erreur lors de la vérification du lien d\'invitation');
        setCheckingToken(false);
      }
    };

    checkToken();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas');
      return;
    }

    if (password.length < 6) {
      setError('Le mot de passe doit contenir au moins 6 caractères');
      return;
    }

    setLoading(true);

    try {
      const params = getSearchParams();
      const token = params.token_hash || params.token;
      
      // Si on a un token, essayer de l'utiliser
      if (token) {
        const { error: verifyError } = await supabaseClient.auth.verifyOtp({
          token_hash: token,
          type: 'invite'
        });

        if (verifyError) {
          console.warn('OTP verification failed, trying direct update:', verifyError);
        }
      }

      // Mettre à jour le mot de passe et les métadonnées
      const { error: updateError } = await supabaseClient.auth.updateUser({
        password: password,
        data: {
          display_name: displayName || undefined
        }
      });

      if (updateError) {
        throw updateError;
      }

      // Se connecter automatiquement (la session devrait déjà être active)
      const { data: sessionData } = await supabaseClient.auth.getSession();
      
      if (!sessionData.session) {
        // Si pas de session, se connecter avec le mot de passe
        const { error: signInError } = await supabaseClient.auth.signInWithPassword({
          email,
          password
        });

        if (signInError) {
          throw signInError;
        }
      }

      // Rediriger vers l'application
      window.location.href = '/';
    } catch (err) {
      console.error('Registration error:', err);
      setError(err.message || 'Erreur lors de l\'inscription. Veuillez réessayer.');
    } finally {
      setLoading(false);
    }
  };

  if (checkingToken) {
    return (
      <div className="register-page">
        <div className="register-card">
          <h1>Vérification du lien d'invitation...</h1>
        </div>
      </div>
    );
  }

  if (!tokenValid) {
    return (
      <div className="register-page">
        <div className="register-card">
          <h1>Lien d'invitation invalide</h1>
          <p className="error">{error}</p>
          <p>Veuillez contacter votre administrateur pour recevoir un nouveau lien d'invitation.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="register-page">
      <div className="register-card">
        <h1>Créer votre compte</h1>
        <p>Complétez votre inscription en définissant votre mot de passe</p>
        
        <form onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              disabled
              className="disabled-input"
            />
          </label>

          <label>
            Nom d'affichage (optionnel)
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Votre nom"
            />
          </label>

          <label>
            Mot de passe
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={6}
              placeholder="Au moins 6 caractères"
            />
          </label>

          <label>
            Confirmer le mot de passe
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={6}
              placeholder="Répétez le mot de passe"
            />
          </label>

          {error && <p className="error">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? 'Création du compte...' : 'Créer mon compte'}
          </button>
        </form>
      </div>
    </div>
  );
}

