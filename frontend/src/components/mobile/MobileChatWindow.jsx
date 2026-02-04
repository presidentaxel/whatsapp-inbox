import { useCallback, useEffect, useRef, useState } from "react";
import { FiArrowLeft, FiMoreVertical, FiUser, FiSearch, FiUsers, FiImage, FiChevronDown, FiFileText, FiLink, FiX, FiCpu, FiVideo, FiHeadphones, FiSliders } from "react-icons/fi";
import { getMessages } from "../../api/messagesApi";
import { toggleConversationBotMode } from "../../api/conversationsApi";
import { supabaseClient } from "../../api/supabaseClient";
import MessageBubble from "../chat/MessageBubble";
import MobileMessageInput from "./MobileMessageInput";
import { formatPhoneNumber } from "../../utils/formatPhone";
import MobileContactDetail from "./MobileContactDetail";
import MobileChatSettings from "./MobileChatSettings";

export default function MobileChatWindow({ conversation, onBack, onRefresh, onShowContact, onToggleBotMode }) {
  const [messages, setMessages] = useState([]);
  const [showMenu, setShowMenu] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const pendingOptimisticRef = useRef(new Map()); // tempId -> waMessageId pour le matching
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isUserScrolling, setIsUserScrolling] = useState(false);
  const [chatTheme, setChatTheme] = useState(localStorage.getItem('chatTheme') || 'default');
  const [chatWallpaper, setChatWallpaper] = useState(localStorage.getItem('chatWallpaper') || 'default');
  const [fontSize, setFontSize] = useState(localStorage.getItem('fontSize') || 'medium');
  const [mediaVisibility, setMediaVisibility] = useState(localStorage.getItem('mediaVisibility') !== 'false');
  const [showContactDetail, setShowContactDetail] = useState(false);
  const [showChatSettings, setShowChatSettings] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [showMedia, setShowMedia] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [filteredMessages, setFilteredMessages] = useState([]);
  const [isTogglingBot, setIsTogglingBot] = useState(false);

  // Écouter les changements de paramètres
  useEffect(() => {
    const handleStorageChange = () => {
      setChatTheme(localStorage.getItem('chatTheme') || 'default');
      setChatWallpaper(localStorage.getItem('chatWallpaper') || 'default');
      setFontSize(localStorage.getItem('fontSize') || 'medium');
      setMediaVisibility(localStorage.getItem('mediaVisibility') !== 'false');
    };
    window.addEventListener('storage', handleStorageChange);
    // Vérifier aussi les changements dans le même onglet
    const interval = setInterval(handleStorageChange, 500);
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(interval);
    };
  }, []);

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

        // Même principe que ChatWindow (PC) : remplacer les optimistes par le message réel,
        // jamais afficher les deux (realtime peut ajouter le réel avant le refresh).
        setMessages((prev) => {
          const usedRealIds = new Set();
          const usedWaMessageIds = new Set();
          const isOptimistic = (msg) => msg._isOptimistic || msg?.id?.startsWith?.("temp-");
          const pendingMap = pendingOptimisticRef.current;
          const out = [];

          const pushReal = (m) => {
            if (m.wa_message_id && usedWaMessageIds.has(m.wa_message_id)) return false;
            if (usedRealIds.has(m.id)) return false;
            out.push(m);
            usedRealIds.add(m.id);
            if (m.wa_message_id) usedWaMessageIds.add(m.wa_message_id);
            return true;
          };

          for (const msg of prev) {
            if (isOptimistic(msg)) {
              const waMessageId = pendingMap.get(msg.id);
              const realMsg = waMessageId ? newMessages.find(m => m.wa_message_id === waMessageId) : null;
              if (waMessageId && realMsg) {
                pendingMap.delete(msg.id);
                pushReal(realMsg);
                continue;
              }
              // En attente du réel (waMessageId connu mais pas encore dans l’API) : ne pas garder l’optimiste
              // pour éviter d’afficher optim + réel quand le realtime ajoutera le message.
              if (waMessageId) {
                continue;
              }
              out.push(msg);
              continue;
            }

            if (usedRealIds.has(msg.id)) continue;

            const fromNew = newMessages.find((m) => m.id === msg.id);
            if (fromNew) {
              pushReal(fromNew);
            } else {
              out.push(msg);
              usedRealIds.add(msg.id);
              if (msg.wa_message_id) usedWaMessageIds.add(msg.wa_message_id);
            }
          }

          for (const real of newMessages) {
            pushReal(real);
          }

          let sorted = sortMessages(out);
          const seenKey = new Set();
          sorted = sorted.filter((m) => {
            if (m._isOptimistic || m?.id?.startsWith?.("temp-")) return true;
            if (m.direction !== "outbound") return true;
            const content = m.content_text?.trim() ?? "";
            const ts = new Date(m.timestamp || m.created_at).getTime();
            const key = `${content}|${Math.floor(ts / 3000)}`;
            if (seenKey.has(key)) return false;
            seenKey.add(key);
            return true;
          });
          return sorted;
        });
      })
      .catch(error => {
        console.error("❌ Erreur refresh messages:", error);
      });
  }, [conversation?.id, sortMessages]);

  // Fonction appelée par MobileMessageInput pour afficher un message optimiste
  const handleSendMessage = useCallback((text, forceRefresh = false, data = null) => {
    // Signal de refresh après envoi réussi (text === null)
    if (text === null && !forceRefresh && data) {
      const { tempId, waMessageId } = data;
      if (tempId && waMessageId) {
        pendingOptimisticRef.current.set(tempId, waMessageId);
      }
      refreshMessages();
      return;
    }
    
    if (forceRefresh) {
      setMessages((prev) => prev.filter(msg => !msg._isOptimistic && !msg.id?.startsWith('temp-')));
      pendingOptimisticRef.current.clear();
      refreshMessages();
      return;
    }

    // Ajouter le message optimiste si fourni (data est le message optimiste ici)
    if (data && data._isOptimistic && conversation?.id) {
      setMessages((prev) => {
        const exists = prev.some(msg =>
          msg._isOptimistic &&
          msg._optimisticContent === data._optimisticContent &&
          Math.abs((msg._optimisticTime || 0) - (data._optimisticTime || 0)) < 2000
        );
        if (exists) return prev;
        return sortMessages([...prev, data]);
      });
      
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
        setIsUserScrolling(false);
        setShowScrollToBottom(false);
      }, 50);
    }
  }, [conversation?.id, refreshMessages, sortMessages]);

  useEffect(() => {
    refreshMessages();
    // Réinitialiser le scroll quand on charge les messages
    setIsUserScrolling(false);
  }, [refreshMessages]);

  // Polling régulier pour mobile (plus fiable que realtime sur mobile)
  useEffect(() => {
    if (!conversation?.id) return;

    // Polling toutes les 15 secondes (aligné avec ChatWindow, réduit charge)
    const pollInterval = setInterval(() => {
      refreshMessages();
    }, 15000);

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
            if (prev.some((msg) => msg.id === incoming.id)) return prev;
            if (incoming.wa_message_id && prev.some((msg) => msg.wa_message_id === incoming.wa_message_id)) return prev;

            const norm = (s) => (s || "").trim().replace(/\s+/g, " ");
            const incomingContent = norm(incoming.content_text);
            const incomingTime = new Date(incoming.timestamp || incoming.created_at).getTime();
            const isOutboundText = incoming.direction === "outbound" && (incoming.message_type === "text" || !incoming.message_type);

            const withoutTemp = prev.filter(msg => {
              if (!msg._isOptimistic && !msg.id?.startsWith("temp-")) {
                return true;
              }

              // Message texte outbound : retirer l’optimiste dès que le contenu correspond (évite le double affichage même bref)
              if (isOutboundText && incomingContent) {
                const optContent = norm(msg._optimisticContent ?? msg.content_text);
                if (optContent === incomingContent) {
                  const optTime = msg._optimisticTime ?? new Date(msg.timestamp || msg.created_at).getTime();
                  if (Math.abs(incomingTime - optTime) < 30000) {
                    return false;
                  }
                }
              }

              if (msg._optimisticContent !== undefined) {
                const optContent = norm(msg._optimisticContent ?? msg.content_text);
                const optTime = msg._optimisticTime ?? new Date(msg.timestamp || msg.created_at).getTime();
                if (optContent === incomingContent && Math.abs(incomingTime - optTime) < 15000) {
                  return false;
                }
              }

              if (msg._optimisticMediaId !== undefined) {
                const optMediaId = msg._optimisticMediaId;
                const optMediaType = msg._optimisticMediaType;
                const optCaption = msg._optimisticCaption;
                const optTime = msg._optimisticTime ?? new Date(msg.timestamp || msg.created_at).getTime();
                const incomingMediaId = incoming.media_id;
                const incomingMediaType = incoming.message_type;
                const incomingCaption = incoming.content_text?.trim();
                const sameMediaId = incomingMediaId === optMediaId;
                const sameTypeAndCaption = incomingMediaType === optMediaType &&
                  ((!incomingCaption && !optCaption) || incomingCaption === optCaption);
                const timeDiff = Math.abs(incomingTime - optTime);
                if ((sameMediaId || sameTypeAndCaption) && timeDiff < 15000) {
                  return false;
                }
              }

              return true;
            });

            const newMessages = sortMessages([...withoutTemp, incoming]);
            
            // Auto-scroll seulement si l'utilisateur est déjà en bas
            if (!isUserScrolling) {
              setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
              }, 100);
            }
            
            return newMessages;
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
  }, [conversation?.id, sortMessages, isUserScrolling]);

  // Réinitialiser le scroll quand on change de conversation
  useEffect(() => {
    setIsUserScrolling(false);
    setShowScrollToBottom(false);
    setShowMenu(false);
  }, [conversation?.id]);

  // Fermer le menu si on clique en dehors
  useEffect(() => {
    if (!showMenu) return;
    
    const handleClickOutside = (event) => {
      const actionsContainer = messagesContainerRef.current?.closest('.mobile-chat')?.querySelector('.mobile-chat__actions');
      if (actionsContainer && !actionsContainer.contains(event.target)) {
        setShowMenu(false);
      }
    };

    // Petit délai pour éviter que le clic qui ouvre le menu ne le ferme immédiatement
    const timeoutId = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('touchstart', handleClickOutside);
    }, 100);
    
    return () => {
      clearTimeout(timeoutId);
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [showMenu]);

  // Gérer le scroll et détecter si l'utilisateur scroll manuellement
  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const container = messagesContainerRef.current;
      if (!container) return;
      
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      setShowScrollToBottom(!isNearBottom);
      
      // Si l'utilisateur scroll vers le haut, on ne fait plus d'auto-scroll
      if (!isNearBottom) {
        setIsUserScrolling(true);
      } else {
        // Si l'utilisateur revient en bas, on peut réactiver l'auto-scroll
        setIsUserScrolling(false);
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, []);

  // Scroll vers le bas seulement si l'utilisateur n'a pas scrollé manuellement
  // ET seulement au chargement initial ou quand de nouveaux messages arrivent
  useEffect(() => {
    if (!isUserScrolling && messages.length > 0) {
      // Attendre un peu pour que le DOM soit prêt
      const timeoutId = setTimeout(() => {
        if (messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior: "auto" });
          setShowScrollToBottom(false);
        }
      }, 50);
      return () => clearTimeout(timeoutId);
    }
  }, [messages.length, isUserScrolling]);

  // Fonction pour scroller vers le bas manuellement
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
    setIsUserScrolling(false);
    setShowScrollToBottom(false);
  };

  // Gérer le clavier mobile : scroll automatique quand l'input est focus
  useEffect(() => {
    const handleFocus = () => {
      setTimeout(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "auto", block: "end" });
        setIsUserScrolling(false);
        setShowScrollToBottom(false);
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

  // Appliquer les styles selon les paramètres
  const fontSizeMap = {
    'small': '0.875rem',
    'medium': '1rem',
    'large': '1.125rem'
  };
  
  const chatStyle = {
    '--chat-theme': chatTheme,
    '--chat-wallpaper': chatWallpaper,
    '--font-size': fontSizeMap[fontSize] || '1rem',
  };

  // Classe CSS pour le thème
  const chatThemeClass = `mobile-chat--theme-${chatTheme}`;
  const chatWallpaperClass = `mobile-chat--wallpaper-${chatWallpaper}`;

  return (
    <div className={`mobile-chat ${chatThemeClass} ${chatWallpaperClass}`} style={chatStyle}>
      {/* Header avec bouton retour */}
      {!showSearch ? (
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

          <div className="mobile-chat__actions" style={{ position: 'relative' }}>
          <button 
            className="icon-btn-round" 
            title="Menu"
            onClick={() => setShowMenu(!showMenu)}
          >
            <FiMoreVertical />
          </button>
          
          {showMenu && (
            <div className="mobile-chat__menu">
            <button onClick={() => {
              setShowMenu(false);
              if (onShowContact && conversation?.contacts) {
                // Passer le contact au parent pour navigation
                onShowContact(conversation.contacts);
              } else if (conversation?.contacts) {
                // Si onShowContact n'est pas fourni, afficher localement
                setShowContactDetail(true);
              }
            }}>
              <FiUser /> Afficher le contact
            </button>
            <button onClick={() => {
              setShowMenu(false);
              setShowSearch(true);
            }}>
              <FiSearch /> Rechercher
            </button>
            <button onClick={() => {
              setShowMenu(false);
              // Nouveau groupe - à implémenter plus tard
              alert("Nouveau groupe - Fonctionnalité à venir");
            }}>
              <FiUsers /> Nouveau groupe
            </button>
            <button onClick={() => {
              setShowMenu(false);
              setShowMedia(true);
            }}>
              <FiFileText /> Médias, liens et documents
            </button>
            <button onClick={() => {
              setShowMenu(false);
              setShowChatSettings(true);
            }}>
              <FiSliders /> Thème de la discussion
            </button>
            <button onClick={async () => {
              setShowMenu(false);
              if (!conversation?.id || isTogglingBot) return;
              setIsTogglingBot(true);
              try {
                const newBotMode = !conversation.bot_enabled;
                await toggleConversationBotMode(conversation.id, newBotMode);
                if (onToggleBotMode) {
                  onToggleBotMode(conversation.id, newBotMode);
                }
                if (onRefresh) {
                  onRefresh();
                }
              } catch (error) {
                console.error("Erreur lors du changement de mode:", error);
                alert("Erreur lors du changement de mode");
              } finally {
                setIsTogglingBot(false);
              }
            }}>
              <FiCpu /> {conversation?.bot_enabled ? 'Passer en mode Humain' : 'Passer en mode Bot'}
            </button>
            </div>
          )}
        </div>
      </header>
      ) : (
        <header className="mobile-chat__header mobile-chat__header--search">
          <button className="mobile-chat__back" onClick={() => {
            setShowSearch(false);
            setSearchTerm("");
            setFilteredMessages([]);
          }}>
            <FiArrowLeft />
          </button>
          <div className="mobile-chat__search-input-container">
            <FiSearch className="mobile-chat__search-icon" />
            <input
              type="text"
              className="mobile-chat__search-input"
              placeholder="Rechercher dans la conversation..."
              value={searchTerm}
              onChange={(e) => {
                const term = e.target.value;
                setSearchTerm(term);
                if (term.trim()) {
                  const filtered = messages.filter(msg => 
                    msg.content_text?.toLowerCase().includes(term.toLowerCase())
                  );
                  setFilteredMessages(filtered);
                } else {
                  setFilteredMessages([]);
                }
              }}
              autoFocus
            />
            {searchTerm && (
              <button 
                className="mobile-chat__search-clear"
                onClick={() => {
                  setSearchTerm("");
                  setFilteredMessages([]);
                }}
              >
                <FiX />
              </button>
            )}
          </div>
        </header>
      )}

      {/* Messages */}
      <div className="mobile-chat__messages" ref={messagesContainerRef}>
        {showSearch && searchTerm ? (
          filteredMessages.length === 0 ? (
            <div style={{padding: '20px', textAlign: 'center', color: '#999'}}>
              Aucun résultat trouvé
            </div>
          ) : (
            <>
              <div style={{padding: '0.75rem 1rem', color: '#8696a0', fontSize: '0.875rem', borderBottom: '1px solid rgba(255,255,255,0.1)'}}>
                {filteredMessages.length} résultat{filteredMessages.length > 1 ? 's' : ''} trouvé{filteredMessages.length > 1 ? 's' : ''}
              </div>
              {filteredMessages.map((msg) => {
                if (!mediaVisibility && msg.message_type && ['image', 'video', 'document', 'audio'].includes(msg.message_type)) {
                  return (
                    <div key={msg.id} style={{ padding: '0.5rem 1rem', color: '#8696a0', fontStyle: 'italic', fontSize: '0.875rem' }}>
                      [Média masqué - Activez l'aperçu dans les paramètres]
                    </div>
                  );
                }
                return <MessageBubble key={msg.id} message={msg} conversation={conversation} />;
              })}
            </>
          )
        ) : messages.length === 0 ? (
          <div style={{padding: '20px', textAlign: 'center', color: '#999'}}>
            Aucun message
          </div>
        ) : (
          messages.map((msg) => {
          // Masquer les médias si mediaVisibility est false
          if (!mediaVisibility && msg.message_type && ['image', 'video', 'document', 'audio'].includes(msg.message_type)) {
            return (
              <div key={msg.id} style={{ padding: '0.5rem 1rem', color: '#8696a0', fontStyle: 'italic', fontSize: '0.875rem' }}>
                [Média masqué - Activez l'aperçu dans les paramètres]
              </div>
            );
          }
          return <MessageBubble key={msg.id} message={msg} conversation={conversation} />;
          })
        )}
        <div ref={messagesEndRef} />
        {showScrollToBottom && (
          <button className="mobile-chat__scroll-to-bottom" onClick={scrollToBottom}>
            <FiChevronDown />
          </button>
        )}
      </div>

      {/* Input mobile simplifié */}
      <div className="mobile-chat__input">
        <MobileMessageInput
          conversationId={conversation?.id}
          accountId={conversation?.account_id}
          onSend={handleSendMessage}
          onMediaSent={(optimisticMessage) => {
            // Si null = signal de fin d'envoi -> supprimer optimiste + refresh
            if (!optimisticMessage) {
              setMessages((prev) => prev.filter(msg => !msg._isOptimistic && !msg.id?.startsWith('temp-')));
              refreshMessages();
              return;
            }
            
            // Ajouter le message optimiste
            setMessages((prev) => {
              const exists = prev.some(msg => 
                msg._isOptimistic && 
                msg._optimisticMediaType === optimisticMessage._optimisticMediaType &&
                Math.abs((msg._optimisticTime || 0) - (optimisticMessage._optimisticTime || 0)) < 2000
              );
              if (exists) return prev;
              return sortMessages([...prev, optimisticMessage]);
            });
            
            setTimeout(() => {
              messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
              setIsUserScrolling(false);
              setShowScrollToBottom(false);
            }, 50);
          }}
          messages={messages}
          disabled={false}
        />
      </div>

      {/* Modales */}
      {showContactDetail && conversation?.contacts && (
        <div className="mobile-chat__overlay">
          <div style={{ width: '100%', height: '100%', background: '#0b1014' }}>
            <MobileContactDetail
              contact={conversation.contacts}
              activeAccount={conversation.account_id}
              onBack={() => setShowContactDetail(false)}
            />
          </div>
        </div>
      )}

      {showChatSettings && (
        <div className="mobile-chat__overlay">
          <div style={{ width: '100%', height: '100%', background: '#0b1014' }}>
            <MobileChatSettings
              onBack={() => setShowChatSettings(false)}
            />
          </div>
        </div>
      )}

      {showMedia && (
        <div className="mobile-chat__media-overlay">
          <div className="mobile-chat__media-header">
            <button onClick={() => setShowMedia(false)}>
              <FiArrowLeft />
            </button>
            <h2>Médias, liens et documents</h2>
          </div>
          <div className="mobile-chat__media-content">
            {(() => {
              const mediaMessages = messages.filter(msg => 
                ['image', 'video', 'document', 'audio'].includes(msg.message_type) || 
                (msg.content_text && msg.content_text.match(/https?:\/\//))
              );
              
              if (mediaMessages.length === 0) {
                return (
                  <div style={{ padding: '2rem 1rem', textAlign: 'center', color: '#8696a0' }}>
                    <FiFileText style={{ fontSize: '3rem', marginBottom: '1rem', opacity: 0.5 }} />
                    <p>Aucun média, lien ou document dans cette conversation</p>
                  </div>
                );
              }
              
              return (
                <div className="mobile-chat__media-grid">
                  {mediaMessages.map(msg => (
                    <div key={msg.id} className="mobile-chat__media-item">
                      {msg.message_type && ['image', 'video', 'document', 'audio'].includes(msg.message_type) ? (
                        <div className="mobile-chat__media-item-content">
                          <div className="mobile-chat__media-item-icon">
                            {msg.message_type === 'image' && <FiImage />}
                            {msg.message_type === 'video' && <FiVideo />}
                            {msg.message_type === 'document' && <FiFileText />}
                            {msg.message_type === 'audio' && <FiHeadphones />}
                          </div>
                          <div className="mobile-chat__media-item-info">
                            <div className="mobile-chat__media-item-type">{msg.message_type}</div>
                            {msg.content_text && (
                              <div className="mobile-chat__media-item-text">{msg.content_text}</div>
                            )}
                            <div className="mobile-chat__media-item-time">
                              {(() => {
                                const timestamp = msg.timestamp || msg.created_at;
                                // Interpréter comme UTC si pas de timezone explicite
                                const dateStr = typeof timestamp === 'string' && !timestamp.match(/[Z+-]\d{2}:\d{2}$/) 
                                  ? timestamp + 'Z' 
                                  : timestamp;
                                return new Date(dateStr).toLocaleString('fr-FR', {
                                  timeZone: 'Europe/Paris',
                                  year: 'numeric',
                                  month: '2-digit',
                                  day: '2-digit',
                                  hour: '2-digit',
                                  minute: '2-digit'
                                });
                              })()}
                            </div>
                          </div>
                        </div>
                      ) : msg.content_text && msg.content_text.match(/https?:\/\//) ? (
                        <div className="mobile-chat__media-item-content">
                          <div className="mobile-chat__media-item-icon">
                            <FiLink />
                          </div>
                          <div className="mobile-chat__media-item-info">
                            <div className="mobile-chat__media-item-link">
                              {msg.content_text.match(/https?:\/\/[^\s]+/)?.[0]}
                            </div>
                            <div className="mobile-chat__media-item-time">
                              {(() => {
                                const timestamp = msg.timestamp || msg.created_at;
                                // Interpréter comme UTC si pas de timezone explicite
                                const dateStr = typeof timestamp === 'string' && !timestamp.match(/[Z+-]\d{2}:\d{2}$/) 
                                  ? timestamp + 'Z' 
                                  : timestamp;
                                return new Date(dateStr).toLocaleString('fr-FR', {
                                  timeZone: 'Europe/Paris',
                                  year: 'numeric',
                                  month: '2-digit',
                                  day: '2-digit',
                                  hour: '2-digit',
                                  minute: '2-digit'
                                });
                              })()}
                            </div>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

