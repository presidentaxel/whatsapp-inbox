import { useState } from "react";
import { supabaseClient } from "../api/supabaseClient";
import { saveAuthSession } from "../utils/secureStorage";
import "../styles/mobile-login.css";

export default function MobileLoginPage({ onLoginSuccess }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const { data, error } = await supabaseClient.auth.signInWithPassword({
        email,
        password,
      });

      if (error) throw error;

      if (data.session) {
        // Sauvegarder la session de manière persistante
        saveAuthSession(data.session, rememberMe);
        onLoginSuccess(data.session);
      }
    } catch (err) {
      setError(err.message || "Erreur de connexion");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mobile-login">
      <div className="mobile-login__header">
        <div className="mobile-login__logo">
          <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
            <circle cx="30" cy="30" r="30" fill="#00a884"/>
            <path d="M30 15C21.716 15 15 21.716 15 30c0 2.616.67 5.076 1.852 7.221L15 45l8.062-2.116A14.93 14.93 0 0030 45c8.284 0 15-6.716 15-15s-6.716-15-15-15zm0 27c-2.38 0-4.619-.69-6.498-1.882l-.467-.277-4.838 1.27 1.293-4.718-.304-.483A11.916 11.916 0 0118 30c0-6.617 5.383-12 12-12s12 5.383 12 12-5.383 12-12 12z" fill="white"/>
          </svg>
        </div>
        <h1 className="mobile-login__title">WhatsApp LMDCVTC</h1>
        <p className="mobile-login__subtitle">
          Plateforme de gestion WhatsApp Business
        </p>
      </div>

      <form className="mobile-login__form" onSubmit={handleSubmit}>
        <div className="mobile-login__input-group">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="votre@email.com"
            required
            autoComplete="email"
            autoFocus
          />
        </div>

        <div className="mobile-login__input-group">
          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            required
            autoComplete="current-password"
          />
        </div>

        <label className="mobile-login__checkbox">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
          />
          <span>Rester connecté</span>
        </label>

        {error && <div className="mobile-login__error">{error}</div>}

        <button
          type="submit"
          className="mobile-login__button"
          disabled={loading}
        >
          {loading ? "Connexion..." : "Se connecter"}
        </button>
      </form>

      <div className="mobile-login__footer">
        <p>La Maison Du Chauffeur VTC</p>
      </div>
    </div>
  );
}

