import { useState, useEffect, useMemo } from "react";
import { 
  getUsersWithAccess, 
  updateUserAccountAccess, 
  getRoles, 
  setUserRoles,
  getAllAccountsForPermissions 
} from "../../api/adminApi";

const ACCESS_LEVELS = [
  { value: "full", label: "Full", description: "Tous les droits (écrire, lire, ...)" },
  { value: "lecture", label: "Lecture", description: "Peut voir mais pas écrire" },
  { value: "aucun", label: "Aucun", description: "Ne sait même pas que le compte existe" },
];

export default function PermissionsTable({
  accounts: _propsAccounts,
  currentUserRole,
  canManagePermissions,
  currentUserId,
  refreshProfile,
}) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [accounts, setAccounts] = useState([]); // Comptes chargés pour la table des permissions (tous les comptes)
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedUsers, setExpandedUsers] = useState({});

  // Normaliser le rôle en minuscules pour la comparaison
  const normalizedRole = currentUserRole?.toLowerCase() || "";
  
  // Si canManagePermissions est true, l'utilisateur peut modifier (c'est la permission qui compte)
  // Si canManagePermissions est false mais que le rôle est admin, on permet quand même l'édition
  // (par sécurité, au cas où la permission n'est pas correctement chargée)
  const canEdit = canManagePermissions || normalizedRole === "admin";
  // Admin et DEV peuvent voir, Manager ne peut rien voir
  const canView = normalizedRole === "admin" || normalizedRole === "dev";

  useEffect(() => {
    if (!canView) return;
    loadAllData();
     
  }, [canView]); // Recharger quand la vue change

  const loadAllData = async () => {
    setLoading(true);
    try {
      // Charger tous les comptes (sans filtre par accès) pour la table des permissions
      // Cela permet à l'admin de voir et gérer les comptes même s'il les a mis en "aucun"
      const accountsRes = await getAllAccountsForPermissions();
      setAccounts(accountsRes.data || []);
      
      // Charger les utilisateurs et leurs accès
      const usersRes = await getUsersWithAccess();
      const loadedUsers = usersRes.data || [];
      setUsers(loadedUsers);
      setExpandedUsers((prev) => {
        if (Object.keys(prev).length) return prev;
        const firstUserId = loadedUsers[0]?.user_id;
        return firstUserId ? { [firstUserId]: true } : {};
      });
    } catch (error) {
      console.error("Erreur lors du chargement des données:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadUsers = async () => {
    try {
      const res = await getUsersWithAccess();
      setUsers(res.data || []);
    } catch (error) {
      console.error("Erreur lors du chargement des utilisateurs:", error);
    }
  };

  const loadRoles = async () => {
    try {
      const res = await getRoles();
      // Filtrer pour ne garder que les 3 rôles fixes : admin, dev, manager
      const fixedRoles = (res.data || []).filter(
        (role) => role.slug === "admin" || role.slug === "dev" || role.slug === "manager"
      );
      setRoles(fixedRoles);
    } catch (error) {
      console.error("Erreur lors du chargement des rôles:", error);
    }
  };

  // Charger les rôles au montage
  useEffect(() => {
    if (canView) {
      loadRoles();
    }
  }, [canView]);

  const getAccessLevel = (userId, accountId) => {
    const user = users.find((u) => u.user_id === userId);
    if (!user) return "aucun";
    const access = user.account_access?.find((a) => a.account_id === accountId);
    return access?.access_level || "aucun";
  };

  const handleAccessChange = async (userId, accountId, newLevel) => {
    if (!canEdit) return;
    
    const currentLevel = getAccessLevel(userId, accountId);
    if (newLevel === currentLevel) return; // Pas de changement, pas besoin de sauvegarder

    const key = `access:${userId}:${accountId}`;
    setSavingKey(key);
    try {
      await updateUserAccountAccess(userId, accountId, newLevel);
      await loadUsers(); // Recharger seulement les utilisateurs (les comptes ne changent pas)
      
      // Si c'est l'utilisateur actuel, rafraîchir son profil pour mettre à jour les permissions immédiatement
      if (currentUserId && userId === currentUserId && refreshProfile) {
        await refreshProfile();
      }
    } catch (error) {
      console.error("Erreur lors de la sauvegarde:", error);
      alert("Erreur lors de la sauvegarde de l'accès");
      // Optionnel : recharger pour restaurer l'état précédent
      await loadUsers();
    } finally {
      setSavingKey(null);
    }
  };

  const handleRoleChange = async (userId, newRoleSlug) => {
    if (!canEdit) return;
    
    const user = users.find((u) => u.user_id === userId);
    if (!user) return;
    
    const currentRoleSlug = user.role_slug;
    if (newRoleSlug === currentRoleSlug) return; // Pas de changement

    const newRole = roles.find((r) => r.slug === newRoleSlug);
    if (!newRole) {
      alert("Rôle introuvable");
      return;
    }

    const key = `role:${userId}`;
    setSavingKey(key);
    try {
      // Assigner le nouveau rôle (sans account_id pour qu'il soit global)
      await setUserRoles(userId, [{ role_id: newRole.id, account_id: null }]);
      await loadUsers(); // Recharger seulement les utilisateurs
      
      // Si c'est l'utilisateur actuel, rafraîchir son profil pour mettre à jour les permissions immédiatement
      if (currentUserId && userId === currentUserId && refreshProfile) {
        await refreshProfile();
      }
    } catch (error) {
      console.error("Erreur lors de la sauvegarde du rôle:", error);
      alert("Erreur lors de la sauvegarde du rôle");
      await loadUsers();
    } finally {
      setSavingKey(null);
    }
  };

  const getRoleColor = (roleSlug) => {
    switch (roleSlug) {
      case "admin":
        return "#dc2626"; // Rouge
      case "dev":
        return "#2563eb"; // Bleu
      case "manager":
        return "#16a34a"; // Vert
      default:
        return "#6b7280"; // Gris
    }
  };

  const getAccessLabel = (level) => {
    const found = ACCESS_LEVELS.find((a) => a.value === level);
    return found?.label || level;
  };

  const getAccessColor = (level) => {
    switch (level) {
      case "full":
        return "#25d366"; // Vert WhatsApp
      case "lecture":
        return "#ffa500"; // Orange
      case "aucun":
        return "#8696a0"; // Gris
      default:
        return "#8696a0";
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

  const toggleUserExpanded = (userId) => {
    setExpandedUsers((prev) => ({ ...prev, [userId]: !prev[userId] }));
  };

  if (!canView) {
    return (
      <div className="permissions-table-container">
        <p className="muted">Vous n'avez pas la permission de voir les accès.</p>
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
          Gérer les accès des utilisateurs par compte WhatsApp.
        </p>
        {canEdit && (
          <p className="permissions-table-hint">
            Modifications sauvegardées automatiquement.
          </p>
        )}
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
          const isExpanded = Boolean(expandedUsers[user.user_id]);
          return (
            <article key={user.user_id} className="permissions-user-card">
              <button
                type="button"
                className="permissions-user-card__header"
                onClick={() => toggleUserExpanded(user.user_id)}
              >
                <div className="permissions-user-card__identity">
                  <strong>{user.email || "Utilisateur"}</strong>
                  <small>{isExpanded ? "Masquer les comptes" : "Afficher les comptes"}</small>
                </div>
                <span className="permissions-user-card__chevron" aria-hidden="true">
                  {isExpanded ? "−" : "+"}
                </span>
              </button>

              <div className="permissions-user-card__role">
                <span>Rôle global</span>
                {canEdit ? (
                  <select
                    value={user.role_slug || ""}
                    onChange={(e) => handleRoleChange(user.user_id, e.target.value)}
                    className="permissions-table-select"
                    disabled={savingKey === `role:${user.user_id}`}
                    style={{
                      backgroundColor: getRoleColor(user.role_slug),
                      color: "#fff",
                      border: "none",
                      cursor: "pointer",
                    }}
                  >
                    {roles.map((role) => (
                      <option key={role.id} value={role.slug}>
                        {role.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div
                    className="permissions-table-access-badge"
                    style={{ backgroundColor: getRoleColor(user.role_slug), color: "#fff" }}
                  >
                    {user.role_name || "Aucun rôle"}
                  </div>
                )}
              </div>

              {isExpanded && (
                <div className="permissions-user-card__accounts">
                  {accounts.map((account) => {
                    const currentLevel = getAccessLevel(user.user_id, account.id);
                    const key = `access:${user.user_id}:${account.id}`;
                    return (
                      <div key={account.id} className="permissions-user-card__account-row">
                        <div className="permissions-user-card__account-info">
                          <strong>{account.name}</strong>
                          <small>{account.phone_number || "Pas de numéro"}</small>
                        </div>
                        {canEdit ? (
                          <select
                            value={currentLevel}
                            onChange={(e) => handleAccessChange(user.user_id, account.id, e.target.value)}
                            className="permissions-table-select"
                            disabled={savingKey === key}
                            style={{
                              backgroundColor: getAccessColor(currentLevel),
                              color: "#fff",
                              border: "none",
                              cursor: "pointer",
                            }}
                          >
                            {ACCESS_LEVELS.map((level) => (
                              <option key={level.value} value={level.value}>
                                {level.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <div
                            className="permissions-table-access-badge"
                            style={{ backgroundColor: getAccessColor(currentLevel), color: "#fff" }}
                          >
                            {getAccessLabel(currentLevel)}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </article>
          );
        })}

        {!visibleUsers.length && (
          <p className="permissions-table-empty">Aucun utilisateur trouvé.</p>
        )}
      </div>

      <div className="permissions-table-legend">
        <h4>Légende des accès :</h4>
        <div className="permissions-table-legend-items">
          {ACCESS_LEVELS.map((level) => (
            <div key={level.value} className="permissions-table-legend-item">
              <span
                className="permissions-table-legend-badge"
                style={{ backgroundColor: getAccessColor(level.value) }}
              >
                {level.label}
              </span>
              <span className="permissions-table-legend-desc">{level.description}</span>
            </div>
          ))}
        </div>
        <h4 style={{ marginTop: "24px", marginBottom: "12px" }}>Légende des rôles :</h4>
        <div className="permissions-table-legend-items">
          <div className="permissions-table-legend-item">
            <span
              className="permissions-table-legend-badge"
              style={{ backgroundColor: getRoleColor("admin") }}
            >
              Admin
            </span>
            <span className="permissions-table-legend-desc">
              Peut changer les permissions et accès
            </span>
          </div>
          <div className="permissions-table-legend-item">
            <span
              className="permissions-table-legend-badge"
              style={{ backgroundColor: getRoleColor("dev") }}
            >
              DEV
            </span>
            <span className="permissions-table-legend-desc">
              Peut voir les permissions mais ne pas les changer
            </span>
          </div>
          <div className="permissions-table-legend-item">
            <span
              className="permissions-table-legend-badge"
              style={{ backgroundColor: getRoleColor("manager") }}
            >
              Manager
            </span>
            <span className="permissions-table-legend-desc">
              Ne peut rien voir des autorisations
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

