import { useState, useEffect } from "react";
import { supabaseClient } from "./api/supabaseClient";
import { getDeviceType } from "./utils/deviceDetection";
import { getAuthSession, saveAuthSession, clearAuthSession } from "./utils/secureStorage";
import { useTheme } from "./hooks/useTheme";

// Desktop
import InboxPage from "./pages/InboxPage";
import AppHeader from "./components/layout/AppHeader";
import LoginPage from "./pages/LoginPage";
import { AuthProvider, useAuth } from "./context/AuthContext";

// Mobile
import MobileLoginPage from "./pages/MobileLoginPage";
import MobileInboxPage from "./pages/MobileInboxPage";
import RegisterPage from "./pages/RegisterPage";

// Composant mobile (sans AuthProvider, gestion directe)
function MobileApp() {
  useTheme(); // Initialiser le thème au chargement de l'application
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Vérifier s'il y a une session sauvegardée
    const savedSession = getAuthSession();
    
    if (savedSession) {
      // Vérifier avec Supabase si la session est toujours valide
      supabaseClient.auth.setSession({
        access_token: savedSession.access_token,
        refresh_token: savedSession.refresh_token,
      }).then(({ data, error }) => {
        if (error || !data.session) {
          console.warn("⚠️ Saved session invalid, clearing:", error);
          clearAuthSession();
          setSession(null);
        } else {
          console.log("✅ Session restored from storage:", data.session.user?.id);
          setSession(data.session);
        }
        setLoading(false);
      });
    } else {
      // Vérifier la session Supabase actuelle
      supabaseClient.auth.getSession().then(({ data, error }) => {
        if (error) {
          console.warn("⚠️ Error getting session:", error);
          setSession(null);
        } else if (data.session) {
          console.log("✅ Session found:", data.session.user?.id);
          if (!data.session.access_token) {
            console.warn("⚠️ Session exists but no access_token!");
          }
          setSession(data.session);
        } else {
          console.log("ℹ️ No session found");
          setSession(null);
        }
        setLoading(false);
      });
    }

    // Écouter les changements de session
    const {
      data: { subscription },
    } = supabaseClient.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) {
        saveAuthSession(session, true);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLoginSuccess = (session) => {
    setSession(session);
  };

  const handleLogout = async () => {
    await supabaseClient.auth.signOut();
    clearAuthSession();
    setSession(null);
  };

  // Vérifier si on est sur la page de register
  const isRegisterPage = window.location.pathname === '/register' || 
                         window.location.search.includes('type=invite');

  if (loading && !isRegisterPage) {
    return (
      <div style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0b141a',
        color: '#e9edef'
      }}>
        <div>Chargement...</div>
      </div>
    );
  }

  if (isRegisterPage) {
    return <RegisterPage />;
  }

  if (!session) {
    return <MobileLoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  return <MobileInboxPage onLogout={handleLogout} />;
}

// Composant desktop (avec AuthProvider)
function DesktopApp() {
  const { session, loading } = useAuth();
  useTheme(); // Initialiser le thème au chargement de l'application

  // Vérifier si on est sur la page de register
  const isRegisterPage = window.location.pathname === '/register' || 
                         window.location.search.includes('type=invite');

  if (loading && !isRegisterPage) {
    return <div className="loading-screen">Chargement...</div>;
  }

  if (isRegisterPage) {
    return <RegisterPage />;
  }

  if (!session) {
    return <LoginPage />;
  }

  return (
    <div className="app">
      <AppHeader />
      <InboxPage />
    </div>
  );
}

// App principale avec détection de device
export default function App() {
  const [deviceType, setDeviceType] = useState(null);

  useEffect(() => {
    // Détection initiale + re-détection au resize
    const detect = () => setDeviceType(getDeviceType());

    detect();
    window.addEventListener("resize", detect);
    return () => window.removeEventListener("resize", detect);
  }, []);

  if (!deviceType) {
    return <div className="loading-screen">Chargement...</div>;
  }

  if (deviceType === "mobile") {
    return (
      <AuthProvider>
        <MobileApp />
      </AuthProvider>
    );
  }

  // Desktop + tablettes large : on sert l'UI desktop
  return (
    <AuthProvider>
      <DesktopApp />
    </AuthProvider>
  );
}