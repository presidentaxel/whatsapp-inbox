import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiSearch, FiInfo } from "react-icons/fi";
import { AiFillStar, AiOutlineStar } from "react-icons/ai";
import { getMessages, sendMessage } from "../../api/messagesApi";
import MessageBubble from "./MessageBubble";
import MessageInput from "./MessageInput";
import { supabaseClient } from "../../api/supabaseClient";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function ChatWindow({
  conversation,
  onFavoriteToggle,
  onBotModeChange,
  canSend = true,
  isWindowActive = true,
}) {
  const [messages, setMessages] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showInfo, setShowInfo] = useState(false);
  const [botTogglePending, setBotTogglePending] = useState(false);

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => {
      const aTs = new Date(a.timestamp || a.created_at || 0).getTime();
      const bTs = new Date(b.timestamp || b.created_at || 0).getTime();
      return aTs - bTs;
    });
  }, []);

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
    getMessages(conversationId).then((res) => setMessages(sortMessages(res.data)));
  }, [conversationId, sortMessages]);

  useEffect(() => {
    refreshMessages();
  }, [refreshMessages]);

  useEffect(() => {
    if (!conversationId || !isWindowActive) {
      return;
    }
    let cancelled = false;
    let timeoutId;
    const poll = async () => {
      await refreshMessages();
      if (!cancelled) {
        timeoutId = setTimeout(poll, 4500);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [conversationId, refreshMessages, isWindowActive]);

  useEffect(() => {
    if (!conversationId) {
      return undefined;
    }

    const channel = supabaseClient
      .channel(`messages:${conversationId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload) => {
          const incoming = payload.new;
          setMessages((prev) => {
            const exists = prev.some((msg) => msg.id === incoming.id);
            if (exists) {
              return sortMessages(prev.map((msg) => (msg.id === incoming.id ? incoming : msg)));
            }
            return sortMessages([...prev, incoming]);
          });
        }
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload) => {
          const updated = payload.new;
          setMessages((prev) =>
            sortMessages(prev.map((msg) => (msg.id === updated.id ? updated : msg)))
          );
        }
      )
      .subscribe();

    return () => {
      supabaseClient.removeChannel(channel);
    };
  }, [conversationId, sortMessages]);

  const onSend = async (text) => {
    if (!conversationId) return;
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage = {
      id: tempId,
      client_temp_id: tempId,
      conversation_id: conversationId,
      direction: "outbound",
      content_text: text,
      status: "pending",
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => sortMessages([...prev, optimisticMessage]));
    try {
      await sendMessage({ conversation_id: conversationId, content: text });
    } finally {
      refreshMessages();
    }
  };

  const subtitle = useMemo(() => {
    if (!conversation) return "";
    return formatPhoneNumber(conversation.client_number);
  }, [conversation]);

  const botEnabled = !!conversation?.bot_enabled;

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
          <img 
            src="/favicon.svg" 
            alt="Logo LMDCVTC" 
            className="empty-state-logo"
            style={{ width: "120px", height: "120px", marginBottom: "1.5rem" }}
          />
          <h2>Bienvenue sur WhatsApp LMDCVTC</h2>
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
        <div className="chat-bot-toggle">
          <span className="chat-bot-toggle__label">
            {botEnabled ? "Bot Gemini actif" : "Mode opérateur"}
          </span>
          <label className={`switch ${botEnabled ? "switch--on" : ""}`}>
            <input
              type="checkbox"
              checked={botEnabled}
              onChange={async () => {
                if (!conversation || !onBotModeChange) return;
                setBotTogglePending(true);
                try {
                  await onBotModeChange(conversation, !botEnabled);
                } finally {
                  setBotTogglePending(false);
                }
              }}
              disabled={!conversation || botTogglePending}
            />
            <span className="switch__slider" />
          </label>
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
              <strong>{formatPhoneNumber(conversation.client_number)}</strong>
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