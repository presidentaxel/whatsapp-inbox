import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FiSettings,
  FiMonitor,
  FiKey,
  FiLock,
  FiMessageSquare,
  FiVideo,
  FiBell,
  FiType,
  FiChevronDown,
  FiSearch,
  FiUser,
  FiShield,
  FiCloud,
  FiFolder,
  FiUpload,
  FiLoader,
} from "react-icons/fi";
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
import { createAccount, deleteAccount, updateAccountGoogleDrive, initGoogleDriveAuth, disconnectGoogleDrive, listGoogleDriveFolders, backfillGoogleDrive } from "../../api/accountsApi";
import NotificationSettings from "./NotificationSettings";
import PermissionsTable from "./PermissionsTable";
import DiscussionSettings from "./DiscussionSettings";
import GeneralSettings from "./GeneralSettings";
import GoogleDriveFolderPicker from "./GoogleDriveFolderPicker";

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
  canViewAccounts,
  canManageAccounts,
  canManageRoles,
  canManageUsers,
  canViewPermissions,
  canManagePermissions,
  onAccountsRefresh,
  refreshProfile,
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
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedGoogleDrive, setExpandedGoogleDrive] = useState({});
  const [googleDriveFolderIds, setGoogleDriveFolderIds] = useState({});
  const [showFolderPicker, setShowFolderPicker] = useState(false);
  const [folderPickerAccountId, setFolderPickerAccountId] = useState(null);
  const [backfilling, setBackfilling] = useState({});

  const accountMap = useMemo(
    () => Object.fromEntries(accounts.map((acc) => [acc.id, acc])),
    [accounts]
  );

  const loadAdminData = useCallback(async () => {
    // Charger les données si on peut voir ou gérer les permissions
    if (!canManagePermissions && !canViewPermissions) return;
    setLoadingAdmin(true);
    try {
      if (canManagePermissions || canViewPermissions) {
        // Charger les permissions et rôles si on peut les voir
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
  }, [canManagePermissions, canManageUsers, canViewPermissions]);

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

  const handleUpdateGoogleDrive = async (accountId, config) => {
    try {
      await updateAccountGoogleDrive(accountId, config);
      setStatusMessage("Configuration Google Drive mise à jour avec succès.");
      onAccountsRefresh?.();
    } catch (error) {
      console.error("update google drive error", error);
      setStatusMessage("Erreur lors de la mise à jour de Google Drive.");
    }
  };

  const toggleGoogleDriveExpanded = (accountId) => {
    setExpandedGoogleDrive((prev) => ({
      ...prev,
      [accountId]: !prev[accountId],
    }));
  };

  const handleConnectGoogleDrive = async (accountId) => {
    try {
      const response = await initGoogleDriveAuth(accountId);
      if (response.data?.authorization_url) {
        window.location.href = response.data.authorization_url;
      }
    } catch (error) {
      console.error("init google drive auth error", error);
      setStatusMessage("Erreur lors de l'initialisation de la connexion Google Drive.");
    }
  };

  const handleDisconnectGoogleDrive = async (accountId) => {
    if (!window.confirm("Déconnecter Google Drive de ce compte ?")) return;
    try {
      await disconnectGoogleDrive(accountId);
      setStatusMessage("Google Drive déconnecté avec succès.");
      onAccountsRefresh?.();
    } catch (error) {
      console.error("disconnect google drive error", error);
      setStatusMessage("Erreur lors de la déconnexion de Google Drive.");
    }
  };

  const handleOpenFolderPicker = (accountId) => {
    setFolderPickerAccountId(accountId);
    setShowFolderPicker(true);
  };

  const handleFolderSelect = (accountId, folderId) => {
    setGoogleDriveFolderIds((prev) => ({
      ...prev,
      [accountId]: folderId,
    }));
    handleUpdateGoogleDrive(accountId, {
      google_drive_folder_id: folderId,
    });
    setShowFolderPicker(false);
    setFolderPickerAccountId(null);
  };

  const handleBackfillGoogleDrive = async (accountId) => {
    if (!window.confirm("Uploader tous les médias existants vers Google Drive ? Cela peut prendre du temps.")) return;
    
    setBackfilling((prev) => ({ ...prev, [accountId]: true }));
    setStatusMessage("Upload des médias en cours...");
    
    try {
      const response = await backfillGoogleDrive(accountId, 100);
      if (response.data?.status === "skipped") {
        setStatusMessage(`Backfill ignoré : ${response.data.reason || "Google Drive non configuré"}`);
      } else {
        setStatusMessage(
          `Backfill terminé : ${response.data.uploaded || 0} uploadés, ${response.data.failed || 0} échecs sur ${response.data.processed || 0} traités.`
        );
      }
      onAccountsRefresh?.();
    } catch (error) {
      console.error("Error backfilling Google Drive:", error);
      const errorMessage = error.response?.data?.detail || error.message || "Erreur lors de l'upload des médias vers Google Drive.";
      setStatusMessage(`Erreur : ${errorMessage}`);
    } finally {
      setBackfilling((prev) => ({ ...prev, [accountId]: false }));
    }
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

  const navItems = useMemo(() => {
    // Menus WhatsApp exacts (copiés-collés de WhatsApp Desktop)
    const base = [
      {
        id: "general",
        label: "Général",
        icon: FiMonitor,
        description: "Démarrer et fermer",
      },
      {
        id: "discussions",
        label: "Discussions",
        icon: FiMessageSquare,
        description: "Thème, fond d'écran, paramètres des discussions",
      },
      {
        id: "notifications",
        label: "Notifications",
        icon: FiBell,
        description: "Notifications de messages",
      },
    ];
    
    // Menus supplémentaires pour les fonctionnalités existantes
    // Managers peuvent voir les comptes, mais seuls Admin peuvent les gérer
    if (canViewAccounts || canManageAccounts)
      base.push({
        id: "accounts",
        label: "Comptes WhatsApp",
        icon: FiShield,
        description: "Gérer les comptes WhatsApp Cloud API",
      });
        // Remplacement du système de rôles/utilisateurs par le nouveau système de permissions
        // Seuls Admin et DEV peuvent voir l'onglet Permissions (Manager ne voit rien)
        // canManagePermissions = Admin (permissions.manage) - peut modifier
        // canViewPermissions = DEV (permissions.view) - peut seulement voir
        if (canManagePermissions || canViewPermissions)
          base.push({
            id: "permissions",
            label: "Permissions",
            icon: FiShield,
            description: "Gérer les accès par compte WhatsApp",
          });
    return base;
  }, [canViewAccounts, canManageAccounts, canManageRoles, canManageUsers, canViewPermissions, canManagePermissions]);

  const filteredNavItems = useMemo(() => {
    if (!searchQuery.trim()) return navItems;
    const query = searchQuery.toLowerCase();
    return navItems.filter(
      (item) =>
        item.label.toLowerCase().includes(query) ||
        item.description.toLowerCase().includes(query)
    );
  }, [navItems, searchQuery]);

  const getUserInitials = (email) => {
    if (!email) return "U";
    const parts = email.split("@")[0].split(/[._-]/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return email[0].toUpperCase();
  };

  const renderPlaceholder = () => (
    <div className="settings-content__empty">
      <FiSettings className="settings-content__empty-icon" />
      <h2 className="settings-content__empty-title">Paramètres</h2>
    </div>
  );

  return (
    <div className="settings-shell">
      <aside className="settings-menu">
        <h2 className="settings-menu__title">Paramètres</h2>
        
        <div className="settings-menu__search">
          <FiSearch className="settings-menu__search-icon" />
          <input
            type="text"
            placeholder="Rechercher dans les paramètres"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="settings-menu__search-input"
          />
        </div>

        <div className="settings-menu__profile">
          <div className="settings-menu__profile-avatar">
            {getUserInitials(currentUser?.email)}
          </div>
          <div className="settings-menu__profile-info">
            <div className="settings-menu__profile-name">
              {currentUser?.email?.split("@")[0]?.replace(/[._-]/g, " ") || "Utilisateur"}
            </div>
            <div className="settings-menu__profile-status">
              Salut ! J'utilise WhatsApp.
            </div>
          </div>
        </div>

        <nav className="settings-menu__nav">
          {filteredNavItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`settings-menu__item ${
                  activePanel === item.id ? "settings-menu__item--active" : ""
                }`}
                onClick={() => setActivePanel(item.id)}
              >
                <Icon className="settings-menu__item-icon" />
                <div className="settings-menu__item-content">
                  <div className="settings-menu__item-label">{item.label}</div>
                  {item.description && (
                    <div className="settings-menu__item-desc">{item.description}</div>
                  )}
                </div>
              </button>
            );
          })}
        </nav>
      </aside>

      <div className="settings-content">
        {activePanel === "general" && (
          <div className="settings-content__panel">
            <h1 className="settings-content__panel-title">Général</h1>
            <GeneralSettings />
            
            <section className="settings-content__section">
              <h2 className="settings-content__section-title">Profil</h2>
              <div className="settings-content__section-content">
                <p>{currentUser?.email || "Utilisateur connecté"}</p>
                <p className="muted">
                  Rôles actifs :{" "}
                  {currentUser?.roles?.length
                    ? currentUser.roles
                        .map((r) => (r.role_name ? r.role_name : r.role_slug))
                        .join(", ")
                    : "aucun"}
                </p>
                <button className="settings-btn settings-btn--danger" onClick={onSignOut}>
                  Déconnexion
                </button>
              </div>
            </section>

            <section className="settings-content__section">
              <h2 className="settings-content__section-title">Comptes disponibles</h2>
              <div className="settings-content__section-content">
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
              </div>
            </section>
          </div>
        )}

        {activePanel === "notifications" && (
          <div className="settings-content__panel">
            <h1 className="settings-content__panel-title">Notifications</h1>
            <div className="settings-content__section-content">
              <NotificationSettings accounts={accounts} />
            </div>
          </div>
        )}

        {activePanel === "compte" && renderPlaceholder()}
          {activePanel === "confidentialite" && renderPlaceholder()}
          {activePanel === "discussions" && (
            <div className="settings-content__panel">
              <h1 className="settings-content__panel-title">Discussions</h1>
              <section className="settings-content__section">
                <DiscussionSettings />
              </section>
            </div>
          )}

      {activePanel === "accounts" && (canViewAccounts || canManageAccounts) && (
        <div className="settings-content__panel">
          <h1 className="settings-content__panel-title">Comptes WhatsApp</h1>
          <section className="settings-content__section">
            <h2 className="settings-content__section-title">Gestion des comptes</h2>
            <p className="muted">
              {canManageAccounts 
                ? "Ajoute tes numéros WhatsApp Cloud API et choisis les membres qui y auront accès."
                : "Visualise les comptes WhatsApp Cloud API configurés."}
            </p>
            {statusMessage && <p>{statusMessage}</p>}
          {accounts.length ? (
            <div className="account-grid">
              {accounts.map((acc) => {
                const isGoogleDriveExpanded = expandedGoogleDrive[acc.id];
                const googleDriveConnected = acc.google_drive_connected || false;
                const googleDriveEnabled = acc.google_drive_enabled || false;
                const googleDriveFolderId = acc.google_drive_folder_id || "";
                return (
                  <article key={acc.id} className="account-card">
                    <header>
                      <strong>{acc.name}</strong>
                      <span>{acc.phone_number || "Numéro inconnu"}</span>
                    </header>
                    <div className="account-meta">
                      <span>ID : {acc.id}</span>
                      <span>Phone ID : {acc.phone_number_id}</span>
                    </div>
                    
                    {canManageAccounts && (
                      <>
                        <div className="account-card__section">
                          <button
                            className="account-card__section-toggle"
                            onClick={() => toggleGoogleDriveExpanded(acc.id)}
                            type="button"
                          >
                            <FiCloud className="account-card__section-icon" />
                            <span>Google Drive</span>
                            <span className={googleDriveConnected ? "account-card__badge account-card__badge--enabled" : "account-card__badge"}>
                              {googleDriveConnected ? "Connecté" : "Non connecté"}
                            </span>
                          </button>
                          
                          {isGoogleDriveExpanded && (
                            <div className="account-card__section-content">
                              {!googleDriveConnected ? (
                                <>
                                  <p className="muted" style={{ marginBottom: "1rem" }}>
                                    Connectez votre compte Google Drive pour activer l'upload automatique des documents.
                                    Les fichiers seront organisés par numéro de téléphone.
                                  </p>
                                  <button
                                    className="settings-btn"
                                    onClick={() => handleConnectGoogleDrive(acc.id)}
                                    type="button"
                                  >
                                    <FiCloud style={{ marginRight: "0.5rem" }} />
                                    Se connecter avec Google Drive
                                  </button>
                                </>
                              ) : (
                                <>
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                                    <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>
                                      Compte Google connecté
                                    </span>
                                    <button
                                      className="danger subtle"
                                      onClick={() => handleDisconnectGoogleDrive(acc.id)}
                                      type="button"
                                    >
                                      Déconnecter
                                    </button>
                                  </div>
                                  
                                  <label className="account-card__toggle-label">
                                    <input
                                      type="checkbox"
                                      checked={googleDriveEnabled}
                                      onChange={(e) =>
                                        handleUpdateGoogleDrive(acc.id, {
                                          google_drive_enabled: e.target.checked,
                                        })
                                      }
                                    />
                                    <span>Activer l'upload automatique vers Google Drive</span>
                                  </label>
                                  
                                  {googleDriveEnabled && (
                                    <div className="account-card__input-group">
                                      <label>
                                        Dossier racine Google Drive
                                        <div className="google-drive-folder-selector">
                                          <div className="google-drive-folder-selector__current">
                                            {googleDriveFolderId ? (
                                              <span className="folder-path">
                                                <FiFolder /> Dossier sélectionné
                                              </span>
                                            ) : (
                                              <span className="folder-path muted">
                                                <FiFolder /> Racine du Drive
                                              </span>
                                            )}
                                          </div>
                                          <button
                                            type="button"
                                            className="btn-secondary"
                                            onClick={() => handleOpenFolderPicker(acc.id)}
                                          >
                                            <FiFolder /> Parcourir les dossiers
                                          </button>
                                        </div>
                                      </label>
                                      <small className="muted">
                                        Le dossier racine où seront créés les dossiers par numéro de téléphone.
                                        Les documents seront organisés dans des dossiers nommés d'après le numéro de téléphone de chaque contact.
                                        Si aucun dossier n'est sélectionné, la racine de votre Google Drive sera utilisée.
                                      </small>
                                      <button
                                        type="button"
                                        className="btn-secondary"
                                        onClick={() => handleBackfillGoogleDrive(acc.id)}
                                        disabled={backfilling[acc.id]}
                                        style={{ marginTop: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}
                                      >
                                        {backfilling[acc.id] ? (
                                          <>
                                            <FiLoader className="spinning" />
                                            Upload en cours...
                                          </>
                                        ) : (
                                          <>
                                            <FiUpload />
                                            Uploader les médias existants
                                          </>
                                        )}
                                      </button>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                          )}
                        </div>
                        
                        <button
                          className="danger subtle"
                          onClick={() => handleDeleteAccount(acc.id)}
                          type="button"
                        >
                          Supprimer
                        </button>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <p>Aucun compte pour le moment.</p>
          )}

          {canManageAccounts && (
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
          )}
          </section>
        </div>
      )}

      {activePanel === "permissions" && (canManagePermissions || canViewPermissions) && (
        <div className="settings-content__panel">
          <h1 className="settings-content__panel-title">Permissions</h1>
          <section className="settings-content__section">
            <h2 className="settings-content__section-title">Accès par compte WhatsApp</h2>
            <PermissionsTable
              accounts={accounts}
              currentUserRole={
                (currentUser?.roles && currentUser.roles.length > 0 
                  ? currentUser.roles[0]?.role_slug 
                  : currentUser?.role_slug) || null
              }
              canManagePermissions={canManagePermissions}
              currentUserId={currentUser?.id}
              refreshProfile={refreshProfile}
            />
          </section>
        </div>
      )}

      {/* Anciennes sections roles/users - conservées pour référence mais non affichées */}
      {false && activePanel === "users" && canManageUsers && (
        <div className="settings-content__panel">
          <h1 className="settings-content__panel-title">Utilisateurs</h1>
          <section className="settings-content__section">
            <h2 className="settings-content__section-title">Gestion des utilisateurs</h2>
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
        </div>
      )}
      </div>

      {showFolderPicker && folderPickerAccountId && (
        <GoogleDriveFolderPicker
          accountId={folderPickerAccountId}
          currentFolderId={googleDriveFolderIds[folderPickerAccountId] || accounts.find(acc => acc.id === folderPickerAccountId)?.google_drive_folder_id || "root"}
          onSelect={(folderId) => handleFolderSelect(folderPickerAccountId, folderId)}
          onClose={() => {
            setShowFolderPicker(false);
            setFolderPickerAccountId(null);
          }}
        />
      )}
    </div>
  );
}

