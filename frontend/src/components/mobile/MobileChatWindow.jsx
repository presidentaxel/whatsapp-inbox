import { useCallback, useEffect, useRef, useState } from "react";
import { FiArrowLeft, FiMoreVertical, FiUser, FiSearch, FiUsers, FiImage } from "react-icons/fi";
import { getMessages, sendMessage } from "../../api/messagesApi";
import { supabaseClient } from "../../api/supabaseClient";
import MessageBubble from "../chat/MessageBubble";
import MobileMessageInput from "./MobileMessageInput";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function MobileChatWindow({ conversation, onBack, onRefresh }) {
  const [messages, setMessages] = useState([]);
  const [showMenu, setShowMenu] = useState(false);
  const messagesEndRef = useRef(null);

  const displayName = conversation?.contacts?.display_name ||
                     formatPhoneNumber(conversation?.client_number) ||
                     conversation?.client_number;

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => {
      const aTs = new Date(a.timestamp || a.created_at || 0).getTime();
      const bTs = new Date(b.timestamp || b.created_at || 0).getTime();
      return aTs - bTs;
    });
  }, []);

  const refreshMessages = useCallback(() => {
    if (!conversation?.id) return;
    getMessages(conversation.id)
      .then((res) => {
        const newMessages = res.data || [];
        console.log(`📨 Messages récupérés: ${newMessages.length}`);
        
        // Log des messages avec média pour debug
        newMessages.forEach(msg => {
          if (msg.media_id) {
            console.log(`🖼️ Message média:`, {
              id: msg.id,
              type: msg.message_type,
              media_id: msg.media_id,
              content: msg.content_text
            });
          }
        });
        
        setMessages(sortMessages(newMessages));
      })
      .catch(error => {
        console.error("❌ Erreur refresh messages:", error);
      });
  }, [conversation?.id, sortMessages]);

  // Fonction pour envoyer un message avec affichage optimiste (instantané)
  const handleSendMessage = useCallback(async (text) => {
    if (!conversation?.id || !text?.trim()) return;

    // Créer un message optimiste (affiché immédiatement)
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage = {
      id: tempId,
      client_temp_id: tempId,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: text.trim(),
      message_type: "text",
      status: "pending",
      timestamp: new Date().toISOString(),
    };

    // Ajouter immédiatement le message à l'interface
    setMessages((prev) => sortMessages([...prev, optimisticMessage]));

    // Scroller vers le bas immédiatement
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);

    // Envoyer réellement le message
    try {
      await sendMessage({
        conversation_id: conversation.id,
        content: text.trim(),
      });
      
      // Rafraîchir après un délai pour obtenir le message réel
      // Le message optimiste reste visible pendant l'envoi
      setTimeout(() => {
        refreshMessages();
      }, 1500);
    } catch (error) {
      console.error("❌ Erreur envoi message:", error);
      // En cas d'erreur, retirer le message optimiste et afficher une erreur
      setMessages((prev) => prev.filter(msg => msg.id !== tempId));
      alert("Erreur lors de l'envoi du message");
    }
  }, [conversation?.id, sortMessages, refreshMessages]);

  useEffect(() => {
    refreshMessages();
  }, [refreshMessages]);

  // Polling régulier pour mobile (plus fiable que realtime sur mobile)
  useEffect(() => {
    if (!conversation?.id) return;

    // Polling toutes les 5 secondes (évite d'écraser trop vite les messages optimistes)
    const pollInterval = setInterval(() => {
      refreshMessages();
    }, 5000);

    return () => {
      clearInterval(pollInterval);
    };
  }, [conversation?.id, refreshMessages]);

  // Realtime updates (backup si disponible)
  useEffect(() => {
    if (!conversation?.id) return;

    const channel = supabaseClient
      .channel(`messages:${conversation.id}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversation.id}`,
        },
        (payload) => {
          const incoming = payload.new;
          setMessages((prev) => {
            // Ne pas ajouter si c'est un doublon
            const exists = prev.some((msg) => msg.id === incoming.id);
            if (exists) return prev;
            
            // Remplacer les messages temporaires par le message réel si même timestamp
            const withoutTemp = prev.filter(msg => {
              if (msg.client_temp_id && incoming.content_text === msg.content_text) {
                const timeDiff = Math.abs(
                  new Date(incoming.timestamp).getTime() - 
                  new Date(msg.timestamp).getTime()
                );
                // Si moins de 3 secondes de différence, c'est le même message
                return timeDiff > 3000;
              }
              return true;
            });
            
            return sortMessages([...withoutTemp, incoming]);
          });
        }
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversation.id}`,
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
  }, [conversation?.id, sortMessages]);

  // Scroll vers le bas
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Gérer le clavier mobile : scroll automatique quand l'input est focus
  useEffect(() => {
    const handleFocus = () => {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      }, 300); // Délai pour que le clavier s'ouvre
    };

    const inputElements = document.querySelectorAll('.mobile-chat__input input, .mobile-chat__input textarea');
    inputElements.forEach(input => {
      input.addEventListener('focus', handleFocus);
    });

    return () => {
      inputElements.forEach(input => {
        input.removeEventListener('focus', handleFocus);
      });
    };
  }, []);

  return (
    <div className="mobile-chat">
      {/* Header avec bouton retour */}
      <header className="mobile-chat__header">
        <button className="mobile-chat__back" onClick={onBack}>
          <FiArrowLeft />
        </button>
        
        <div className="mobile-chat__contact" onClick={onBack}>
          <div className="mobile-chat__avatar">
            {displayName.charAt(0).toUpperCase()}
          </div>
          <div className="mobile-chat__info">
            <span className="mobile-chat__name">{displayName}</span>
          </div>
        </div>

        <div className="mobile-chat__actions">
          <button 
            className="icon-btn-round" 
            title="Menu"
            onClick={() => setShowMenu(!showMenu)}
          >
            <FiMoreVertical />
          </button>
        </div>

        {showMenu && (
          <div className="mobile-chat__menu">
            <button onClick={() => {
              setShowMenu(false);
              alert("Fonctionnalité disponible prochainement");
            }}>
              <FiUser /> Afficher le contact
            </button>
            <button onClick={() => {
              setShowMenu(false);
              alert("Fonctionnalité disponible prochainement");
            }}>
              <FiSearch /> Rechercher
            </button>
            <button onClick={() => {
              setShowMenu(false);
              alert("Fonctionnalité disponible prochainement");
            }}>
              <FiUsers /> Nouveau groupe
            </button>
            <button onClick={() => {
              setShowMenu(false);
              alert("Fonctionnalité disponible prochainement");
            }}>
              <FiImage /> Médias, liens et documents
            </button>
          </div>
        )}
      </header>

      {/* Messages */}
      <div className="mobile-chat__messages">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input mobile simplifié */}
      <div className="mobile-chat__input">
        <MobileMessageInput
          conversationId={conversation?.id}
          accountId={conversation?.account_id}
          onSend={handleSendMessage}
          onMediaSent={() => {
            // Attendre 2 secondes pour que le serveur traite le média
            console.log("⏳ Attente traitement média...");
            setTimeout(() => {
              console.log("🔄 Refresh après média");
              refreshMessages();
            }, 2000);
          }}
          disabled={false}
        />
      </div>
    </div>
  );
}

