import { useState, useEffect } from 'react';
import { FiArrowLeft, FiUser, FiShield, FiCheck, FiX, FiEdit2, FiTrash2, FiSearch } from 'react-icons/fi';
import { api } from '../../api/axiosClient';
import '../../styles/mobile-team-panel.css';

export default function MobileTeamPanel({ onBack }) {
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedUser, setSelectedUser] = useState(null);
  const [editingUser, setEditingUser] = useState(null);
  const [currentUserProfile, setCurrentUserProfile] = useState(null);

  useEffect(() => {
    loadData();
    loadCurrentUserProfile();
  }, []);

  const loadCurrentUserProfile = async () => {
    try {
      const res = await api.get('/auth/me');
      setCurrentUserProfile(res.data);
    } catch (error) {
      console.error('Error loading current user profile:', error);
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [usersRes, rolesRes] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/roles')
      ]);
      setUsers(usersRes.data || []);
      setRoles(rolesRes.data || []);
    } catch (error) {
      console.error('Error loading team data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Vérifier les permissions
  const hasPermission = (permissionCode) => {
    if (!currentUserProfile) return false;
    const global = currentUserProfile.permissions?.global || [];
    return global.includes(permissionCode);
  };

  const canManageRoles = hasPermission('roles.manage');
  const canManageUsers = hasPermission('users.manage');
  const canViewRoles = hasPermission('roles.manage') || hasPermission('users.manage');

  const handleToggleUserStatus = async (userId, currentStatus) => {
    try {
      await api.post(`/admin/users/${userId}/status`, {
        is_active: !currentStatus
      });
      await loadData();
    } catch (error) {
      console.error('Error updating user status:', error);
      alert('Erreur lors de la mise à jour du statut');
    }
  };

  const handleUpdateUserRoles = async (userId, roleAssignments) => {
    try {
      await api.put(`/admin/users/${userId}/roles`, {
        assignments: roleAssignments
      });
      await loadData();
      setEditingUser(null);
    } catch (error) {
      console.error('Error updating user roles:', error);
      alert('Erreur lors de la mise à jour des rôles');
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!confirm('Êtes-vous sûr de vouloir supprimer cet utilisateur ? Cette action est irréversible.')) {
      return;
    }
    try {
      await api.delete(`/admin/users/${userId}`);
      await loadData();
      setSelectedUser(null);
    } catch (error) {
      console.error('Error deleting user:', error);
      if (error.response?.data?.detail === 'cannot_delete_self') {
        alert('Vous ne pouvez pas vous supprimer vous-même');
      } else {
        alert('Erreur lors de la suppression de l\'utilisateur');
      }
    }
  };

  const filteredUsers = users.filter(user => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      user.email?.toLowerCase().includes(term) ||
      user.display_name?.toLowerCase().includes(term)
    );
  });

  const getUserRoles = (user) => {
    return user.roles || [];
  };

  const getRoleName = (roleId) => {
    const role = roles.find(r => r.id === roleId);
    return role?.name || roleId;
  };

  if (selectedUser) {
    return (
      <UserDetailView
        user={selectedUser}
        roles={roles}
        onBack={() => setSelectedUser(null)}
        onUpdateRoles={handleUpdateUserRoles}
        onToggleStatus={handleToggleUserStatus}
        onDelete={canManageUsers ? handleDeleteUser : null}
        canManageRoles={canManageRoles}
        canManageUsers={canManageUsers}
        canViewRoles={canViewRoles}
      />
    );
  }

  if (loading) {
    return (
      <div className="mobile-team-panel">
        <header className="mobile-panel-header">
          <button className="icon-btn" onClick={onBack} title="Retour">
            <FiArrowLeft />
          </button>
          <h1>Équipe</h1>
        </header>
        <div className="mobile-team-panel__loading">
          <p>Chargement...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mobile-team-panel">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Équipe</h1>
      </header>

      <div className="mobile-panel-search">
        <div className="search-box">
          <FiSearch />
          <input
            type="text"
            placeholder="Rechercher un membre..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="mobile-team-panel__content">
        <div className="mobile-team-panel__stats">
          <div className="mobile-team-panel__stat">
            <span className="mobile-team-panel__stat-value">{users.length}</span>
            <span className="mobile-team-panel__stat-label">Membres</span>
          </div>
          <div className="mobile-team-panel__stat">
            <span className="mobile-team-panel__stat-value">
              {users.filter(u => u.is_active).length}
            </span>
            <span className="mobile-team-panel__stat-label">Actifs</span>
          </div>
        </div>

        <div className="mobile-team-panel__list">
          {filteredUsers.map((user) => (
            <div
              key={user.user_id}
              className="mobile-team-panel__item"
              onClick={() => setSelectedUser(user)}
            >
              <div className="mobile-team-panel__item-avatar">
                {(user.display_name || user.email || '?').charAt(0).toUpperCase()}
              </div>
              <div className="mobile-team-panel__item-content">
                <div className="mobile-team-panel__item-name">
                  {user.display_name || user.email?.split('@')[0] || 'Utilisateur'}
                </div>
                <div className="mobile-team-panel__item-email">{user.email}</div>
                {canViewRoles && (
                  <div className="mobile-team-panel__item-roles">
                    {getUserRoles(user).map((role, idx) => (
                      <span key={idx} className="mobile-team-panel__role-badge">
                        {getRoleName(role.role_id)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="mobile-team-panel__item-status">
                <div
                  className={`mobile-team-panel__status-indicator ${user.is_active ? 'active' : 'inactive'}`}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function UserDetailView({ user, roles, onBack, onUpdateRoles, onToggleStatus, onDelete, canManageRoles, canManageUsers, canViewRoles }) {
  // Un seul rôle à la fois - prendre le premier rôle existant ou null
  const [selectedRoleId, setSelectedRoleId] = useState(
    (user.roles && user.roles.length > 0) ? user.roles[0].role_id : null
  );

  const handleRoleSelect = (roleId) => {
    // Si on clique sur le rôle déjà sélectionné, on le désélectionne
    setSelectedRoleId(prev => prev === roleId ? null : roleId);
  };

  const handleSave = () => {
    // Un seul rôle - soit un tableau avec un élément, soit vide
    const assignments = selectedRoleId ? [{
      role_id: selectedRoleId,
      account_id: null
    }] : [];
    onUpdateRoles(user.user_id, assignments);
  };

  return (
    <div className="mobile-team-panel">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Membre</h1>
      </header>

      <div className="mobile-team-panel__detail">
        <div className="mobile-team-panel__detail-avatar">
          {(user.display_name || user.email || '?').charAt(0).toUpperCase()}
        </div>

        <div className="mobile-team-panel__detail-info">
          <h2>{user.display_name || user.email?.split('@')[0] || 'Utilisateur'}</h2>
          <p>{user.email}</p>
        </div>

        {canManageUsers && (
          <div className="mobile-team-panel__detail-section">
            <h3>Statut</h3>
            <div className="mobile-team-panel__toggle-row">
              <span>{user.is_active ? 'Actif' : 'Inactif'}</span>
              <button
                className={`mobile-team-panel__toggle-btn ${user.is_active ? 'active' : ''}`}
                onClick={() => onToggleStatus(user.user_id, user.is_active)}
              >
                <span className="mobile-team-panel__toggle-slider"></span>
              </button>
            </div>
          </div>
        )}

        {canViewRoles && (
          <div className="mobile-team-panel__detail-section">
            <h3>Rôle</h3>
            {canManageRoles ? (
              <>
                <div className="mobile-team-panel__roles-list">
                  {roles.map((role) => (
                    <div
                      key={role.id}
                      className={`mobile-team-panel__role-item ${selectedRoleId === role.id ? 'active' : ''}`}
                      onClick={() => handleRoleSelect(role.id)}
                    >
                      <div className="mobile-team-panel__role-info">
                        <FiShield />
                        <span>{role.name}</span>
                      </div>
                      {selectedRoleId === role.id && <FiCheck />}
                    </div>
                  ))}
                </div>
                <button
                  className="mobile-team-panel__save-btn"
                  onClick={handleSave}
                >
                  Enregistrer les modifications
                </button>
              </>
            ) : (
              <div className="mobile-team-panel__roles-list">
                {roles.map((role) => (
                  <div
                    key={role.id}
                    className={`mobile-team-panel__role-item ${selectedRoleId === role.id ? 'active' : ''}`}
                  >
                    <div className="mobile-team-panel__role-info">
                      <FiShield />
                      <span>{role.name}</span>
                    </div>
                    {selectedRoleId === role.id && <FiCheck />}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {canManageUsers && onDelete && (
          <div className="mobile-team-panel__detail-section">
            <button
              className="mobile-team-panel__delete-btn"
              onClick={() => onDelete(user.user_id)}
            >
              <FiTrash2 />
              Supprimer l'utilisateur
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

