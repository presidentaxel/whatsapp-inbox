import { useState, useEffect, useRef } from "react";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { formatRelativeDate } from "../../utils/date";
import { markConversationUnread } from "../../api/conversationsApi";

const HIDDEN_CONVERSATIONS_KEY = "hidden_conversations";

// Fonctions utilitaires pour gérer les conversations masquées dans localStorage
const getHiddenConversations = () => {
  try {
    const stored = localStorage.getItem(HIDDEN_CONVERSATIONS_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch {
    return [];
  }
};

const addHiddenConversation = (conversationId) => {
  try {
    const hidden = getHiddenConversations();
    if (!hidden.includes(conversationId)) {
      hidden.push(conversationId);
      localStorage.setItem(HIDDEN_CONVERSATIONS_KEY, JSON.stringify(hidden));
    }
  } catch (error) {
    console.error("Error hiding conversation:", error);
  }
};

export default function ConversationList({
  data,
  selectedId,
  onSelect,
  onRefresh,
  emptyLabel = "Aucune conversation",
}) {
  const [contextMenu, setContextMenu] = useState({ open: false, x: 0, y: 0, conversation: null });
  const [hiddenConversations, setHiddenConversations] = useState(getHiddenConversations());
  const containerRef = useRef(null);

  useEffect(() => {
    const closeMenu = () => setContextMenu((prev) => ({ ...prev, open: false }));
    window.addEventListener("click", closeMenu);
    window.addEventListener("scroll", closeMenu, true);
    return () => {
      window.removeEventListener("click", closeMenu);
      window.removeEventListener("scroll", closeMenu, true);
    };
  }, []);

  const handleContextMenu = (event, conversation) => {
    event.preventDefault();
    event.stopPropagation();
    const menuWidth = 200;
    const menuHeight = 150; // Ajusté pour 2 boutons
    const clampedX = Math.min(event.clientX, window.innerWidth - menuWidth);
    const clampedY = Math.min(event.clientY, window.innerHeight - menuHeight);
    setContextMenu({
      open: true,
      x: clampedX,
      y: clampedY,
      conversation,
    });
  };

  const handleMarkUnread = async () => {
    if (!contextMenu.conversation) return;
    try {
      await markConversationUnread(contextMenu.conversation.id);
      onRefresh?.();
    } catch (error) {
      console.error("Error marking conversation as unread:", error);
    } finally {
      setContextMenu({ open: false, x: 0, y: 0, conversation: null });
    }
  };

  const handleHideConversation = () => {
    if (!contextMenu.conversation) return;
    const conversationId = contextMenu.conversation.id;
    addHiddenConversation(conversationId);
    setHiddenConversations(getHiddenConversations());
    setContextMenu({ open: false, x: 0, y: 0, conversation: null });
    // Si la conversation masquée est actuellement sélectionnée, la désélectionner
    if (selectedId === conversationId) {
      onSelect(null);
    }
  };

  // Filtrer les conversations masquées
  const visibleConversations = data.filter((c) => !hiddenConversations.includes(c.id));

  if (!visibleConversations.length) {
    return <div className="conversation-list empty">{emptyLabel}</div>;
  }

  return (
    <div className="conversation-list" ref={containerRef}>
      {visibleConversations.map((c) => {
        const displayName =
          c.contacts?.display_name || c.contacts?.whatsapp_number || c.client_number;
        const timeLabel = c.updated_at
          ? formatRelativeDate(c.updated_at)
          : "";
        return (
          <div
            key={c.id}
            className={`conversation-item ${selectedId === c.id ? "active" : ""}`}
            onClick={() => onSelect(c)}
            onContextMenu={(e) => handleContextMenu(e, c)}
          >
            <div className="conversation-item__header">
              <div className="conversation-name">
                {displayName}
                {c.is_favorite && <span className="favorite-dot">★</span>}
              </div>
              <div className="conversation-item__header-meta">
                {c.bot_enabled && (
                  <span className="bot-pill bot-pill--on">
                    BOT MODE
                  </span>
                )}
                <span className="conversation-time">{timeLabel}</span>
              </div>
            </div>
            <div className="conversation-meta">
              <div className="conversation-meta__text">
                <span className="conversation-meta__phone" title={formatPhoneNumber(c.client_number)}>
                  {formatPhoneNumber(c.client_number)}
                </span>
                <span className="conversation-meta__preview" title={c.last_message || ""}>
                  {c.last_message || "—"}
                </span>
              </div>
              {c.unread_count > 0 && <span className="badge">{c.unread_count}</span>}
            </div>
          </div>
        );
      })}

      {contextMenu.open && (
        <div
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={handleMarkUnread}>Marquer comme non lu</button>
          <button onClick={handleHideConversation}>Masquer la conversation</button>
        </div>
      )}
    </div>
  );
}