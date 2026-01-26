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
        console.log(`📨 Refreshed messages for conversation ${conversation.id}: ${newMessages.length} messages`);
        if (newMessages.length > 0) {
          const latest = newMessages[newMessages.length - 1];
          console.log(`   Latest message: ${latest.content_text?.substring(0, 50)}... (type: ${latest.message_type}, direction: ${latest.direction})`);
        }
        
          // Fusionner intelligemment avec les messages optimistes existants
          setMessages((prev) => {
            // Garder les messages optimistes qui n'ont pas encore de correspondant réel
            const optimisticMessages = prev.filter(msg => msg._isOptimistic || msg.id?.startsWith('temp-'));
            
            // Pour chaque message optimiste, vérifier s'il a un correspondant dans les nouveaux messages
            const stillOptimistic = optimisticMessages.filter(optMsg => {
              // Pour les messages texte
              if (optMsg._optimisticContent !== undefined) {
                const optContent = optMsg._optimisticContent || optMsg.content_text;
                const optTime = optMsg._optimisticTime || new Date(optMsg.timestamp || optMsg.created_at).getTime();
                
                // Chercher un message réel correspondant (même contenu, temps proche)
                const matching = newMessages.find(realMsg => {
                  const realContent = realMsg.content_text?.trim();
                  const realTime = new Date(realMsg.timestamp || realMsg.created_at).getTime();
                  const timeDiff = Math.abs(realTime - optTime);
                  
                  // Correspondance si même contenu et moins de 10 secondes de différence
                  return realContent === optContent?.trim() && timeDiff < 10000;
                });
                
                // Si on trouve un correspondant, on ne garde pas l'optimiste
                return !matching;
              }
              
              // Pour les messages média
              if (optMsg._optimisticMediaId !== undefined) {
                const optMediaId = optMsg._optimisticMediaId;
                const optMediaType = optMsg._optimisticMediaType;
                const optCaption = optMsg._optimisticCaption;
                const optTime = optMsg._optimisticTime || new Date(optMsg.timestamp || optMsg.created_at).getTime();
                
                // Chercher un message réel correspondant (même media_id ou même type + caption + temps proche)
                const matching = newMessages.find(realMsg => {
                  const realMediaId = realMsg.media_id;
                  const realMediaType = realMsg.message_type;
                  const realCaption = realMsg.content_text?.trim();
                  const realTime = new Date(realMsg.timestamp || realMsg.created_at).getTime();
                  const timeDiff = Math.abs(realTime - optTime);
                  
                  // Correspondance si :
                  // - Même media_id OU
                  // - Même type + même caption (ou les deux sans caption) + moins de 10 secondes
                  const sameMediaId = realMediaId === optMediaId;
                  const sameTypeAndCaption = realMediaType === optMediaType && 
                                           ((!realCaption && !optCaption) || realCaption === optCaption) &&
                                           timeDiff < 10000;
                  
                  return sameMediaId || sameTypeAndCaption;
                });
                
                // Si on trouve un correspondant, on ne garde pas l'optimiste
                return !matching;
              }
              
              // Pour les autres messages optimistes (fallback)
              return true;
            });
            
            // Combiner les nouveaux messages réels avec les optimistes qui n'ont pas encore de correspondant
            const combined = [...newMessages, ...stillOptimistic];
            return sortMessages(combined);
          });
      })
      .catch(error => {
        console.error("❌ Erreur refresh messages:", error);
      });
  }, [conversation?.id, sortMessages]);

  // Fonction pour envoyer un message avec affichage optimiste (instantané)
  // Cette fonction est maintenant appelée par MobileMessageInput qui gère l'envoi
  const handleSendMessage = useCallback((text, forceRefresh = false, optimisticMessageOrId = null) => {
    if (forceRefresh) {
      // Si on passe un ID, supprimer uniquement ce message optimiste
      if (typeof optimisticMessageOrId === 'string' && optimisticMessageOrId.startsWith('temp-')) {
        setMessages((prev) => prev.filter(msg => msg.id !== optimisticMessageOrId && msg.client_temp_id !== optimisticMessageOrId));
      } else {
        // Sinon, supprimer tous les messages optimistes et rafraîchir
        setMessages((prev) => prev.filter(msg => !msg._isOptimistic && !msg.id?.startsWith('temp-')));
        refreshMessages();
      }
      return;
    }

    if (!conversation?.id || !text?.trim()) return;

    // Si un message optimiste est fourni, l'utiliser
    const messageToAdd = optimisticMessageOrId || {
      id: `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      client_temp_id: `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: text.trim(),
      message_type: "text",
      status: "pending",
      timestamp: new Date().toISOString(),
      _isOptimistic: true,
      _optimisticContent: text.trim(),
      _optimisticTime: Date.now()
    };

    // Vérifier qu'on n'ajoute pas un doublon
    setMessages((prev) => {
      // Vérifier si un message optimiste avec le même contenu existe déjà
      const existingOptimistic = prev.find(msg => 
        msg._isOptimistic && 
        msg._optimisticContent === messageToAdd._optimisticContent &&
        Math.abs((msg._optimisticTime || 0) - (messageToAdd._optimisticTime || 0)) < 2000
      );
      
      if (existingOptimistic) {
        console.log("⚠️ Message optimiste déjà présent, on ne l'ajoute pas");
        return prev;
      }
      
      return sortMessages([...prev, messageToAdd]);
    });

    // Scroller vers le bas immédiatement sans animation
    setTimeout(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
      setIsUserScrolling(false);
      setShowScrollToBottom(false);
    }, 50);

    // Rafraîchir après un délai pour obtenir le message réel
    // Le message optimiste reste visible pendant l'envoi
    setTimeout(() => {
      refreshMessages();
    }, 1500);
  }, [conversation?.id, sortMessages, refreshMessages]);

  useEffect(() => {
    refreshMessages();
    // Réinitialiser le scroll quand on charge les messages
    setIsUserScrolling(false);
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
            // Ne pas ajouter si c'est un doublon (même ID)
            const exists = prev.some((msg) => msg.id === incoming.id);
            if (exists) return prev;
            
            // Remplacer les messages optimistes par le message réel
            const incomingContent = incoming.content_text?.trim();
            const incomingTime = new Date(incoming.timestamp || incoming.created_at).getTime();
            
            const withoutTemp = prev.filter(msg => {
              // Garder les messages réels (non optimistes)
              if (!msg._isOptimistic && !msg.id?.startsWith('temp-')) {
                return true;
              }
              
              // Pour les messages texte optimistes
              if (msg._optimisticContent !== undefined) {
                const optContent = msg._optimisticContent || msg.content_text?.trim();
                const optTime = msg._optimisticTime || new Date(msg.timestamp || msg.created_at).getTime();
                
                // Si le contenu correspond et le temps est proche (moins de 10 secondes), c'est le même message
                if (optContent === incomingContent) {
                  const timeDiff = Math.abs(incomingTime - optTime);
                  if (timeDiff < 10000) {
                    // C'est le même message, on supprime l'optimiste
                    console.log("✅ Message texte optimiste remplacé par message réel:", incoming.id);
                    return false;
                  }
                }
              }
              
              // Pour les messages média optimistes
              if (msg._optimisticMediaId !== undefined) {
                const optMediaId = msg._optimisticMediaId;
                const optMediaType = msg._optimisticMediaType;
                const optCaption = msg._optimisticCaption;
                const optTime = msg._optimisticTime || new Date(msg.timestamp || msg.created_at).getTime();
                
                const incomingMediaId = incoming.media_id;
                const incomingMediaType = incoming.message_type;
                const incomingCaption = incoming.content_text?.trim();
                
                // Correspondance si :
                // - Même media_id OU
                // - Même type + même caption (ou les deux sans caption) + moins de 10 secondes
                const sameMediaId = incomingMediaId === optMediaId;
                const sameTypeAndCaption = incomingMediaType === optMediaType && 
                                         ((!incomingCaption && !optCaption) || incomingCaption === optCaption);
                const timeDiff = Math.abs(incomingTime - optTime);
                
                if ((sameMediaId || sameTypeAndCaption) && timeDiff < 10000) {
                  // C'est le même message, on supprime l'optimiste
                  console.log("✅ Message média optimiste remplacé par message réel:", incoming.id);
                  return false;
                }
              }
              
              // Garder les autres messages optimistes qui ne correspondent pas
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
            // Ajouter le message optimiste immédiatement avec vérification de doublon
            if (optimisticMessage) {
              setMessages((prev) => {
                // Vérifier si un message optimiste avec le même media_id existe déjà
                const existingOptimistic = prev.find(msg => 
                  msg._isOptimistic && 
                  msg._optimisticMediaId === optimisticMessage._optimisticMediaId &&
                  msg._optimisticMediaType === optimisticMessage._optimisticMediaType &&
                  Math.abs((msg._optimisticTime || 0) - (optimisticMessage._optimisticTime || 0)) < 2000
                );
                
                if (existingOptimistic) {
                  console.log("⚠️ Message média optimiste déjà présent, on ne l'ajoute pas");
                  return prev;
                }
                
                return sortMessages([...prev, optimisticMessage]);
              });
              
              // Scroller vers le bas immédiatement sans animation
              setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
                setIsUserScrolling(false);
                setShowScrollToBottom(false);
              }, 50);
            }
            
            // Rafraîchir après un délai pour obtenir le message réel
            setTimeout(() => {
              refreshMessages();
            }, 2000);
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

