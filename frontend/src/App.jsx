import InboxPage from "./pages/InboxPage";
import AppHeader from "./components/layout/AppHeader";
import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";

function AppShell() {
  const { session, loading } = useAuth();

  if (loading) {
    return <div className="loading-screen">Chargement...</div>;
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

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}