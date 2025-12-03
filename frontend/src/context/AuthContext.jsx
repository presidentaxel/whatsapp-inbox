import { createContext, useContext, useEffect, useMemo, useState, useCallback } from "react";
import { supabaseClient } from "../api/supabaseClient";
import { api } from "../api/axiosClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const {
      data: { subscription },
    } = supabaseClient.auth.onAuthStateChange((_event, sess) => {
      setSession(sess);
    });
    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) {
      setProfile(null);
      return;
    }
    api
      .get("/auth/me")
      .then((res) => setProfile(res.data))
      .catch(() => setProfile(null));
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

