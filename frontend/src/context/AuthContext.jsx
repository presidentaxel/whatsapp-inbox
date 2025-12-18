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
        setSession(null);
      } else if (data.session) {
        if (!data.session.access_token) {
          // Session sans access_token
        }
        setSession(data.session);
      } else {
        setSession(null);
      }
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
    
    // Vérifier que le token existe avant d'appeler l'API
    if (!session.access_token) {
      setProfile(null);
      return;
    }
    
    api
      .get("/auth/me")
      .then((res) => setProfile(res.data))
      .catch(() => {
        setProfile(null);
      });
  }, [session]);

  const hasPermission = useCallback(
    (permissionCode, accountId = null) => {
      if (!profile) return false;
      
      // Vérifier si le compte est en "aucun" (pas d'accès du tout)
      const accountAccessLevels = profile.permissions?.account_access_levels || {};
      if (accountId && accountAccessLevels[accountId] === "aucun") {
        // Exception : permissions de gestion des permissions ne sont pas bloquées par "aucun"
        // pour permettre aux admins de gérer les permissions même s'ils ont mis "aucun" pour eux-mêmes
        const adminPermissions = ["permissions.view", "permissions.manage"];
        if (!adminPermissions.includes(permissionCode)) {
          return false;
        }
      }
      
      const global = profile.permissions?.global ?? [];
      if (global.includes(permissionCode)) {
        // Si permission globale, vérifier que le compte n'est pas en "aucun"
        if (accountId && accountAccessLevels[accountId] === "aucun") {
          const adminPermissions = ["permissions.view", "permissions.manage"];
          if (!adminPermissions.includes(permissionCode)) {
            return false;
          }
        }
        return true;
      }
      
      if (accountId && profile.permissions?.accounts?.[accountId]) {
        // Si permission spécifique au compte, vérifier aussi que le compte n'est pas en "aucun"
        if (accountAccessLevels[accountId] === "aucun") {
          const adminPermissions = ["permissions.view", "permissions.manage"];
          if (!adminPermissions.includes(permissionCode)) {
            return false;
          }
        }
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

