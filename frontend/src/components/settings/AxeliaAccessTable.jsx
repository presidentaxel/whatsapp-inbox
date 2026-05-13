import { useState, useEffect, useCallback, useMemo } from "react";
import { FiCpu, FiZap } from "react-icons/fi";
import {
  getUsersWithAccess,
  updateUserAxeliaAccess,
  updateUserAgentStudioAccess,
  updateUserPlaygroundAccess,
} from "../../api/adminApi";
import { platformAlert } from "../../platform/platformDialogs";

export default function AxeliaAccessTable({
  currentUserRole,
  canManagePermissions,
  currentUserId,
  refreshProfile,
}) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const normalizedRole = currentUserRole?.toLowerCase() || "";
  const canEdit = canManagePermissions || normalizedRole === "admin";
  const canView = normalizedRole === "admin" || normalizedRole === "dev";

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getUsersWithAccess();
      setUsers(res.data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshUsersQuiet = useCallback(async () => {
    try {
      const res = await getUsersWithAccess();
      setUsers(res.data || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!canView) return;
    loadUsers();
  }, [canView, loadUsers]);

  const handleToggleAxelia = async (userId, nextAllowed) => {
    if (!canEdit) return;
    const prev = users;
    setUsers((us) =>
      us.map((u) =>
        u.user_id === userId ? { ...u, axelia_access_effective: nextAllowed } : u,
      ),
    );
    try {
      await updateUserAxeliaAccess(userId, nextAllowed);
      await refreshUsersQuiet();
      if (currentUserId && userId === currentUserId && refreshProfile) {
        await refreshProfile();
      }
    } catch (e) {
      console.error(e);
      setUsers(prev);
      await platformAlert("Erreur lors de la mise à jour de l'accès Axelia.");
    }
  };

  const handleTogglePlayground = async (userId, nextAllowed) => {
    if (!canEdit) return;
    const prev = users;
    setUsers((us) =>
      us.map((u) =>
        u.user_id === userId ? { ...u, playground_access_effective: nextAllowed } : u,
      ),
    );
    try {
      await updateUserPlaygroundAccess(userId, nextAllowed);
      await refreshUsersQuiet();
      if (currentUserId && userId === currentUserId && refreshProfile) {
        await refreshProfile();
      }
    } catch (e) {
      console.error(e);
      setUsers(prev);
      await platformAlert("Erreur lors de la mise à jour de l'accès Playground.");
    }
  };

  const handleToggleAgentStudio = async (userId, nextAllowed) => {
    if (!canEdit) return;
    const prev = users;
    setUsers((us) =>
      us.map((u) =>
        u.user_id === userId ? { ...u, agent_studio_access_effective: nextAllowed } : u,
      ),
    );
    try {
      await updateUserAgentStudioAccess(userId, nextAllowed);
      await refreshUsersQuiet();
      if (currentUserId && userId === currentUserId && refreshProfile) {
        await refreshProfile();
      }
    } catch (e) {
      console.error(e);
      setUsers(prev);
      await platformAlert("Erreur lors de la mise à jour de l'accès Agent Studio.");
    }
  };

  const visibleUsers = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return users;
    return users.filter((user) => {
      const email = (user.email || "").toLowerCase();
      const role = (user.role_name || user.role_slug || "").toLowerCase();
      return email.includes(q) || role.includes(q);
    });
  }, [users, searchQuery]);

  if (!canView) {
    return (
      <div className="permissions-table-container">
        <p className="muted">Vous n'avez pas la permission de voir ces réglages.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="permissions-table-container">
        <p>Chargement...</p>
      </div>
    );
  }

  return (
    <div className="permissions-table-container">
      <div className="permissions-table-header">
        <p className="permissions-table-description">
          Contrôle qui voit les entrées <strong>Axelia</strong>, <strong>Playground</strong> et
          <strong> Agent Studio</strong> dans l&apos;application (
          <code>/axelia</code>, <code>/playground</code>, <code>/agent-studio</code>). Sans
          autorisation explicite, l&apos;entrée du menu n&apos;apparaît pas.
        </p>
        <p className="permissions-table-hint">
          Par défaut, les rôles concernés ont ces accès via les permissions de rôle ; les autres
          comptes peuvent être autorisés individuellement ici.
        </p>
      </div>

      <div className="permissions-users-toolbar">
        <input
          type="search"
          className="permissions-users-search"
          placeholder="Rechercher un utilisateur…"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <div className="permissions-users-list">
        {visibleUsers.map((user) => {
          const effectiveAx = Boolean(user.axelia_access_effective);
          const fromRoleAx = Boolean(user.axelia_access_role_default);
          const effectivePg = Boolean(user.playground_access_effective);
          const fromRolePg = Boolean(user.playground_access_role_default);
          const effectiveStudio = Boolean(user.agent_studio_access_effective);
          const fromRoleStudio = Boolean(user.agent_studio_access_role_default);

          return (
            <article key={user.user_id} className="permissions-user-card">
              <div className="permissions-user-card__header" style={{ cursor: "default" }}>
                <div className="permissions-user-card__identity">
                  <strong>{user.email || "Utilisateur"}</strong>
                  <small>{user.role_name || "-"}</small>
                </div>
              </div>

              <div className="permissions-user-card__accounts">
                <div className="permissions-user-card__account-row">
                  <div className="permissions-user-card__account-info">
                    <strong style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <FiZap aria-hidden /> Accès Axelia
                    </strong>
                    {fromRoleAx && effectiveAx ? (
                      <small>Inclus par défaut depuis le rôle</small>
                    ) : (
                      <small>Accès individuel</small>
                    )}
                  </div>
                  {canEdit ? (
                    <label style={{ cursor: "pointer", userSelect: "none" }}>
                      <input
                        type="checkbox"
                        checked={effectiveAx}
                        onChange={(e) => handleToggleAxelia(user.user_id, e.target.checked)}
                        style={{ marginRight: 8 }}
                      />
                      {effectiveAx ? "Autorisé" : "Non autorisé"}
                    </label>
                  ) : (
                    <div className="permissions-table-access-badge" style={{ backgroundColor: "#1e293b", color: "#fff" }}>
                      {effectiveAx ? "Oui" : "Non"}
                    </div>
                  )}
                </div>

                <div className="permissions-user-card__account-row">
                  <div className="permissions-user-card__account-info">
                    <strong style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <FiCpu aria-hidden /> Accès Playground
                    </strong>
                    {fromRolePg && effectivePg ? (
                      <small>Inclus par défaut depuis le rôle</small>
                    ) : (
                      <small>Accès individuel</small>
                    )}
                  </div>
                  {canEdit ? (
                    <label style={{ cursor: "pointer", userSelect: "none" }}>
                      <input
                        type="checkbox"
                        checked={effectivePg}
                        onChange={(e) => handleTogglePlayground(user.user_id, e.target.checked)}
                        style={{ marginRight: 8 }}
                      />
                      {effectivePg ? "Autorisé" : "Non autorisé"}
                    </label>
                  ) : (
                    <div className="permissions-table-access-badge" style={{ backgroundColor: "#1e293b", color: "#fff" }}>
                      {effectivePg ? "Oui" : "Non"}
                    </div>
                  )}
                </div>

                <div className="permissions-user-card__account-row">
                  <div className="permissions-user-card__account-info">
                    <strong style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                      <FiCpu aria-hidden /> Accès Agent Studio
                    </strong>
                    {fromRoleStudio && effectiveStudio ? (
                      <small>Inclus par défaut depuis le rôle</small>
                    ) : (
                      <small>Accès individuel</small>
                    )}
                  </div>
                  {canEdit ? (
                    <label style={{ cursor: "pointer", userSelect: "none" }}>
                      <input
                        type="checkbox"
                        checked={effectiveStudio}
                        onChange={(e) => handleToggleAgentStudio(user.user_id, e.target.checked)}
                        style={{ marginRight: 8 }}
                      />
                      {effectiveStudio ? "Autorisé" : "Non autorisé"}
                    </label>
                  ) : (
                    <div className="permissions-table-access-badge" style={{ backgroundColor: "#1e293b", color: "#fff" }}>
                      {effectiveStudio ? "Oui" : "Non"}
                    </div>
                  )}
                </div>
              </div>
            </article>
          );
        })}

        {!visibleUsers.length && <p className="permissions-table-empty">Aucun utilisateur trouvé.</p>}
      </div>
    </div>
  );
}
