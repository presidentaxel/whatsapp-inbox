import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiSearch, FiInfo } from "react-icons/fi";
import { AiFillStar, AiOutlineStar } from "react-icons/ai";
import { getMessages, sendMessage } from "../../api/messagesApi";
import MessageBubble from "./MessageBubble";
import MessageInput from "./MessageInput";

export default function ChatWindow({ conversation, onFavoriteToggle, canSend = true }) {
  const [messages, setMessages] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showInfo, setShowInfo] = useState(false);

  const conversationId = conversation?.id;
  const messagesEndRef = useRef(null);
  const displayName =
    conversation?.contacts?.display_name ||
    conversation?.contacts?.whatsapp_number ||
    conversation?.client_number;

  const refreshMessages = useCallback(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    getMessages(conversationId).then((res) => setMessages(res.data));
  }, [conversationId]);

  useEffect(() => {
    refreshMessages();
  }, [refreshMessages]);

  useEffect(() => {
    if (!conversationId) {
      return;
    }
    const interval = setInterval(refreshMessages, 3000);
    return () => clearInterval(interval);
  }, [conversationId, refreshMessages]);

  const onSend = async (text) => {
    if (!conversationId) return;
    await sendMessage({ conversation_id: conversationId, content: text });
    refreshMessages();
  };

  const subtitle = useMemo(() => {
    if (!conversation) return "";
    return conversation.client_number;
  }, [conversation]);

  const filteredMessages = useMemo(() => {
    if (!showSearch || !searchTerm.trim()) {
      return messages;
    }
    const term = searchTerm.toLowerCase();
    return messages.filter((m) => (m.content_text || "").toLowerCase().includes(term));
  }, [messages, searchTerm, showSearch]);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [filteredMessages]);

  if (!conversationId) {
    return (
      <div className="chat-window empty-state">
        <div>
          <h2>Bienvenue 👋</h2>
          <p>Sélectionne un compte puis une conversation pour commencer.</p>
        </div>
      </div>
    );
  }

  const handleFavoriteClick = () => {
    if (!conversation) return;
    const next = !conversation.is_favorite;
    onFavoriteToggle?.(conversation, next);
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div>
          <div className="chat-title">{displayName}</div>
          <div className="chat-subtitle">{subtitle}</div>
        </div>
        <div className="chat-actions">
          <button
            title="Rechercher"
            className={showSearch ? "active" : ""}
            onClick={() => setShowSearch((p) => !p)}
          >
            <FiSearch />
          </button>
          <button
            title="Infos contact"
            className={showInfo ? "active" : ""}
            onClick={() => setShowInfo((p) => !p)}
          >
            <FiInfo />
          </button>
          <button
            title={conversation?.is_favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
            onClick={handleFavoriteClick}
          >
            {conversation?.is_favorite ? <AiFillStar /> : <AiOutlineStar />}
          </button>
        </div>
      </div>

      {showSearch && (
        <div className="chat-search-bar">
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Rechercher un message"
          />
          {searchTerm && (
            <button onClick={() => setSearchTerm("")} aria-label="Effacer la recherche">
              ×
            </button>
          )}
        </div>
      )}

      <div className="chat-body">
        <div className="messages">
          {filteredMessages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {showInfo && (
          <aside className="chat-info-panel">
            <h3>Informations</h3>
            <div className="info-row">
              <span>Nom</span>
              <strong>{displayName}</strong>
            </div>
            <div className="info-row">
              <span>Numéro</span>
              <strong>{conversation.client_number}</strong>
            </div>
            <div className="info-row">
              <span>Statut</span>
              <strong>{conversation.status}</strong>
            </div>
            <div className="info-row">
              <span>Messages non lus</span>
              <strong>{conversation.unread_count || 0}</strong>
            </div>
          </aside>
        )}
      </div>

      <MessageInput onSend={onSend} disabled={!canSend || !conversationId} />
    </div>
  );
}