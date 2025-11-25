import { FiCpu, FiMessageSquare, FiUsers, FiSettings, FiLogOut } from "react-icons/fi";

const NAV_ITEMS = [
  { id: "chat", icon: <FiMessageSquare /> },
  { id: "contacts", icon: <FiUsers /> },
  { id: "assistant", icon: <FiCpu /> },
  { id: "settings", icon: <FiSettings /> },
];

export default function SidebarNav({ active = "chat", onSelect, allowedItems, onSignOut }) {
  const whitelist = allowedItems ?? NAV_ITEMS.map((item) => item.id);
  return (
    <nav className="sidebar-nav">
      <div className="sidebar-nav__items">
        {NAV_ITEMS.filter((item) => whitelist.includes(item.id)).map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav__btn ${item.id === active ? "active" : ""}`}
            onClick={() => onSelect?.(item.id)}
          >
            {item.icon}
            {item.badge && <span className="sidebar-nav__badge">{item.badge}</span>}
          </button>
        ))}
      </div>
      
      {onSignOut && (
        <div className="sidebar-nav__bottom">
          <button
            className="sidebar-nav__btn sidebar-nav__btn--logout"
            onClick={onSignOut}
            title="Déconnexion"
          >
            <FiLogOut />
          </button>
        </div>
      )}
    </nav>
  );
}

