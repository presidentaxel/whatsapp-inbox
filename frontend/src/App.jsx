import { useState, useEffect } from "react";
import { supabaseClient } from "./api/supabaseClient";
import { isMobileDevice } from "./utils/deviceDetection";
import { getAuthSession, saveAuthSession, clearAuthSession } from "./utils/secureStorage";

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
          clearAuthSession();
          setSession(null);
        } else {
          setSession(data.session);
        }
        setLoading(false);
      });
    } else {
      // Vérifier la session Supabase actuelle
      supabaseClient.auth.getSession().then(({ data }) => {
        setSession(data.session);
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
    setDeviceType(isMobileDevice() ? 'mobile' : 'desktop');
    
    // Re-détecter au resize (utile pour le mode responsive)
    const handleResize = () => {
      setDeviceType(isMobileDevice() ? 'mobile' : 'desktop');
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (!deviceType) {
    return <div className="loading-screen">Chargement...</div>;
  }

  if (deviceType === 'mobile') {
    return <MobileApp />;
  }

  return (
    <AuthProvider>
      <DesktopApp />
    </AuthProvider>
  );
}