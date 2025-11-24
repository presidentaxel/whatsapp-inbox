import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createRole,
  deleteRole,
  getAdminUsers,
  getPermissions,
  getRoles,
  setUserOverrides,
  setUserRoles,
  updateUserStatus,
} from "../../api/adminApi";
import { createAccount, deleteAccount } from "../../api/accountsApi";

const INITIAL_ACCOUNT_FORM = {
  name: "",
  slug: "",
  phone_number: "",
  phone_number_id: "",
  access_token: "",
  verify_token: "",
};

const INITIAL_ROLE_FORM = {
  name: "",
  slug: "",
  description: "",
  permissions: [],
};

export default function SettingsPanel({
  accounts = [],
  onSignOut,
  currentUser,
  canManageAccounts,
  canManageRoles,
  canManageUsers,
  onAccountsRefresh,
}) {
  const [accountForm, setAccountForm] = useState(INITIAL_ACCOUNT_FORM);
  const [roleForm, setRoleForm] = useState(INITIAL_ROLE_FORM);
  const [permissions, setPermissions] = useState([]);
  const [roles, setRoles] = useState([]);
  const [users, setUsers] = useState([]);
  const [loadingAdmin, setLoadingAdmin] = useState(false);
  const [roleDrafts, setRoleDrafts] = useState({});
  const [overrideDrafts, setOverrideDrafts] = useState({});
  const [statusMessage, setStatusMessage] = useState("");
  const [activePanel, setActivePanel] = useState("general");

  const accountMap = useMemo(
    () => Object.fromEntries(accounts.map((acc) => [acc.id, acc])),
    [accounts]
  );

  const loadAdminData = useCallback(async () => {
    if (!canManageRoles && !canManageUsers) return;
    setLoadingAdmin(true);
    try {
      if (canManageRoles) {
        const [permRes, roleRes] = await Promise.all([getPermissions(), getRoles()]);
        setPermissions(permRes.data);
        setRoles(roleRes.data);
      }
      if (canManageUsers) {
        const userRes = await getAdminUsers();
        setUsers(userRes.data);
      }
    } catch (error) {
      console.error("Admin data error", error);
    } finally {
      setLoadingAdmin(false);
    }
  }, [canManageRoles, canManageUsers]);

  useEffect(() => {
    loadAdminData();
  }, [loadAdminData]);

  const handleAccountInput = (field, value) => {
    setAccountForm((prev) => ({
      ...prev,
      [field]: value,
      ...(field === "name" && !prev.slug
        ? { slug: value.toLowerCase().replace(/\s+/g, "-") }
        : {}),
    }));
  };

  const handleCreateAccount = async (e) => {
    e.preventDefault();
    try {
      await createAccount({
        ...accountForm,
        phone_number: accountForm.phone_number || null,
      });
      setAccountForm(INITIAL_ACCOUNT_FORM);
      setStatusMessage("Compte créé avec succès.");
      onAccountsRefresh?.();
    } catch (error) {
      console.error("create account error", error);
      setStatusMessage("Erreur lors de la création du compte.");
    }
  };

  const handleDeleteAccount = async (accountId) => {
    if (!window.confirm("Supprimer ce compte WhatsApp ?")) return;
    await deleteAccount(accountId);
    onAccountsRefresh?.();
  };

  const toggleRolePermission = (code) => {
    setRoleForm((prev) => {
      const exists = prev.permissions.includes(code);
      return {
        ...prev,
        permissions: exists
          ? prev.permissions.filter((perm) => perm !== code)
          : [...prev.permissions, code],
      };
    });
  };

  const handleCreateRole = async (e) => {
    e.preventDefault();
    await createRole(roleForm);
    setRoleForm(INITIAL_ROLE_FORM);
    loadAdminData();
  };

  const handleDeleteRole = async (roleId, slug) => {
    if (slug === "admin") return;
    if (!window.confirm("Supprimer ce rôle ?")) return;
    await deleteRole(roleId);
    loadAdminData();
  };

  const updateRolesForUser = async (user, assignments) => {
    await setUserRoles(
      user.user_id,
      assignments.map((item) => ({
        role_id: item.role_id,
        account_id: item.account_id ?? null,
      }))
    );
    loadAdminData();
  };

  const updateOverridesForUser = async (user, overrides) => {
    await setUserOverrides(
      user.user_id,
      overrides.map((item) => ({
        permission_code: item.permission_code,
        account_id: item.account_id ?? null,
        is_allowed: item.is_allowed,
      }))
    );
    loadAdminData();
  };

  const handleAddRoleToUser = async (user) => {
    const draft = roleDrafts[user.user_id] || { role_id: "", account_id: "" };
    if (!draft.role_id) return;
    const nextAssignments = [
      ...user.roles.map((role) => ({
        role_id: role.role_id,
        account_id: role.account_id ?? null,
      })),
      { role_id: draft.role_id, account_id: draft.account_id || null },
    ];
    await updateRolesForUser(user, nextAssignments);
    setRoleDrafts((prev) => ({ ...prev, [user.user_id]: { role_id: "", account_id: "" } }));
  };

  const handleRemoveRoleFromUser = async (user, index) => {
    const nextAssignments = user.roles
      .filter((_, idx) => idx !== index)
      .map((role) => ({ role_id: role.role_id, account_id: role.account_id ?? null }));
    await updateRolesForUser(user, nextAssignments);
  };

  const handleAddOverrideToUser = async (user) => {
    const draft = overrideDrafts[user.user_id] || {
      permission_code: "",
      account_id: "",
      is_allowed: true,
    };
    if (!draft.permission_code) return;
    const next = [
      ...user.overrides,
      {
        permission_code: draft.permission_code,
        account_id: draft.account_id || null,
        is_allowed: draft.is_allowed,
      },
    ];
    await updateOverridesForUser(user, next);
    setOverrideDrafts((prev) => ({
      ...prev,
      [user.user_id]: { permission_code: "", account_id: "", is_allowed: true },
    }));
  };

  const handleRemoveOverrideFromUser = async (user, index) => {
    const next = user.overrides.filter((_, idx) => idx !== index);
    await updateOverridesForUser(user, next);
  };

  const handleToggleUserStatus = async (user) => {
    await updateUserStatus(user.user_id, { is_active: !user.is_active });
    loadAdminData();
  };

  const panels = useMemo(
    () =>
      [
        { id: "general", label: "Général" },
        canManageAccounts && { id: "accounts", label: "Comptes" },
        canManageRoles && { id: "roles", label: "Rôles" },
        canManageUsers && { id: "users", label: "Utilisateurs" },
      ].filter(Boolean),
    [canManageAccounts, canManageRoles, canManageUsers]
  );

  return (
    <div className="settings-panel">
      <div className="settings-tabs">
        {panels.map((tab) => (
          <button
            key={tab.id}
            className={`settings-tab ${activePanel === tab.id ? "active" : ""}`}
            onClick={() => setActivePanel(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activePanel === "general" && (
        <>
          <section className="settings-card">
            <h2>Profil</h2>
            <p>{currentUser?.email || "Utilisateur connecté"}</p>
            <p className="muted">
              Rôles actifs :{" "}
              {currentUser?.roles?.length
                ? currentUser.roles
                    .map((r) => (r.role_name ? r.role_name : r.role_slug))
                    .join(", ")
                : "aucun"}
            </p>
            <button className="danger" onClick={onSignOut}>
              Déconnexion
            </button>
          </section>

          <section className="settings-card">
            <h2>Comptes disponibles</h2>
            {accounts.length ? (
              <div className="account-grid">
                {accounts.map((acc) => (
                  <article key={acc.id} className="account-card compact">
                    <header>
                      <strong>{acc.name}</strong>
                      <span>{acc.phone_number || "Numéro inconnu"}</span>
                    </header>
                    <div className="account-meta">
                      <span>ID : {acc.id}</span>
                      <span>Phone ID : {acc.phone_number_id}</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p>Aucun compte assigné à ce profil.</p>
            )}
          </section>
        </>
      )}

      {activePanel === "accounts" && canManageAccounts && (
        <section className="settings-card">
          <h2>Gestion des comptes</h2>
          <p className="muted">
            Ajoute tes numéros WhatsApp Cloud API et choisis les membres qui y auront accès.
          </p>
          {statusMessage && <p>{statusMessage}</p>}
          {accounts.length ? (
            <div className="account-grid">
              {accounts.map((acc) => (
                <article key={acc.id} className="account-card">
                  <header>
                    <strong>{acc.name}</strong>
                    <span>{acc.phone_number || "Numéro inconnu"}</span>
                  </header>
                  <div className="account-meta">
                    <span>ID : {acc.id}</span>
                    <span>Phone ID : {acc.phone_number_id}</span>
                  </div>
                  <button
                    className="danger subtle"
                    onClick={() => handleDeleteAccount(acc.id)}
                    type="button"
                  >
                    Supprimer
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p>Aucun compte pour le moment.</p>
          )}

          <form className="account-form" onSubmit={handleCreateAccount}>
            <h3>Ajouter un compte</h3>
            <div className="form-grid">
              <input
                placeholder="Nom"
                value={accountForm.name}
                onChange={(e) => handleAccountInput("name", e.target.value)}
                required
              />
              <input
                placeholder="Slug"
                value={accountForm.slug}
                onChange={(e) => handleAccountInput("slug", e.target.value)}
                required
              />
              <input
                placeholder="Numéro (optionnel)"
                value={accountForm.phone_number}
                onChange={(e) => handleAccountInput("phone_number", e.target.value)}
              />
              <input
                placeholder="Phone Number ID"
                value={accountForm.phone_number_id}
                onChange={(e) => handleAccountInput("phone_number_id", e.target.value)}
                required
              />
              <input
                placeholder="Access Token"
                value={accountForm.access_token}
                onChange={(e) => handleAccountInput("access_token", e.target.value)}
                required
              />
              <input
                placeholder="Verify Token"
                value={accountForm.verify_token}
                onChange={(e) => handleAccountInput("verify_token", e.target.value)}
                required
              />
            </div>
            <button type="submit">Créer</button>
          </form>
        </section>
      )}

      {activePanel === "roles" && canManageRoles && (
        <section className="settings-card">
          <h2>Rôles & permissions</h2>
          {loadingAdmin && <p>Chargement…</p>}
          {!loadingAdmin && (
            <>
              <div className="role-list">
                {roles.map((role) => (
                  <article key={role.id} className="role-card">
                    <header>
                      <div>
                        <strong>{role.name}</strong>
                        <span className="role-slug">{role.slug}</span>
                      </div>
                      {role.slug !== "admin" && (
                        <button
                          type="button"
                          className="danger subtle"
                          onClick={() => handleDeleteRole(role.id, role.slug)}
                        >
                          Supprimer
                        </button>
                      )}
                    </header>
                    <p>{role.description}</p>
                    <div className="chip-list">
                      {(role.permissions || []).map((perm) => (
                        <span key={perm} className="chip">
                          {perm}
                        </span>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
              <form className="role-form" onSubmit={handleCreateRole}>
                <h3>Nouveau rôle</h3>
                <input
                  placeholder="Nom"
                  value={roleForm.name}
                  onChange={(e) => setRoleForm((prev) => ({ ...prev, name: e.target.value }))}
                  required
                />
                <input
                  placeholder="Slug"
                  value={roleForm.slug}
                  onChange={(e) => setRoleForm((prev) => ({ ...prev, slug: e.target.value }))}
                  required
                />
                <textarea
                  placeholder="Description"
                  value={roleForm.description}
                  onChange={(e) =>
                    setRoleForm((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
                <div className="permission-grid">
                  {permissions.map((perm) => (
                    <label key={perm.code}>
                      <input
                        type="checkbox"
                        checked={roleForm.permissions.includes(perm.code)}
                        onChange={() => toggleRolePermission(perm.code)}
                      />
                      {perm.label || perm.code}
                    </label>
                  ))}
                </div>
                <button type="submit">Créer le rôle</button>
              </form>
            </>
          )}
        </section>
      )}

      {activePanel === "users" && canManageUsers && (
        <section className="settings-card">
          <h2>Utilisateurs</h2>
          {users.length === 0 && <p>Aucun utilisateur enregistré.</p>}
          {users.map((user) => {
            const roleDraft = roleDrafts[user.user_id] || { role_id: "", account_id: "" };
            const overrideDraft =
              overrideDrafts[user.user_id] || {
                permission_code: "",
                account_id: "",
                is_allowed: true,
              };
            return (
              <article key={user.user_id} className="user-card">
                <header>
                  <div>
                    <strong>{user.email || "Utilisateur"}</strong>
                    <span>{user.user_id}</span>
                  </div>
                  <button type="button" onClick={() => handleToggleUserStatus(user)}>
                    {user.is_active ? "Désactiver" : "Activer"}
                  </button>
                </header>

                <div className="user-section">
                  <h4>Rôles</h4>
                  <div className="chip-list">
                    {user.roles.map((role, idx) => (
                      <span key={role.id || `${role.role_id}-${idx}`} className="chip removable">
                        {role.role_name || role.role_slug}
                        {role.account_id && accountMap[role.account_id] && (
                          <small> • {accountMap[role.account_id].name}</small>
                        )}
                        <button onClick={() => handleRemoveRoleFromUser(user, idx)}>×</button>
                      </span>
                    ))}
                    {!user.roles.length && <span>Aucun rôle assigné.</span>}
                  </div>
                  <div className="inline-form">
                    <select
                      className="app-select"
                      value={roleDraft.role_id}
                      onChange={(e) =>
                        setRoleDrafts((prev) => ({
                          ...prev,
                          [user.user_id]: { ...roleDraft, role_id: e.target.value },
                        }))
                      }
                    >
                      <option value="">Choisir un rôle</option>
                      {roles.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className="app-select"
                      value={roleDraft.account_id}
                      onChange={(e) =>
                        setRoleDrafts((prev) => ({
                          ...prev,
                          [user.user_id]: { ...roleDraft, account_id: e.target.value },
                        }))
                      }
                    >
                      <option value="">Accès global</option>
                      {accounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>
                          {acc.name}
                        </option>
                      ))}
                    </select>
                    <button type="button" onClick={() => handleAddRoleToUser(user)}>
                      Ajouter
                    </button>
                  </div>
                </div>

                <div className="user-section">
                  <h4>Overrides</h4>
                  <div className="chip-list">
                    {user.overrides.map((override, idx) => (
                      <span key={override.id || `${override.permission_code}-${idx}`} className="chip removable">
                        {override.permission_code}{" "}
                        {override.is_allowed ? "(autorisé)" : "(bloqué)"}
                        {override.account_id && accountMap[override.account_id] && (
                          <small> • {accountMap[override.account_id].name}</small>
                        )}
                        <button onClick={() => handleRemoveOverrideFromUser(user, idx)}>×</button>
                      </span>
                    ))}
                    {!user.overrides.length && <span>Aucun override.</span>}
                  </div>
                  <div className="inline-form">
                    <select
                      className="app-select"
                      value={overrideDraft.permission_code}
                      onChange={(e) =>
                        setOverrideDrafts((prev) => ({
                          ...prev,
                          [user.user_id]: { ...overrideDraft, permission_code: e.target.value },
                        }))
                      }
                    >
                      <option value="">Permission</option>
                      {permissions.map((perm) => (
                        <option key={perm.code} value={perm.code}>
                          {perm.code}
                        </option>
                      ))}
                    </select>
                    <select
                      className="app-select"
                      value={overrideDraft.account_id}
                      onChange={(e) =>
                        setOverrideDrafts((prev) => ({
                          ...prev,
                          [user.user_id]: { ...overrideDraft, account_id: e.target.value },
                        }))
                      }
                    >
                      <option value="">Global</option>
                      {accounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>
                          {acc.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className="app-select"
                      value={overrideDraft.is_allowed ? "allow" : "deny"}
                      onChange={(e) =>
                        setOverrideDrafts((prev) => ({
                          ...prev,
                          [user.user_id]: {
                            ...overrideDraft,
                            is_allowed: e.target.value === "allow",
                          },
                        }))
                      }
                    >
                      <option value="allow">Autoriser</option>
                      <option value="deny">Bloquer</option>
                    </select>
                    <button type="button" onClick={() => handleAddOverrideToUser(user)}>
                      Ajouter
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}

