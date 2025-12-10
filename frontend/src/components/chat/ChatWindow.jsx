import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiSearch, FiInfo } from "react-icons/fi";
import { AiFillStar, AiOutlineStar } from "react-icons/ai";
import { getMessages, sendMessage, editMessage, deleteMessageApi } from "../../api/messagesApi";
import { markConversationRead } from "../../api/conversationsApi";
import MessageBubble from "./MessageBubble";
import AdvancedMessageInput from "./AdvancedMessageInput";
import TypingIndicator from "./TypingIndicator";
import { supabaseClient } from "../../api/supabaseClient";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { notifyNewMessage } from "../../utils/notifications";
import { useAuth } from "../../context/AuthContext";

export default function ChatWindow({
  conversation,
  onFavoriteToggle,
  onBotModeChange,
  canSend = true,
  isWindowActive = true,
}) {
  const { profile } = useAuth();
  const [messages, setMessages] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showInfo, setShowInfo] = useState(false);
  const [botTogglePending, setBotTogglePending] = useState(false);
  const [reactionTargetId, setReactionTargetId] = useState(null);
  const [contextMenu, setContextMenu] = useState({ open: false, x: 0, y: 0, message: null });
  const [autoScroll, setAutoScroll] = useState(true);
  const [otherTyping, setOtherTyping] = useState(false);

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => {
      const aTs = new Date(a.timestamp || a.created_at || 0).getTime();
      const bTs = new Date(b.timestamp || b.created_at || 0).getTime();
      return aTs - bTs;
    });
  }, []);

  const conversationId = conversation?.id;
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const displayName =
    conversation?.contacts?.display_name ||
    conversation?.contacts?.whatsapp_number ||
    conversation?.client_number;

  const refreshMessages = useCallback(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    getMessages(conversationId).then((res) => {
      // Filtrer réactions/statuts
      const currentUserId = profile?.id;
      const filtered = res.data.filter((msg) => {
        const type = (msg.message_type || "").toLowerCase();
        if (["reaction", "status"].includes(type)) return false;
        if (currentUserId && Array.isArray(msg.deleted_for_user_ids) && msg.deleted_for_user_ids.includes(currentUserId)) {
          return false;
        }
        return true;
      });
      setMessages(sortMessages(filtered));
    });
  }, [conversationId, sortMessages, profile?.id]);

  useEffect(() => {
    refreshMessages();
  }, [refreshMessages]);

  // Marquer la conversation comme lue quand elle est ouverte et active
  useEffect(() => {
    if (conversationId && isWindowActive && conversation) {
      // Marquer comme lue après un court délai pour éviter les appels trop fréquents
      const markReadTimeout = setTimeout(() => {
        markConversationRead(conversationId).catch((err) => {
          console.error("Failed to mark conversation as read:", err);
        });
      }, 1000);

      return () => clearTimeout(markReadTimeout);
    }
  }, [conversationId, isWindowActive, conversation]);

  // Fermer le menu contextuel sur clic ailleurs ou scroll
  useEffect(() => {
    const closeMenu = () => setContextMenu((prev) => ({ ...prev, open: false }));
    window.addEventListener("click", closeMenu);
    window.addEventListener("scroll", closeMenu, true);
    return () => {
      window.removeEventListener("click", closeMenu);
      window.removeEventListener("scroll", closeMenu, true);
    };
  }, []);

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

  // Détecter si l'autre personne est en train d'écrire
  // Basé sur le timing des messages entrants récents
  useEffect(() => {
    if (!conversationId || !isWindowActive || messages.length === 0) {
      return;
    }

    // Trouver le dernier message entrant
    const lastInboundMessage = messages
      .filter(m => (m.direction === "inbound" || (!m.from_me && m.direction !== "outbound")) && m.message_type !== "reaction")
      .sort((a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime())[0];

    if (!lastInboundMessage) {
      setOtherTyping(false);
      return;
    }

    const messageTime = new Date(lastInboundMessage.timestamp || 0).getTime();
    const now = Date.now();
    const timeSinceMessage = now - messageTime;

    // Si le dernier message entrant date de moins de 8 secondes,
    // simuler "en train d'écrire" pour indiquer que l'autre personne est active
    // (approximation car WhatsApp Cloud API ne fournit pas cette info directement)
    if (timeSinceMessage < 8000 && timeSinceMessage > 500) {
      setOtherTyping(true);
      const typingTimeout = setTimeout(() => {
        setOtherTyping(false);
      }, Math.max(0, 8000 - timeSinceMessage));
      
      return () => clearTimeout(typingTimeout);
    } else {
      setOtherTyping(false);
    }
  }, [messages, conversationId, isWindowActive]);

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
          
          // Ignorer les réactions - elles ne doivent pas être affichées comme des messages normaux
          if (incoming.message_type === "reaction") {
            return;
          }
          
          // Si c'est un message entrant (de l'autre personne), 
          // l'indicateur "en train d'écrire" sera géré par le useEffect qui surveille les messages
          
          // Afficher une notification si c'est un message entrant et que la fenêtre n'est pas au premier plan
          const hasFocus = document.hasFocus?.() === true;
          if (!incoming.from_me && (!isWindowActive || !hasFocus)) {
            notifyNewMessage(incoming, conversation);
          }
          
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
          // Si le statut d'un message sortant a changé (sent → delivered → read),
          // mettre à jour la liste pour afficher le nouveau statut
          setMessages((prev) =>
            sortMessages(prev.map((msg) => (msg.id === updated.id ? updated : msg)))
          );
        }
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "message_reactions",
        },
        () => {
          // Rafraîchir les messages quand une réaction change
          refreshMessages();
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
    if (autoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [filteredMessages, autoScroll]);

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setAutoScroll(distanceFromBottom < 120);
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    setAutoScroll(true);
  }, [conversationId]);

  useEffect(() => {
    if (!reactionTargetId) return;
    const t = setTimeout(() => setReactionTargetId(null), 2000);
    return () => clearTimeout(t);
  }, [reactionTargetId]);

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

  const handleContextMenu = (event, message) => {
    event.preventDefault();
    const menuWidth = 220;
    const menuHeight = 200;
    const clampedX = Math.min(event.clientX, window.innerWidth - menuWidth);
    const clampedY = Math.min(event.clientY, window.innerHeight - menuHeight);
    setContextMenu({
      open: true,
      x: clampedX,
      y: clampedY,
      message,
    });
  };

  const handleMenuAction = async (action) => {
    const msg = contextMenu.message;
    setContextMenu((prev) => ({ ...prev, open: false }));
    if (!msg) return;

    if (action === "delete_me") {
      try {
        await deleteMessageApi(msg.id, { scope: "me" });
      } finally {
        refreshMessages();
      }
      return;
    }

    if (action === "react") {
      setReactionTargetId(msg.id);
      return;
    }
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
        <div className="messages" ref={messagesContainerRef}>
          {filteredMessages.map((m) => (
            <MessageBubble 
              key={m.id} 
              message={m} 
              conversation={conversation}
              onReactionChange={refreshMessages}
              forceReactionOpen={reactionTargetId === m.id}
              onContextMenu={(e) => handleContextMenu(e, m)}
            />
          ))}
          {otherTyping && <TypingIndicator />}
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

      <AdvancedMessageInput 
        conversation={conversation}
        onSend={onSend}
        disabled={!canSend || !conversationId}
      />

      {contextMenu.open && (
        <div
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={() => handleMenuAction("react")}>Ajouter une réaction</button>
          <button onClick={() => handleMenuAction("delete_me")}>Supprimer pour moi</button>
        </div>
      )}
    </div>
  );
}