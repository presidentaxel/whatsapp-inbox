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

export default function MobileChatWindow({
  conversation,
  onBack,
  onRefresh,
  onShowContact,
  onBotSettingsUpdated,
  conversationInternallyBlocked = false,
}) {
  const [messages, setMessages] = useState([]);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const [oldestMessageTimestamp, setOldestMessageTimestamp] = useState(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const pendingOptimisticRef = useRef(new Map());
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

  const mobileTs = (msg) => {
    const ts = msg.timestamp || msg.created_at;
    if (!ts) return 0;
    if (typeof ts === "number") return ts;
    return new Date(ts).getTime() || 0;
  };

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => mobileTs(a) - mobileTs(b));
  }, []);

  const handleAudioTranscript = useCallback((messageId, text) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, audio_transcript: text } : m))
    );
  }, []);

  const MESSAGES_PAGE_SIZE = 50;

  const refreshMessages = useCallback(() => {
    if (!conversation?.id) return;
    getMessages(conversation.id, { limit: MESSAGES_PAGE_SIZE })
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
    if (!conversation?.id) return;
    setMessages([]);
    setHasMoreMessages(true);
    setOldestMessageTimestamp(null);
    setIsUserScrolling(false);

    getMessages(conversation.id, { limit: MESSAGES_PAGE_SIZE })
      .then((res) => {
        const batch = res.data || [];
        setMessages(sortMessages(batch));
        if (batch.length < MESSAGES_PAGE_SIZE) {
          setHasMoreMessages(false);
        } else {
          const oldest = batch.reduce((min, msg) => {
            const ts = new Date(msg.timestamp || msg.created_at || 0).getTime();
            return !min || ts < min ? ts : min;
          }, null);
          if (oldest) setOldestMessageTimestamp(new Date(oldest).toISOString());
        }
        setTimeout(() => {
          messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
        }, 50);
      })
      .catch(() => {});
  }, [conversation?.id, sortMessages]);

  const loadOlderMessages = useCallback(async () => {
    if (!conversation?.id || !hasMoreMessages || isLoadingMore || !oldestMessageTimestamp) return;
    setIsLoadingMore(true);
    try {
      const container = messagesContainerRef.current;
      const prevScrollHeight = container?.scrollHeight || 0;

      const res = await getMessages(conversation.id, {
        before: oldestMessageTimestamp,
        limit: MESSAGES_PAGE_SIZE,
      });
      const batch = res.data || [];

      if (batch.length === 0) {
        setHasMoreMessages(false);
        return;
      }

      setMessages((prev) => sortMessages([...batch, ...prev]));

      if (batch.length < MESSAGES_PAGE_SIZE) {
        setHasMoreMessages(false);
      }

      const oldest = batch.reduce((min, msg) => {
        const ts = new Date(msg.timestamp || msg.created_at || 0).getTime();
        return !min || ts < min ? ts : min;
      }, null);
      if (oldest) {
        setOldestMessageTimestamp(new Date(oldest).toISOString());
      } else {
        setHasMoreMessages(false);
      }

      requestAnimationFrame(() => {
        if (container) {
          container.scrollTop = container.scrollHeight - prevScrollHeight;
        }
      });
    } catch {
      // Silent
    } finally {
      setIsLoadingMore(false);
    }
  }, [conversation?.id, hasMoreMessages, isLoadingMore, oldestMessageTimestamp, sortMessages]);

  // Polling régulier pour mobile (plus fiable que realtime sur mobile)
  useEffect(() => {
    if (!conversation?.id || conversationInternallyBlocked) return;

    const pollInterval = setInterval(() => {
      refreshMessages();
    }, 30000);

    return () => {
      clearInterval(pollInterval);
    };
  }, [conversation?.id, refreshMessages, conversationInternallyBlocked]);

  // Realtime updates
  useEffect(() => {
    if (!conversation?.id) return;

    const insertSorted = (list, msg) => {
      const ts = mobileTs(msg);
      let i = list.length;
      while (i > 0 && mobileTs(list[i - 1]) > ts) i--;
      const next = [...list];
      next.splice(i, 0, msg);
      return next;
    };

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
          if (conversationInternallyBlocked) return;
          if (incoming.message_type === "reaction" || incoming.is_system === true) return;

          setMessages((prev) => {
            if (prev.some((m) => m.id === incoming.id)) return prev;
            if (incoming.wa_message_id && prev.some((m) => m.wa_message_id === incoming.wa_message_id)) return prev;

            const idx = prev.findLastIndex((m) => m.id?.startsWith("temp-") || m._isOptimistic);
            const cleaned = idx >= 0 && (incoming.direction === "outbound" || incoming.from_me)
              ? prev.filter((_, i) => i !== idx)
              : prev;

            return insertSorted(cleaned, incoming);
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
          if (conversationInternallyBlocked) return;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === updated.id || (updated.wa_message_id && m.wa_message_id === updated.wa_message_id)
                ? updated
                : m
            )
          );
        }
      )
      .subscribe();

    return () => {
      supabaseClient.removeChannel(channel);
    };
  }, [conversation?.id, conversationInternallyBlocked]);

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

  const loadOlderRef = useRef(loadOlderMessages);
  loadOlderRef.current = loadOlderMessages;

  useEffect(() => {
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      const container = messagesContainerRef.current;
      if (!container) return;
      
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
      setShowScrollToBottom(!isNearBottom);
      
      if (!isNearBottom) {
        setIsUserScrolling(true);
      } else {
        setIsUserScrolling(false);
      }

      if (container.scrollTop < 200) {
        loadOlderRef.current();
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
            <button
              type="button"
              disabled={isTogglingBot}
              onClick={async () => {
                setShowMenu(false);
                if (!conversation?.id || isTogglingBot) return;
                setIsTogglingBot(true);
                try {
                  const res = await toggleConversationBotMode(conversation.id, {
                    enabled: false,
                  });
                  const updated = res.data?.conversation;
                  if (updated && onBotSettingsUpdated) onBotSettingsUpdated(updated);
                  onRefresh?.();
                } catch (error) {
                  console.error("Erreur mode humain:", error);
                  alert("Erreur lors du changement de mode");
                } finally {
                  setIsTogglingBot(false);
                }
              }}
            >
              <FiCpu /> Mode humain (pas de bot)
            </button>
            <button
              type="button"
              disabled={isTogglingBot}
              onClick={async () => {
                setShowMenu(false);
                if (!conversation?.id || isTogglingBot) return;
                setIsTogglingBot(true);
                try {
                  const res = await toggleConversationBotMode(conversation.id, {
                    enabled: true,
                    reply_mode: "gemini",
                  });
                  const updated = res.data?.conversation;
                  if (updated && onBotSettingsUpdated) onBotSettingsUpdated(updated);
                  onRefresh?.();
                } catch (error) {
                  console.error("Erreur mode Gemini:", error);
                  alert("Erreur lors du changement de mode");
                } finally {
                  setIsTogglingBot(false);
                }
              }}
            >
              <FiCpu /> Bot Gemini (playbook)
            </button>
            <button
              type="button"
              disabled={isTogglingBot}
              onClick={async () => {
                setShowMenu(false);
                if (!conversation?.id || isTogglingBot) return;
                setIsTogglingBot(true);
                try {
                  const res = await toggleConversationBotMode(conversation.id, {
                    enabled: true,
                    reply_mode: "playground",
                  });
                  const updated = res.data?.conversation;
                  if (updated && onBotSettingsUpdated) onBotSettingsUpdated(updated);
                  onRefresh?.();
                } catch (error) {
                  console.error("Erreur mode Playground:", error);
                  alert("Erreur lors du changement de mode");
                } finally {
                  setIsTogglingBot(false);
                }
              }}
            >
              <FiCpu /> Bot Playground (flux)
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
                if (!mediaVisibility && msg.message_type && ['image', 'video', 'document', 'audio', 'voice'].includes(msg.message_type)) {
                  return (
                    <div key={msg.id} style={{ padding: '0.5rem 1rem', color: '#8696a0', fontStyle: 'italic', fontSize: '0.875rem' }}>
                      [Média masqué - Activez l'aperçu dans les paramètres]
                    </div>
                  );
                }
                return (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    conversation={conversation}
                    onAudioTranscript={handleAudioTranscript}
                  />
                );
              })}
            </>
          )
        ) : messages.length === 0 ? (
          <div style={{padding: '20px', textAlign: 'center', color: '#999'}}>
            Aucun message
          </div>
        ) : (
          <>
          {isLoadingMore && (
            <div style={{ textAlign: "center", padding: "8px 0", color: "#888", fontSize: "0.85rem" }}>
              Chargement...
            </div>
          )}
          {messages.map((msg) => {
          // Masquer les médias si mediaVisibility est false
          if (!mediaVisibility && msg.message_type && ['image', 'video', 'document', 'audio', 'voice'].includes(msg.message_type)) {
            return (
              <div key={msg.id} style={{ padding: '0.5rem 1rem', color: '#8696a0', fontStyle: 'italic', fontSize: '0.875rem' }}>
                [Média masqué - Activez l'aperçu dans les paramètres]
              </div>
            );
          }
          return (
            <MessageBubble
              key={msg.id}
              message={msg}
              conversation={conversation}
              onAudioTranscript={handleAudioTranscript}
            />
          );
          })}
          </>
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
        {conversationInternallyBlocked ? (
          <div className="chat-internal-block-banner" role="status">
            <p>
              Contact <strong>bloqué dans l’app</strong> sur cette ligne — envoi désactivé. Les nouveaux
              messages restent traités côté serveur sans mise à jour de cette vue.
            </p>
          </div>
        ) : (
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
        )}
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
                ['image', 'video', 'document', 'audio', 'voice'].includes(msg.message_type) || 
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
                      {msg.message_type && ['image', 'video', 'document', 'audio', 'voice'].includes(msg.message_type) ? (
                        <div className="mobile-chat__media-item-content">
                          <div className="mobile-chat__media-item-icon">
                            {msg.message_type === 'image' && <FiImage />}
                            {msg.message_type === 'video' && <FiVideo />}
                            {msg.message_type === 'document' && <FiFileText />}
                            {(msg.message_type === 'audio' || msg.message_type === 'voice') && <FiHeadphones />}
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

