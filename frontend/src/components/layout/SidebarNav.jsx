import { FiMessageSquare, FiUsers, FiSettings } from "react-icons/fi";

const NAV_ITEMS = [
  { id: "chat", icon: <FiMessageSquare /> },
  { id: "contacts", icon: <FiUsers /> },
  { id: "settings", icon: <FiSettings /> },
];

export default function SidebarNav({ active = "chat", onSelect, allowedItems }) {
  const whitelist = allowedItems ?? NAV_ITEMS.map((item) => item.id);
  return (
    <nav className="sidebar-nav">
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
    </nav>
  );
}

