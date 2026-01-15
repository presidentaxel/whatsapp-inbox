import { useState, useEffect } from "react";
import { FiPlus, FiEdit2, FiTrash2, FiUsers } from "react-icons/fi";

export default function BroadcastGroupsList({
  groups,
  selectedGroupId,
  onSelectGroup,
  onCreateGroup,
  onEditGroup,
  onDeleteGroup,
}) {
  const [contextMenu, setContextMenu] = useState({ open: false, x: 0, y: 0, group: null });

  const handleContextMenu = (event, group) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      open: true,
      x: event.clientX,
      y: event.clientY,
      group,
    });
  };

  const closeContextMenu = () => {
    setContextMenu({ open: false, x: 0, y: 0, group: null });
  };

  useEffect(() => {
    window.addEventListener("click", closeContextMenu);
    return () => window.removeEventListener("click", closeContextMenu);
  }, []);

  if (!groups || groups.length === 0) {
    return (
      <div className="broadcast-groups-list empty">
        <p>Aucun groupe de diffusion</p>
        <button className="btn-primary" onClick={onCreateGroup}>
          <FiPlus /> Créer un groupe
        </button>
      </div>
    );
  }

  return (
    <div className="broadcast-groups-list">
      <div className="broadcast-groups-list__header">
        <h3>Groupes de diffusion</h3>
        <button className="btn-icon" onClick={onCreateGroup} title="Créer un groupe">
          <FiPlus />
        </button>
      </div>
      
      <div className="broadcast-groups-list__items">
        {groups.map((group) => (
          <div
            key={group.id}
            className={`broadcast-group-item ${selectedGroupId === group.id ? "active" : ""}`}
            onClick={() => onSelectGroup(group)}
            onContextMenu={(e) => handleContextMenu(e, group)}
          >
            <div className="broadcast-group-item__icon">
              <FiUsers />
            </div>
            <div className="broadcast-group-item__content">
              <div className="broadcast-group-item__name">{group.name}</div>
              {group.description && (
                <div className="broadcast-group-item__description">{group.description}</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {contextMenu.open && (
        <div
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={() => { onEditGroup(contextMenu.group); closeContextMenu(); }}>
            <FiEdit2 /> Modifier
          </button>
          <button
            className="danger"
            onClick={() => {
              if (confirm(`Supprimer le groupe "${contextMenu.group.name}" ?`)) {
                onDeleteGroup(contextMenu.group.id);
              }
              closeContextMenu();
            }}
          >
            <FiTrash2 /> Supprimer
          </button>
        </div>
      )}
    </div>
  );
}

