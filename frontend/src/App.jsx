import { useState, useEffect, lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { supabaseClient } from "./api/supabaseClient";
import { getDeviceType } from "./utils/deviceDetection";
import { getAuthSession, saveAuthSession, clearAuthSession } from "./utils/secureStorage";
import { useTheme } from "./hooks/useTheme";
import { AuthProvider, useAuth } from "./context/AuthContext";

// Lazy-loaded pages: desktop and mobile bundles are split
const InboxPage = lazy(() => import("./pages/InboxPage"));
const AppHeader = lazy(() => import("./components/layout/AppHeader"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const MobileLoginPage = lazy(() => import("./pages/MobileLoginPage"));
const MobileInboxPage = lazy(() => import("./pages/MobileInboxPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const HttpErrorPage = lazy(() => import("./pages/HttpErrorPage"));

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
      supabaseClient.auth
        .setSession({
          access_token: savedSession.access_token,
          refresh_token: savedSession.refresh_token,
        })
        .then(({ data, error }) => {
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
      supabaseClient.auth.getSession().then(({ data, error }) => {
        if (error) {
          setSession(null);
        } else if (data.session) {
          setSession(data.session);
        } else {
          setSession(null);
        }
        setLoading(false);
      });
    }

    // Écouter les changements de session
    const {
      data: { subscription },
    } = supabaseClient.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      if (nextSession) {
        saveAuthSession(nextSession, true);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const handleLoginSuccess = (nextSession) => {
    setSession(nextSession);
  };

  const handleLogout = async () => {
    await supabaseClient.auth.signOut();
    clearAuthSession();
    setSession(null);
  };

  // Vérifier si on est sur la page de register
  const isRegisterPage =
    window.location.pathname === "/register" || window.location.search.includes("type=invite");

  if (loading && !isRegisterPage) {
    return (
      <div
        style={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0b141a",
          color: "#e9edef",
        }}
      >
        <div>Chargement...</div>
      </div>
    );
  }

  const fallback = (
    <div
      style={{
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0b141a",
        color: "#e9edef",
      }}
    >
      <div>Chargement...</div>
    </div>
  );

  if (isRegisterPage) {
    return (
      <Suspense fallback={fallback}>
        <RegisterPage />
      </Suspense>
    );
  }

  if (!session) {
    return (
      <Suspense fallback={fallback}>
        <MobileLoginPage onLoginSuccess={handleLoginSuccess} />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={fallback}>
      <AuthProvider>
        <MobileInboxPage onLogout={handleLogout} />
      </AuthProvider>
    </Suspense>
  );
}

// Composant desktop (avec AuthProvider)
function DesktopApp() {
  const { session, loading } = useAuth();
  useTheme(); // Initialiser le thème au chargement de l'application

  // Vérifier si on est sur la page de register
  const isRegisterPage =
    window.location.pathname === "/register" || window.location.search.includes("type=invite");

  if (loading && !isRegisterPage) {
    return <div className="loading-screen">Chargement...</div>;
  }

  const fallback = <div className="loading-screen">Chargement...</div>;

  if (isRegisterPage) {
    return (
      <Suspense fallback={fallback}>
        <RegisterPage />
      </Suspense>
    );
  }

  if (!session) {
    return (
      <Suspense fallback={fallback}>
        <LoginPage />
      </Suspense>
    );
  }

  return (
    <Suspense fallback={fallback}>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <div className="app">
          <AppHeader />
          <Routes>
            <Route path="/" element={<Navigate to="/discussions" replace />} />
            <Route path="/404" element={<HttpErrorPage code={404} />} />
            <Route path="/500" element={<HttpErrorPage code={500} />} />
            <Route path="/502" element={<HttpErrorPage code={502} />} />
            <Route path="/503" element={<HttpErrorPage code={503} />} />
            <Route path="/:inboxSection" element={<InboxPage />} />
            <Route path="*" element={<HttpErrorPage code={404} />} />
          </Routes>
        </div>
      </BrowserRouter>
    </Suspense>
  );
}

// App principale avec détection de device
export default function App() {
  const [deviceType, setDeviceType] = useState(() =>
    typeof window !== "undefined" ? getDeviceType() : null
  );

  useEffect(() => {
    const detect = () => setDeviceType(getDeviceType());

    detect();
    window.addEventListener("resize", detect);
    window.addEventListener("orientationchange", detect);

    const vv = window.visualViewport;
    if (vv) {
      vv.addEventListener("resize", detect);
    }

    const mqPointer = window.matchMedia("(pointer: coarse)");
    const mqHover = window.matchMedia("(hover: none)");
    const onMq = () => detect();
    mqPointer.addEventListener("change", onMq);
    mqHover.addEventListener("change", onMq);

    return () => {
      window.removeEventListener("resize", detect);
      window.removeEventListener("orientationchange", detect);
      if (vv) {
        vv.removeEventListener("resize", detect);
      }
      mqPointer.removeEventListener("change", onMq);
      mqHover.removeEventListener("change", onMq);
    };
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
