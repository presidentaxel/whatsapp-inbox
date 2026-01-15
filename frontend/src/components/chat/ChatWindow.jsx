import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiSearch, FiInfo, FiX } from "react-icons/fi";
import { AiFillStar, AiOutlineStar } from "react-icons/ai";
import { MdPushPin } from "react-icons/md";
import { getMessages, sendMessage, editMessage, deleteMessageApi, permanentlyDeleteMessage, checkAndDownloadConversationMedia, pinMessage, unpinMessage } from "../../api/messagesApi";
import { markConversationRead } from "../../api/conversationsApi";
import MessageBubble from "./MessageBubble";
import AdvancedMessageInput from "./AdvancedMessageInput";
import TypingIndicator from "./TypingIndicator";
import MediaGallery from "./MediaGallery";
import { supabaseClient } from "../../api/supabaseClient";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { formatRelativeDateTime } from "../../utils/date";
import { notifyNewMessage, isNotificationEnabledForAccount } from "../../utils/notifications";
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
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [removedMessageIds, setRemovedMessageIds] = useState(new Set());
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const [oldestMessageTimestamp, setOldestMessageTimestamp] = useState(null);

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => {
      // Normaliser les dates - s'assurer qu'elles sont au format ISO string
      const getTimestamp = (msg) => {
        const ts = msg.timestamp || msg.created_at;
        if (!ts) return 0;
        // Si c'est déjà un nombre (timestamp Unix), le convertir
        if (typeof ts === 'number') {
          return ts;
        }
        // Si c'est une string, la parser
        const date = new Date(ts);
        return isNaN(date.getTime()) ? 0 : date.getTime();
      };
      
      const aTs = getTimestamp(a);
      const bTs = getTimestamp(b);
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
      return Promise.resolve();
    }
    
    // Pour le polling, on charge seulement les 100 derniers messages
    // et on met à jour la liste en gardant les anciens messages déjà chargés
    return getMessages(conversationId, { limit: 100 }).then((res) => {
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

      // Mettre à jour les messages : fusionner avec les messages existants
      // en gardant les plus récents et en évitant les doublons
      setMessages((prev) => {
        
        // Créer une Map des nouveaux messages par ID pour accès rapide
        const newMessagesById = new Map();
        const newMessagesByWaId = new Map();
        filtered.forEach(msg => {
          if (msg.id) newMessagesById.set(msg.id, msg);
          if (msg.wa_message_id) newMessagesByWaId.set(msg.wa_message_id, msg);
        });
        
        // Construire la liste finale
        const result = [];
        const seenIds = new Set();
        const seenWaIds = new Set();
        
        // ÉTAPE 1: Supprimer TOUS les messages optimistes (temp-*)
        // Soit s'ils ont un correspondant réel, soit s'ils sont trop anciens (plus de 3 secondes)
        const optimisticToRemove = new Set();
        const now = Date.now();
        
        prev.forEach((msg) => {
          if (msg.id && msg.id.startsWith("temp-")) {
            const msgTime = new Date(msg.timestamp || msg.created_at).getTime();
            const age = now - msgTime;
            
            // Chercher un message réel correspondant
            const msgContent = (msg.content_text || "").trim();
            const matching = filtered.find((newMsg) => {
              const newMsgContent = (newMsg.content_text || "").trim();
              if (msgContent !== newMsgContent || msgContent.length === 0) {
                return false;
              }
              
              const newMsgTime = new Date(newMsg.timestamp || newMsg.created_at).getTime();
              const timeDiff = Math.abs(msgTime - newMsgTime);
              
              // Fenêtre de 10 secondes
              return timeDiff < 10000;
            });
            
            // Supprimer si correspondant trouvé OU si trop ancien (plus de 30 secondes)
            if (matching || age > 30000) {
              optimisticToRemove.add(msg.id);
            }
          }
        });
        
        // ÉTAPE 2: Traiter les messages existants (en excluant les optimistes à supprimer)
        prev.forEach((msg) => {
          // Supprimer tous les messages optimistes identifiés
          if (msg.id && msg.id.startsWith("temp-") && optimisticToRemove.has(msg.id)) {
            return; // Ne pas ajouter ce message optimiste
          }
          
          // Ne JAMAIS garder les messages optimistes qui n'ont pas été identifiés pour suppression
          // (ils seront supprimés au prochain refresh)
          if (msg.id && msg.id.startsWith("temp-")) {
            return; // Ne pas garder les messages optimistes
          }
          
          // Si le message existe dans les nouveaux messages, utiliser la version du serveur
          if (msg.id && newMessagesById.has(msg.id)) {
            const serverVersion = newMessagesById.get(msg.id);
            if (!seenIds.has(serverVersion.id)) {
              result.push(serverVersion);
              seenIds.add(serverVersion.id);
              if (serverVersion.wa_message_id) seenWaIds.add(serverVersion.wa_message_id);
            }
            return; // Ne pas ajouter l'ancienne version
          }
          
          // Si le message existe par wa_message_id dans les nouveaux messages, utiliser la version du serveur
          if (msg.wa_message_id && newMessagesByWaId.has(msg.wa_message_id)) {
            const serverVersion = newMessagesByWaId.get(msg.wa_message_id);
            if (!seenIds.has(serverVersion.id)) {
              result.push(serverVersion);
              seenIds.add(serverVersion.id);
              if (serverVersion.wa_message_id) seenWaIds.add(serverVersion.wa_message_id);
            }
            return; // Ne pas ajouter l'ancienne version
          }
          
          // Garder le message existant s'il n'est pas dans les nouveaux messages
          // Ne JAMAIS garder les messages optimistes (temp-*) - ils sont supprimés automatiquement
          if (msg.id && !seenIds.has(msg.id)) {
            // Supprimer tous les messages optimistes
            if (msg.id.startsWith("temp-")) {
              return; // Ne pas garder les messages optimistes
            }
            result.push(msg);
            seenIds.add(msg.id);
            if (msg.wa_message_id) seenWaIds.add(msg.wa_message_id);
          }
        });
        
        // Ensuite, ajouter les nouveaux messages qui n'ont pas encore été ajoutés
        filtered.forEach((msg) => {
          if (msg.id && !seenIds.has(msg.id)) {
            result.push(msg);
            seenIds.add(msg.id);
            if (msg.wa_message_id) seenWaIds.add(msg.wa_message_id);
          } else if (msg.wa_message_id && !seenWaIds.has(msg.wa_message_id)) {
            result.push(msg);
            if (msg.id) seenIds.add(msg.id);
            seenWaIds.add(msg.wa_message_id);
          }
        });
        
        return sortMessages(result);
      });
      
      return filtered;
    });
  }, [conversationId, sortMessages, profile?.id]);

  // Charger tous les messages au démarrage
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setHasMoreMessages(true);
      setOldestMessageTimestamp(null);
      setIsInitialLoad(false);
      return;
    }
    
    // Réinitialiser l'état
    setMessages([]);
    setHasMoreMessages(true);
    setOldestMessageTimestamp(null);
    setIsInitialLoad(true);
    
    // Vérifier et télécharger les médias manquants en arrière-plan (ne bloque pas)
    // Appelé de manière asynchrone pour ne pas ralentir le chargement des messages
    checkAndDownloadConversationMedia(conversationId)
      .then(() => {
        console.log(`✅ [FRONTEND] Media check started for conversation ${conversationId}`);
      })
      .catch((err) => {
        console.warn(`⚠️ [FRONTEND] Failed to start media check for conversation ${conversationId}:`, err);
        // Ne pas bloquer si ça échoue, c'est juste un bonus
      });
    
    // Charger d'abord les 100 derniers messages pour un affichage immédiat
    const loadMessages = async () => {
      // ÉTAPE 1: Charger les 100 derniers messages immédiatement
      const firstRes = await getMessages(conversationId, { limit: 100 });
      const firstFiltered = firstRes.data.filter((msg) => {
        const type = (msg.message_type || "").toLowerCase();
        if (["reaction", "status"].includes(type)) return false;
        if (profile?.id && Array.isArray(msg.deleted_for_user_ids) && msg.deleted_for_user_ids.includes(profile.id)) {
          return false;
        }
        return true;
      });
      
      // Afficher immédiatement les premiers messages
      setMessages(sortMessages(firstFiltered));
      setIsInitialLoad(false);
      
      // Scroll en bas immédiatement
      setTimeout(() => {
        if (messagesEndRef.current && messagesContainerRef.current) {
          const container = messagesContainerRef.current;
          container.scrollTop = container.scrollHeight;
          messagesEndRef.current.scrollIntoView({ behavior: "auto" });
        }
      }, 50);
      
      // Si on a moins de 100 messages, on a tout chargé
      if (firstFiltered.length < 100) {
        setHasMoreMessages(false);
        return;
      }
      
      // ÉTAPE 2: Charger l'historique plus ancien en arrière-plan progressivement
      let hasMore = true;
      let before = firstFiltered.reduce((oldest, msg) => {
        const ts = msg.timestamp || msg.created_at;
        if (!ts) return oldest;
        const date = new Date(ts);
        if (isNaN(date.getTime())) return oldest;
        const time = date.getTime();
        return !oldest || time < oldest ? time : oldest;
      }, null);
      
      if (before) {
        before = new Date(before).toISOString();
        setOldestMessageTimestamp(before);
      }
      
      let allMessages = [...firstFiltered];
      
      // Charger progressivement l'historique (batch par batch)
      while (hasMore && conversationId && before) {
        const res = await getMessages(conversationId, { before, limit: 100 });
        const filtered = res.data.filter((msg) => {
          const type = (msg.message_type || "").toLowerCase();
          if (["reaction", "status"].includes(type)) return false;
          if (profile?.id && Array.isArray(msg.deleted_for_user_ids) && msg.deleted_for_user_ids.includes(profile.id)) {
            return false;
          }
          return true;
        });
        
        if (filtered.length === 0) {
          hasMore = false;
          break;
        }
        
        // Ajouter les nouveaux messages à la liste complète
        allMessages = [...allMessages, ...filtered];
        
        // Mettre à jour la liste complète (sans bloquer l'UI)
        setMessages(sortMessages(allMessages));
        
        // Trouver le timestamp du message le plus ancien
        const oldest = filtered.reduce((oldest, msg) => {
          const ts = msg.timestamp || msg.created_at;
          if (!ts) return oldest;
          const date = new Date(ts);
          if (isNaN(date.getTime())) return oldest;
          const time = date.getTime();
          return !oldest || time < oldest ? time : oldest;
        }, null);
        
        if (oldest) {
          before = new Date(oldest).toISOString();
          setOldestMessageTimestamp(before);
        } else {
          hasMore = false;
        }
        
        // Si on a moins de 100 messages, on a tout chargé
        if (filtered.length < 100) {
          hasMore = false;
        }
      }
      
      setHasMoreMessages(false);
    };
    
    loadMessages();
  }, [conversationId, sortMessages, profile?.id]);

  // Marquer la conversation comme lue quand elle est ouverte et active
  useEffect(() => {
    if (conversationId && isWindowActive && conversation) {
      // Marquer comme lue après un court délai pour éviter les appels trop fréquents
      const markReadTimeout = setTimeout(() => {
      markConversationRead(conversationId).catch(() => {});
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
      .sort((a, b) => {
        const getTime = (msg) => {
          const ts = msg.timestamp || msg.created_at;
          if (!ts) return 0;
          if (typeof ts === 'number') return ts;
          const date = new Date(ts);
          return isNaN(date.getTime()) ? 0 : date.getTime();
        };
        return getTime(b) - getTime(a);
      })[0];

    if (!lastInboundMessage) {
      setOtherTyping(false);
      return;
    }

    const getMessageTime = (msg) => {
      const ts = msg.timestamp || msg.created_at;
      if (!ts) return 0;
      if (typeof ts === 'number') return ts;
      const date = new Date(ts);
      return isNaN(date.getTime()) ? 0 : date.getTime();
    };
    const messageTime = getMessageTime(lastInboundMessage);
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
          // Vérifier aussi que les notifications sont activées pour ce compte
          const hasFocus = document.hasFocus?.() === true;
          const accountId = conversation?.account_id;
          if (!incoming.from_me && (!isWindowActive || !hasFocus)) {
            // Vérifier que l'utilisateur a accès à ce compte avant d'envoyer une notification
            if (accountId && profile?.permissions?.account_access_levels) {
              const accountAccessLevels = profile.permissions.account_access_levels;
              const accountIdStr = String(accountId);
              const accessLevel = accountAccessLevels[accountId] || 
                                 accountAccessLevels[accountIdStr] ||
                                 accountAccessLevels[accountIdStr.trim()];
              
              // Bloquer explicitement si access_level = 'aucun'
              if (accessLevel === "aucun") {
                return; // Ne pas notifier si l'utilisateur n'a aucun accès
              }
            }
            
            // Vérifier les préférences de notifications pour ce compte avant d'envoyer
            if (accountId && isNotificationEnabledForAccount(accountId, 'messages')) {
              notifyNewMessage(incoming, conversation);
            }
          }
          
          setMessages((prev) => {
            // Ignorer les messages qui ont été supprimés pour renvoi
            if (removedMessageIds.has(incoming.id) || removedMessageIds.has(incoming.wa_message_id)) {
              return prev;
            }
            
            // Vérifier si le message existe déjà (par ID ou wa_message_id)
            const existsById = prev.some((msg) => msg.id === incoming.id);
            const existsByWaId = incoming.wa_message_id && prev.some((msg) => msg.wa_message_id === incoming.wa_message_id);
            
            if (existsById || existsByWaId) {
              // Mettre à jour le message existant avec les données du serveur (qui ont le bon statut)
              const updated = prev.map((msg) => {
                if (msg.id === incoming.id || (incoming.wa_message_id && msg.wa_message_id === incoming.wa_message_id)) {
                  return incoming; // Utiliser la version du serveur qui a le bon statut
                }
                return msg;
              });
              return sortMessages(updated);
            }
            
            // Si c'est un message sortant (qu'on vient d'envoyer), supprimer les messages optimistes correspondants
            if (incoming.direction === "outbound" || incoming.from_me) {
              // Trouver et supprimer tous les messages optimistes qui correspondent
              const cleaned = prev.filter((msg) => {
                // Supprimer les messages optimistes (temp-*) qui correspondent au nouveau message
                if (msg.id && msg.id.startsWith("temp-")) {
                  const msgContent = (msg.content_text || "").trim();
                  const incomingContent = (incoming.content_text || "").trim();
                  const contentMatch = msgContent === incomingContent && msgContent.length > 0;
                  
                  if (contentMatch) {
                    const msgTime = new Date(msg.timestamp || msg.created_at).getTime();
                    const incomingTime = new Date(incoming.timestamp || incoming.created_at).getTime();
                    const timeDiff = Math.abs(msgTime - incomingTime);
                    
                    // Si le contenu correspond et que c'est dans les 30 secondes, c'est le même message
                    if (timeDiff < 30000) {
                      return false; // Supprimer ce message optimiste
                    }
                  }
                }
                // Supprimer aussi les messages réels qui ont le même contenu et timestamp proche (doublons)
                if (msg.id && !msg.id.startsWith("temp-") && msg.direction === "outbound") {
                  const msgContent = (msg.content_text || "").trim();
                  const incomingContent = (incoming.content_text || "").trim();
                  const contentMatch = msgContent === incomingContent && msgContent.length > 0;
                  
                  if (contentMatch) {
                    const msgTime = new Date(msg.timestamp || msg.created_at).getTime();
                    const incomingTime = new Date(incoming.timestamp || incoming.created_at).getTime();
                    const timeDiff = Math.abs(msgTime - incomingTime);
                    
                    // Si le contenu correspond exactement et que c'est dans les 10 secondes, c'est un doublon
                    if (timeDiff < 10000 && msg.id !== incoming.id) {
                      return false; // Supprimer le doublon
                    }
                  }
                }
                return true; // Garder les autres messages
              });
              
              // Ajouter le nouveau message avec le bon statut depuis le serveur
              return sortMessages([...cleaned, incoming]);
            }
            
            // Pour les messages entrants, ajouter simplement
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
          setMessages((prev) => {
            const updatedList = prev.map((msg) => {
              // Mettre à jour par ID
              if (msg.id === updated.id) {
                return updated; // Utiliser la version complète du serveur
              }
              // Mettre à jour par wa_message_id aussi
              if (updated.wa_message_id && msg.wa_message_id === updated.wa_message_id) {
                return updated;
              }
              return msg;
            });
            return sortMessages(updatedList);
          });
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
  }, [conversationId, sortMessages, removedMessageIds]);

  const onSend = async (text, forceRefresh = false, optimisticMessageOverride = null) => {
    if (!conversationId) return;

    // Si forceRefresh est true, juste rafraîchir les messages sans envoyer
    if (forceRefresh || text === "") {
      refreshMessages();
      return;
    }

    // Si un message optimiste est fourni (pour les templates), l'utiliser
    const optimisticMessage = optimisticMessageOverride || {
      id: `temp-${Date.now()}`,
      client_temp_id: `temp-${Date.now()}`,
      conversation_id: conversationId,
      direction: "outbound",
      content_text: text,
      status: "pending",
      timestamp: new Date().toISOString(),
    };
    
    setMessages((prev) => sortMessages([...prev, optimisticMessage]));
    
    // Forcer le scroll en bas quand l'utilisateur envoie un message
    setAutoScroll(true);
    
    // Si c'est un template (optimisticMessageOverride fourni), ne pas envoyer via sendMessage
    // car l'envoi est géré dans handleSendTemplate
    if (optimisticMessageOverride) {
      // Le message optimiste est déjà ajouté, l'envoi sera géré par handleSendTemplate
      return;
    }
    
    try {
      await sendMessage({ conversation_id: conversationId, content: text });
      
      // Le webhook Supabase devrait ajouter le message automatiquement
      // On fait un refresh après un délai pour s'assurer que le statut est à jour
      // et pour récupérer le message si le webhook n'a pas fonctionné
      setTimeout(() => {
        refreshMessages();
      }, 1000);
    } catch (error) {
      // En cas d'erreur, supprimer le message optimiste et rafraîchir immédiatement
      setMessages((prev) => prev.filter((msg) => msg.id !== optimisticMessage.id));
      refreshMessages();
    }
  };

  const resendMessage = async (message) => {
    if (!conversationId || !message) return;
    
    const messageContent = message.content_text;
    if (!messageContent) return;

    const messageId = message.id;
    
    // Supprimer le message échoué de la base de données AVANT de renvoyer
    try {
      if (messageId) {
        await permanentlyDeleteMessage(messageId);
      }
    } catch (error) {
      // Continuer quand même le renvoi même si la suppression échoue
    }
    
    // Supprimer le message échoué de la liste locale immédiatement
    setMessages((prev) => prev.filter((m) => m.id !== messageId));
    
    // Ajouter l'ID à la liste des messages supprimés pour éviter qu'il réapparaisse via webhook
    setRemovedMessageIds((prev) => {
      const newSet = new Set(prev);
      if (messageId) newSet.add(messageId);
      if (message.wa_message_id) newSet.add(message.wa_message_id);
      return newSet;
    });
    
    // Forcer le scroll en bas quand l'utilisateur renvoie un message
    setAutoScroll(true);
    
    // Renvoyer le message
    try {
      await sendMessage({ conversation_id: conversationId, content: messageContent });
      // Ne pas appeler refreshMessages() ici car le nouveau message sera ajouté via le webhook Supabase
    } catch (error) {
      // En cas d'erreur, retirer de la liste des supprimés et rafraîchir
      setRemovedMessageIds((prev) => {
        const newSet = new Set(prev);
        if (messageId) newSet.delete(messageId);
        if (message.wa_message_id) newSet.delete(message.wa_message_id);
        return newSet;
      });
      refreshMessages();
    }
  };

  const subtitle = useMemo(() => {
    if (!conversation) return "";
    return formatPhoneNumber(conversation.client_number);
  }, [conversation]);

  const botEnabled = !!conversation?.bot_enabled;

  const filteredMessages = useMemo(() => {
    let filtered = messages;
    
    // Appliquer la recherche si active
    if (showSearch && searchTerm.trim()) {
      const term = searchTerm.toLowerCase().trim();
      filtered = filtered.filter((m) => {
        const content = (m.content_text || "").toLowerCase();
        return content.includes(term);
      });
    }
    
    // Retourner les messages dans l'ordre chronologique (sans séparer les épinglés)
    return filtered;
  }, [messages, searchTerm, showSearch]);

  // Messages épinglés pour le header
  const pinnedMessages = useMemo(() => {
    return messages.filter((m) => m.is_pinned === true);
  }, [messages]);

  // Références pour scroller vers les messages épinglés
  const messageRefs = useRef({});

  // Fonction pour scroller vers un message spécifique
  const scrollToMessage = useCallback((messageId) => {
    const messageElement = messageRefs.current[messageId];
    if (messageElement && messagesContainerRef.current) {
      const container = messagesContainerRef.current;
      const elementTop = messageElement.offsetTop;
      const containerHeight = container.clientHeight;
      const scrollPosition = elementTop - containerHeight / 2 + messageElement.offsetHeight / 2;
      
      container.scrollTo({
        top: scrollPosition,
        behavior: 'smooth'
      });
      
      // Mettre en surbrillance le message brièvement
      messageElement.style.transition = 'background-color 0.3s ease';
      messageElement.style.backgroundColor = 'rgba(37, 211, 102, 0.2)';
      setTimeout(() => {
        messageElement.style.backgroundColor = '';
        setTimeout(() => {
          messageElement.style.transition = '';
        }, 300);
      }, 2000);
    }
  }, []);

  // Fonction pour vérifier si l'utilisateur est proche du bas
  const isNearBottom = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return false;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    return distanceFromBottom < 120;
  }, []);

  // Fonction pour scroller en bas
  const scrollToBottom = useCallback((behavior = "auto") => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior });
    }
  }, []);

  // Scroller seulement si l'utilisateur est déjà en bas
  useEffect(() => {
    if (!messagesEndRef.current || filteredMessages.length === 0) return;
    
    // Si c'est le chargement initial, toujours scroller en bas
    if (isInitialLoad) {
      // Utiliser plusieurs tentatives pour s'assurer que le scroll se fait après le rendu
      const attemptScroll = () => {
        if (messagesEndRef.current && messagesContainerRef.current) {
          const container = messagesContainerRef.current;
          const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;
          
          if (!isAtBottom) {
            scrollToBottom("auto");
            // Réessayer après un court délai si nécessaire
            setTimeout(() => {
              if (messagesEndRef.current) {
                scrollToBottom("auto");
              }
            }, 100);
          }
          setIsInitialLoad(false);
        }
      };
      
      // Essayer immédiatement
      requestAnimationFrame(attemptScroll);
      // Réessayer après un délai pour s'assurer que le DOM est mis à jour
      setTimeout(attemptScroll, 50);
      return;
    }
    
    // Sinon, scroller seulement si autoScroll est true ET que l'utilisateur est proche du bas
    if (autoScroll && isNearBottom()) {
      requestAnimationFrame(() => {
        scrollToBottom("smooth");
      });
    }
  }, [filteredMessages, autoScroll, isNearBottom, isInitialLoad, scrollToBottom]);

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      // Si l'utilisateur scroll manuellement et n'est plus proche du bas, désactiver autoScroll
      // Cela "fige" le scroll automatique pour cette conversation
      if (distanceFromBottom >= 120) {
        setAutoScroll(false);
      } else {
        // Si l'utilisateur revient en bas, réactiver autoScroll
        setAutoScroll(true);
      }
    };
    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  // Scroller en bas seulement au chargement initial d'une nouvelle conversation
  useEffect(() => {
    // Réinitialiser autoScroll et isInitialLoad au changement de conversation
    setAutoScroll(true);
    setIsInitialLoad(true);
    // Réinitialiser la liste des messages supprimés
    setRemovedMessageIds(new Set());
    
    // Forcer le scroll en bas après le changement de conversation
    // Utiliser plusieurs tentatives pour s'assurer que ça fonctionne
    const scrollAfterChange = () => {
      if (messagesContainerRef.current && messagesEndRef.current) {
        const container = messagesContainerRef.current;
        // Forcer le scroll en bas immédiatement
        container.scrollTop = container.scrollHeight;
        
        // Réessayer après un court délai
        setTimeout(() => {
          if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "auto" });
          }
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        }, 100);
      }
    };
    
    // Essayer après un court délai pour laisser le temps au DOM de se mettre à jour
    setTimeout(scrollAfterChange, 50);
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
            src="/T512xT512.svg" 
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

  const handleMenuAction = async (action, messageOverride = null) => {
    const msg = messageOverride || contextMenu.message;
    if (messageOverride) {
      // Si c'est appelé depuis le header, pas besoin de fermer le menu contextuel
    } else {
      setContextMenu((prev) => ({ ...prev, open: false }));
    }
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

    if (action === "pin") {
      try {
        await pinMessage(msg.id);
        refreshMessages();
      } catch (error) {
        console.error("Erreur lors de l'épinglage:", error);
      }
      return;
    }

    if (action === "unpin") {
      try {
        await unpinMessage(msg.id);
        refreshMessages();
      } catch (error) {
        console.error("Erreur lors du désépinglage:", error);
      }
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
        {/* Header des messages épinglés */}
        {pinnedMessages.length > 0 && (
          <div className="pinned-messages-header">
            {pinnedMessages.map((pinnedMsg) => {
              const preview = (pinnedMsg.content_text || "").trim();
              const previewText = preview.length > 60 ? preview.substring(0, 60) + "..." : preview;
              return (
                <div
                  key={pinnedMsg.id}
                  className="pinned-message-preview"
                  onClick={() => scrollToMessage(pinnedMsg.id)}
                >
                  <div className="pinned-message-preview__icon">
                    <MdPushPin />
                  </div>
                  <div className="pinned-message-preview__content">
                    <div className="pinned-message-preview__text">{previewText || "Message épinglé"}</div>
                    <div className="pinned-message-preview__timestamp">
                      {pinnedMsg.timestamp ? formatRelativeDateTime(pinnedMsg.timestamp) : ""}
                    </div>
                  </div>
                  <button
                    className="pinned-message-preview__unpin"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleMenuAction("unpin", pinnedMsg);
                    }}
                    title="Désépingler"
                  >
                    <FiX />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <div className="messages" ref={messagesContainerRef}>
          {filteredMessages.map((m) => (
            <div
              key={m.id}
              ref={(el) => {
                if (el) messageRefs.current[m.id] = el;
              }}
            >
              <MessageBubble 
                message={m} 
                conversation={conversation}
                onReactionChange={refreshMessages}
                forceReactionOpen={reactionTargetId === m.id}
                onContextMenu={(e) => handleContextMenu(e, m)}
                onResend={resendMessage}
              />
            </div>
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
            
            {/* Bibliothèque de médias */}
            <div className="info-section">
              <h4>Bibliothèque de médias</h4>
              <MediaGallery conversationId={conversationId} mediaType="all" />
            </div>
          </aside>
        )}
      </div>

      <AdvancedMessageInput 
        conversation={conversation}
        onSend={onSend}
        disabled={!canSend || !conversationId}
        accountId={conversation?.account_id}
        messages={messages}
      />

      {contextMenu.open && (
        <div
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={() => handleMenuAction("react")}>Ajouter une réaction</button>
          {contextMenu.message?.is_pinned ? (
            <button onClick={() => handleMenuAction("unpin")}>Désépingler</button>
          ) : (
            <button onClick={() => handleMenuAction("pin")}>Épingler</button>
          )}
          <button onClick={() => handleMenuAction("delete_me")}>Supprimer pour moi</button>
        </div>
      )}
    </div>
  );
}