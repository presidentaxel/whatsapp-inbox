export default function ConversationList({
  data,
  selectedId,
  onSelect,
  emptyLabel = "Aucune conversation",
}) {
  if (!data.length) {
    return <div className="conversation-list empty">{emptyLabel}</div>;
  }

  return (
    <div className="conversation-list">
      {data.map((c) => {
        const displayName =
          c.contacts?.display_name || c.contacts?.whatsapp_number || c.client_number;
        const timeLabel = c.updated_at
          ? new Date(c.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
          : "";
        return (
          <div
            key={c.id}
            className={`conversation-item ${selectedId === c.id ? "active" : ""}`}
            onClick={() => onSelect(c)}
          >
            <div className="conversation-item__header">
              <div className="conversation-name">
                {displayName}
                {c.is_favorite && <span className="favorite-dot">★</span>}
              </div>
              <span className="conversation-time">{timeLabel}</span>
            </div>
            <div className="conversation-meta">
              <span>{c.client_number}</span>
              {c.unread_count > 0 && <span className="badge">{c.unread_count}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}