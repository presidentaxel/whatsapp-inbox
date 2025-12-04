import { createContext, useContext, useEffect, useMemo, useState, useCallback } from "react";
import { supabaseClient } from "../api/supabaseClient";
import { api } from "../api/axiosClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data, error }) => {
      if (error) {
        console.warn("⚠️ Error getting session in AuthContext:", error);
        setSession(null);
      } else if (data.session) {
        console.log("✅ Session found in AuthContext:", data.session.user?.id);
        if (!data.session.access_token) {
          console.warn("⚠️ Session exists but no access_token in AuthContext!");
        }
        setSession(data.session);
      } else {
        console.log("ℹ️ No session found in AuthContext");
        setSession(null);
      }
      setLoading(false);
    });
    const {
      data: { subscription },
    } = supabaseClient.auth.onAuthStateChange((_event, sess) => {
      console.log("🔄 Auth state changed:", _event, sess?.user?.id);
      setSession(sess);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) {
      setProfile(null);
      return;
    }
    
    // Vérifier que le token existe avant d'appeler l'API
    if (!session.access_token) {
      console.warn("⚠️ Session exists but no access_token in AuthContext");
      setProfile(null);
      return;
    }
    
    api
      .get("/auth/me")
      .then((res) => setProfile(res.data))
      .catch((error) => {
        console.error("❌ Error fetching profile in AuthContext:", error);
        if (error.response?.status === 401) {
          console.warn("⚠️ 401 Unauthorized - Session may have expired, clearing profile");
        }
        setProfile(null);
      });
  }, [session]);

  const hasPermission = useCallback(
    (permissionCode, accountId = null) => {
      if (!profile) return false;
      const global = profile.permissions?.global ?? [];
      if (global.includes(permissionCode)) {
        return true;
      }
      if (accountId && profile.permissions?.accounts?.[accountId]) {
        return profile.permissions.accounts[accountId].includes(permissionCode);
      }
      return false;
    },
    [profile]
  );

  const refreshProfile = useCallback(() => {
    if (!session) {
      setProfile(null);
      return Promise.resolve(null);
    }
    return api
      .get("/auth/me")
      .then((res) => {
        setProfile(res.data);
        return res.data;
      })
      .catch(() => {
        setProfile(null);
        return null;
      });
  }, [session]);

  const value = useMemo(
    () => ({
      session,
      loading,
      profile,
      hasPermission,
      refreshProfile,
      signIn: (email, password) =>
        supabaseClient.auth.signInWithPassword({ email, password }),
      signOut: () => supabaseClient.auth.signOut(),
    }),
    [session, loading, profile, hasPermission, refreshProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

