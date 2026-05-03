import { useState, useEffect, useCallback } from "react";
import { FiCpu, FiZap } from "react-icons/fi";
import {
  getUsersWithAccess,
  updateUserAxeliaAccess,
  updateUserPlaygroundAccess,
} from "../../api/adminApi";

export default function AxeliaAccessTable({
  currentUserRole,
  canManagePermissions,
  currentUserId,
  refreshProfile,
}) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);

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
      alert("Erreur lors de la mise à jour de l'accès Axelia.");
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
      alert("Erreur lors de la mise à jour de l'accès Playground.");
    }
  };

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
          Contrôle qui voit les entrées <strong>Axelia</strong> et <strong>Playground</strong> dans
          l&apos;application (<code>/axelia</code>, <code>/playground</code>). Sans autorisation
          explicite, l&apos;entrée du menu n&apos;apparaît pas.
        </p>
        <p className="permissions-table-hint">
          Par défaut, les rôles concernés ont ces accès via les permissions de rôle ; les autres
          comptes peuvent être autorisés individuellement ici.
        </p>
      </div>

      <div className="permissions-table-wrapper">
        <table className="permissions-table">
          <thead>
            <tr>
              <th className="permissions-table-user-col">Utilisateur</th>
              <th className="permissions-table-role-col">Rôle</th>
              <th style={{ minWidth: 160 }} className="permissions-table-account-col">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FiZap aria-hidden /> Accès Axelia
                </span>
              </th>
              <th style={{ minWidth: 160 }} className="permissions-table-account-col">
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <FiCpu aria-hidden /> Accès Playground
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => {
              const effectiveAx = Boolean(user.axelia_access_effective);
              const fromRoleAx = Boolean(user.axelia_access_role_default);
              const effectivePg = Boolean(user.playground_access_effective);
              const fromRolePg = Boolean(user.playground_access_role_default);

              return (
                <tr key={user.user_id}>
                  <td className="permissions-table-user-cell">
                    <strong>{user.email || "Utilisateur"}</strong>
                  </td>
                  <td className="permissions-table-role-cell">{user.role_name || "-"}</td>
                  <td className="permissions-table-access-cell">
                    {canEdit ? (
                      <label style={{ cursor: "pointer", userSelect: "none" }}>
                        <input
                          type="checkbox"
                          checked={effectiveAx}
                          onChange={(e) =>
                            handleToggleAxelia(user.user_id, e.target.checked)
                          }
                          style={{ marginRight: 8 }}
                        />
                        {effectiveAx ? "Autorisé" : "Non autorisé"}
                        {fromRoleAx && effectiveAx ? (
                          <small className="muted" style={{ display: "block", marginTop: 4 }}>
                            Inclus par défaut depuis le rôle
                          </small>
                        ) : null}
                      </label>
                    ) : (
                      <div
                        className="permissions-table-access-badge"
                        style={{ backgroundColor: "#1e293b", color: "#fff" }}
                      >
                        {effectiveAx ? "Oui" : "Non"}
                      </div>
                    )}
                  </td>
                  <td className="permissions-table-access-cell">
                    {canEdit ? (
                      <label style={{ cursor: "pointer", userSelect: "none" }}>
                        <input
                          type="checkbox"
                          checked={effectivePg}
                          onChange={(e) =>
                            handleTogglePlayground(user.user_id, e.target.checked)
                          }
                          style={{ marginRight: 8 }}
                        />
                        {effectivePg ? "Autorisé" : "Non autorisé"}
                        {fromRolePg && effectivePg ? (
                          <small className="muted" style={{ display: "block", marginTop: 4 }}>
                            Inclus par défaut depuis le rôle
                          </small>
                        ) : null}
                      </label>
                    ) : (
                      <div
                        className="permissions-table-access-badge"
                        style={{ backgroundColor: "#1e293b", color: "#fff" }}
                      >
                        {effectivePg ? "Oui" : "Non"}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!users.length && <p className="permissions-table-empty">Aucun utilisateur trouvé.</p>}
      </div>
    </div>
  );
}
