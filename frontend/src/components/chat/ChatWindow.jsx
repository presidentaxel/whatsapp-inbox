import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiSearch, FiInfo, FiX } from "react-icons/fi";
import { AiFillStar, AiOutlineStar } from "react-icons/ai";
import { MdPushPin } from "react-icons/md";
import { getMessages, sendMessage, permanentlyDeleteMessage, checkAndDownloadConversationMedia, pinMessage, unpinMessage, addReaction } from "../../api/messagesApi";
import { markConversationRead } from "../../api/conversationsApi";
import { listPlaygroundFlows } from "../../api/playgroundFlowsApi";
import MessageBubble from "./MessageBubble";
import AdvancedMessageInput from "./AdvancedMessageInput";
import TypingIndicator from "./TypingIndicator";
import MediaGallery from "./MediaGallery";
import { supabaseClient } from "../../api/supabaseClient";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { formatRelativeDateTime } from "../../utils/date";
import { useAuth } from "../../context/AuthContext";

// Debounce check-media: 5 min par conversation (réduit appels inutiles ~75%)
const CHECK_MEDIA_DEBOUNCE_MS = 5 * 60 * 1000;
const lastCheckMediaByConversation = new Map();

export default function ChatWindow({
  conversation,
  onFavoriteToggle,
  onBotModeChange,
  onPlaygroundFlowChange,
  onMarkRead,
  canSend = true,
  isWindowActive = true,
  conversationInternallyBlocked = false,
  canUsePlayground = false,
  canUseAgentStudio = false,
}) {
  const { profile } = useAuth();
  const [messages, setMessages] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [showInfo, setShowInfo] = useState(false);
  const [botTogglePending, setBotTogglePending] = useState(false);
  const [reactionTargetId, setReactionTargetId] = useState(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [otherTyping, setOtherTyping] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [removedMessageIds, setRemovedMessageIds] = useState(new Set());
  const removedIdsRef = useRef(removedMessageIds);
  removedIdsRef.current = removedMessageIds;
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const [oldestMessageTimestamp, setOldestMessageTimestamp] = useState(null);
  const [replyingToMessage, setReplyingToMessage] = useState(null);
  const [isRealtimeSubscribed, setIsRealtimeSubscribed] = useState(false);
  const [playgroundFlows, setPlaygroundFlows] = useState([]);
  const [playgroundFlowsLoading, setPlaygroundFlowsLoading] = useState(false);
  const [playgroundFlowPending, setPlaygroundFlowPending] = useState(false);
  const [playgroundFlowError, setPlaygroundFlowError] = useState(null);

  const msgTs = (msg) => {
    const ts = msg.timestamp || msg.created_at;
    if (!ts) return 0;
    if (typeof ts === "number") return ts;
    return new Date(ts).getTime() || 0;
  };

  const sortMessages = useCallback((items) => {
    return [...items].sort((a, b) => msgTs(a) - msgTs(b));
  }, []);

  const handleAudioTranscript = useCallback((messageId, text) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, audio_transcript: text } : m))
    );
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
      // Filtrer réactions/statuts et messages système
      const currentUserId = profile?.id;
      const filtered = res.data.filter((msg) => {
        const type = (msg.message_type || "").toLowerCase();
        if (["reaction", "status"].includes(type)) return false;
        // Exclure les messages système (notifications d'épinglage, etc.)
        if (msg.is_system === true) return false;
        if (currentUserId && Array.isArray(msg.deleted_for_user_ids) && msg.deleted_for_user_ids.includes(currentUserId)) {
          return false;
        }
        // Exclure les messages supprimés visuellement (soft delete)
        if (removedMessageIds.has(msg.id) || (msg.wa_message_id && removedMessageIds.has(msg.wa_message_id))) {
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
        
        // ÉTAPE 2: Traiter les messages existants
        // Realtime remplace l'optimiste par le réel quasi instantanément → toujours retirer les optimistes ici
        prev.forEach((msg) => {
          if (msg.id && msg.id.startsWith("temp-")) {
            return; // Toujours supprimer : realtime a déjà ajouté le message réel
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
          if (msg.id && !seenIds.has(msg.id)) {
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
  }, [conversationId, sortMessages, profile?.id, removedMessageIds]);

  const MESSAGES_PAGE_SIZE = 50;

  const filterMessages = useCallback((data) => {
    return data.filter((msg) => {
      const type = (msg.message_type || "").toLowerCase();
      if (["reaction", "status"].includes(type)) return false;
      if (msg.is_system === true) return false;
      if (profile?.id && Array.isArray(msg.deleted_for_user_ids) && msg.deleted_for_user_ids.includes(profile.id)) {
        return false;
      }
      return true;
    });
  }, [profile?.id]);

  const getOldestTimestamp = useCallback((msgs) => {
    return msgs.reduce((oldest, msg) => {
      const ts = msg.timestamp || msg.created_at;
      if (!ts) return oldest;
      const date = new Date(ts);
      if (isNaN(date.getTime())) return oldest;
      const time = date.getTime();
      return !oldest || time < oldest ? time : oldest;
    }, null);
  }, []);

  // Load only the first page of messages when conversation changes
  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setHasMoreMessages(true);
      setOldestMessageTimestamp(null);
      setIsInitialLoad(false);
      return;
    }
    
    setMessages([]);
    setHasMoreMessages(true);
    setOldestMessageTimestamp(null);
    setIsInitialLoad(true);
    
    const now = Date.now();
    const lastCheck = lastCheckMediaByConversation.get(conversationId) || 0;
    if (now - lastCheck >= CHECK_MEDIA_DEBOUNCE_MS) {
      lastCheckMediaByConversation.set(conversationId, now);
      checkAndDownloadConversationMedia(conversationId)
        .then(() => {})
        .catch((err) => {
          console.warn(`Media check failed for ${conversationId}:`, err);
        });
    }
    
    const loadMessages = async () => {
      const firstRes = await getMessages(conversationId, { limit: MESSAGES_PAGE_SIZE });
      const firstFiltered = filterMessages(firstRes.data);
      
      setMessages(sortMessages(firstFiltered));
      setIsInitialLoad(false);
      
      setTimeout(() => {
        if (messagesEndRef.current && messagesContainerRef.current) {
          const container = messagesContainerRef.current;
          container.scrollTop = container.scrollHeight;
          messagesEndRef.current.scrollIntoView({ behavior: "auto" });
        }
      }, 50);
      
      if (firstFiltered.length < MESSAGES_PAGE_SIZE) {
        setHasMoreMessages(false);
        return;
      }
      
      const oldest = getOldestTimestamp(firstFiltered);
      if (oldest) {
        setOldestMessageTimestamp(new Date(oldest).toISOString());
      }
    };
    
    loadMessages();
  }, [conversationId, sortMessages, filterMessages, getOldestTimestamp]);

  const loadOlderMessages = useCallback(async () => {
    if (!conversationId || !hasMoreMessages || isLoadingMore || !oldestMessageTimestamp) return;
    setIsLoadingMore(true);
    try {
      const container = messagesContainerRef.current;
      const prevScrollHeight = container?.scrollHeight || 0;

      const res = await getMessages(conversationId, {
        before: oldestMessageTimestamp,
        limit: MESSAGES_PAGE_SIZE,
      });
      const filtered = filterMessages(res.data);

      if (filtered.length === 0) {
        setHasMoreMessages(false);
        return;
      }

      setMessages((prev) => sortMessages([...filtered, ...prev]));

      if (filtered.length < MESSAGES_PAGE_SIZE) {
        setHasMoreMessages(false);
      }

      const oldest = getOldestTimestamp(filtered);
      if (oldest) {
        setOldestMessageTimestamp(new Date(oldest).toISOString());
      } else {
        setHasMoreMessages(false);
      }

      // Preserve scroll position after prepending older messages
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
  }, [conversationId, hasMoreMessages, isLoadingMore, oldestMessageTimestamp, filterMessages, getOldestTimestamp, sortMessages]);

  // Marquer la conversation comme lue quand elle est ouverte et active
  const lastMarkedReadRef = useRef(null);
  useEffect(() => {
    if (!conversationId || !isWindowActive || !conversation) return;
    if ((conversation.unread_count || 0) === 0 && lastMarkedReadRef.current === conversationId) return;
    const markReadTimeout = setTimeout(() => {
      lastMarkedReadRef.current = conversationId;
      onMarkRead?.(conversationId);
      markConversationRead(conversationId).catch(() => {});
    }, 1000);
    return () => clearTimeout(markReadTimeout);
  }, [conversationId, isWindowActive, conversation?.unread_count, onMarkRead]);


  useEffect(() => {
    if (!conversationId || !isWindowActive || conversationInternallyBlocked) {
      return;
    }
    let cancelled = false;
    let timeoutId;
    // Safety net: même si le canal est "SUBSCRIBED", des events peuvent ne pas arriver
    // (RLS/publication/filtre). On garde donc un polling court.
    const pollDelay = isRealtimeSubscribed ? 6000 : 2500;
    const poll = async () => {
      await refreshMessages();
      if (!cancelled) {
        timeoutId = setTimeout(poll, pollDelay);
      }
    };
    // Si le realtime est indisponible, lancer rapidement un refresh initial.
    timeoutId = setTimeout(poll, isRealtimeSubscribed ? pollDelay : 250);
    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [
    conversationId,
    refreshMessages,
    isWindowActive,
    conversationInternallyBlocked,
    isRealtimeSubscribed,
  ]);

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
      setIsRealtimeSubscribed(false);
      return undefined;
    }

    const insertSorted = (list, msg) => {
      const ts = msgTs(msg);
      let i = list.length;
      while (i > 0 && msgTs(list[i - 1]) > ts) i--;
      const next = [...list];
      next.splice(i, 0, msg);
      return next;
    };

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
          if (conversationInternallyBlocked) return;
          if (incoming.message_type === "reaction" || incoming.is_system === true) return;

          setMessages((prev) => {
            const removed = removedIdsRef.current;
            if (removed.has(incoming.id) || removed.has(incoming.wa_message_id)) return prev;

            const existsById = prev.some((m) => m.id === incoming.id);
            const existsByWaId = incoming.wa_message_id && prev.some((m) => m.wa_message_id === incoming.wa_message_id);

            if (existsById || existsByWaId) {
              return prev.map((m) =>
                m.id === incoming.id || (incoming.wa_message_id && m.wa_message_id === incoming.wa_message_id)
                  ? incoming
                  : m
              );
            }

            if (incoming.direction === "outbound" || incoming.from_me) {
              const idx = prev.findLastIndex((m) => m.id?.startsWith("temp-"));
              const cleaned = idx >= 0 ? prev.filter((_, i) => i !== idx) : prev;
              return insertSorted(cleaned, incoming);
            }

            return insertSorted(prev, incoming);
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
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "message_reactions",
        },
        (payload) => {
          const msgId = payload.new?.message_id || payload.old?.message_id;
          if (!msgId || conversationInternallyBlocked) return;
          setMessages((prev) => {
            if (prev.some((m) => m.id === msgId || m.wa_message_id === msgId)) {
              refreshMessages();
            }
            return prev;
          });
        }
      )
      .subscribe((status) => {
        if (status === "SUBSCRIBED") {
          setIsRealtimeSubscribed(true);
          return;
        }
        if (
          status === "TIMED_OUT" ||
          status === "CHANNEL_ERROR" ||
          status === "CLOSED"
        ) {
          setIsRealtimeSubscribed(false);
        }
      });

    return () => {
      setIsRealtimeSubscribed(false);
      supabaseClient.removeChannel(channel);
    };
  }, [conversationId, conversationInternallyBlocked, refreshMessages]);

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
    
    // Ajouter reply_to_message si on répond à un message
    if (replyingToMessage) {
      optimisticMessage.reply_to_message = replyingToMessage;
    }
    
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
      const payload = { conversation_id: conversationId, content: text };
      
      // Ajouter reply_to_message_id si on répond à un message
      if (replyingToMessage?.id) {
        payload.reply_to_message_id = replyingToMessage.id;
      }
      
      await sendMessage(payload);
      
      // Annuler la réponse après l'envoi
      if (replyingToMessage) {
        setReplyingToMessage(null);
      }
      
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

  const activeBotSegment = useMemo(() => {
    if (!conversation?.bot_enabled) return "human";
    const mode = String(conversation?.bot_reply_mode || "gemini").toLowerCase();
    if (mode === "playground") return "playground";
    if (mode === "agent") return "agent";
    return "gemini";
  }, [conversation?.bot_enabled, conversation?.bot_reply_mode]);

  const botSegments = useMemo(() => {
    const segs = [{ id: "human", label: "Humain" }];
    const showPlaygroundSuite =
      canUsePlayground ||
      activeBotSegment === "gemini" ||
      activeBotSegment === "playground";
    if (showPlaygroundSuite) {
      segs.push({ id: "gemini", label: "Gemini" }, { id: "playground", label: "Playground" });
    }
    if (canUseAgentStudio || activeBotSegment === "agent") {
      segs.push({ id: "agent", label: "Agent" });
    }
    return segs;
  }, [canUseAgentStudio, canUsePlayground, activeBotSegment]);

  useEffect(() => {
    setPlaygroundFlowError(null);
  }, [conversationId]);

  useEffect(() => {
    const acc = conversation?.account_id;
    if (!acc || activeBotSegment !== "playground") {
      setPlaygroundFlows([]);
      return;
    }
    let cancelled = false;
    setPlaygroundFlowsLoading(true);
    listPlaygroundFlows(acc)
      .then((res) => {
        const rows = Array.isArray(res.data) ? res.data : [];
        if (!cancelled) setPlaygroundFlows(rows);
      })
      .catch(() => {
        if (!cancelled) setPlaygroundFlows([]);
      })
      .finally(() => {
        if (!cancelled) setPlaygroundFlowsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [conversation?.account_id, activeBotSegment]);

  const filteredMessages = useMemo(() => {
    let filtered = messages;
    
    // Exclure les messages système (sécurité supplémentaire)
    filtered = filtered.filter((m) => m.is_system !== true);
    
    // Exclure les messages supprimés visuellement (soft delete)
    filtered = filtered.filter((m) => {
      return !removedMessageIds.has(m.id) && 
             (!m.wa_message_id || !removedMessageIds.has(m.wa_message_id));
    });
    
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
  }, [messages, searchTerm, showSearch, removedMessageIds]);

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

  const loadOlderRef = useRef(loadOlderMessages);
  loadOlderRef.current = loadOlderMessages;

  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceFromBottom >= 120) {
        setAutoScroll(false);
      } else {
        setAutoScroll(true);
      }

      // Load older messages when scrolling near the top
      if (el.scrollTop < 200) {
        loadOlderRef.current();
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


  // Fonctions pour le menu du message
  const handleReply = (message) => {
    setReplyingToMessage(message);
    // Scroller vers le champ de saisie
    setTimeout(() => {
      const input = document.querySelector('.message-input textarea, .message-input input');
      if (input) {
        input.focus();
      }
    }, 100);
  };

  const handleCopy = async (message) => {
    const textToCopy = message.content_text || "";
    try {
      await navigator.clipboard.writeText(textToCopy);
      // Optionnel: afficher une notification
    } catch (error) {
      console.error("Erreur lors de la copie:", error);
      // Fallback pour les navigateurs qui ne supportent pas clipboard API
      const textArea = document.createElement("textarea");
      textArea.value = textToCopy;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
    }
  };

  const handlePin = async (message) => {
    try {
      await pinMessage(message.id);
      refreshMessages();
    } catch (error) {
      console.error("Erreur lors de l'épinglage:", error);
    }
  };

  const handleUnpin = async (message) => {
    try {
      await unpinMessage(message.id);
      refreshMessages();
    } catch (error) {
      console.error("Erreur lors du désépinglage:", error);
    }
  };

  const handleDelete = async (message) => {
    // Soft delete visuel uniquement - ne supprime pas de la base de données
    // Ajouter l'ID du message à la liste des messages supprimés pour cet utilisateur
    setRemovedMessageIds((prev) => {
      const newSet = new Set(prev);
      if (message.id) newSet.add(message.id);
      if (message.wa_message_id) newSet.add(message.wa_message_id);
      return newSet;
    });
    
    // Retirer le message de la liste locale immédiatement
    setMessages((prev) => prev.filter((msg) => {
      return msg.id !== message.id && 
             (!message.wa_message_id || msg.wa_message_id !== message.wa_message_id);
    }));
  };

  const handleReactionChange = async (messageId, emoji) => {
    try {
      await addReaction({
        message_id: messageId,
        emoji: emoji,
      });
      refreshMessages();
    } catch (error) {
      console.error("Erreur lors de l'ajout de la réaction:", error);
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-header">
        <div>
          <div className="chat-title">{displayName}</div>
          <div className="chat-subtitle">{subtitle}</div>
        </div>
        <div className="chat-header-bot-stack">
          <div className="chat-bot-mode">
            <div className="chat-bot-mode__segments" role="group" aria-label="Mode bot conversation">
              {botSegments.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className={`chat-bot-mode__seg ${
                    activeBotSegment === opt.id ? "is-active" : ""
                  }`}
                  disabled={!conversation || botTogglePending}
                  title={
                    opt.id === "gemini"
                      ? "Assistant playbook + Q&A (profil bot)"
                      : opt.id === "agent"
                        ? "Agent Studio — fiche par défaut déployée"
                        : opt.id === "playground"
                          ? "Scénario Playground"
                          : undefined
                  }
                  onClick={async () => {
                    if (!conversation || !onBotModeChange || activeBotSegment === opt.id) return;
                    setBotTogglePending(true);
                    try {
                      if (opt.id === "human") {
                        await onBotModeChange(conversation, { enabled: false });
                      } else {
                        await onBotModeChange(conversation, {
                          enabled: true,
                          reply_mode: opt.id,
                        });
                      }
                    } finally {
                      setBotTogglePending(false);
                    }
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          {activeBotSegment === "playground" && onPlaygroundFlowChange && conversation ? (
            <div className="chat-playground-flow">
              <label
                className="chat-playground-flow__label"
                htmlFor="chat-playground-flow-select"
                title="Scénario utilisé pour cette conversation. Laissez vide pour appliquer le scénario actif du compte (webhook)."
              >
                Scénario
              </label>
              <select
                id="chat-playground-flow-select"
                className="chat-playground-flow__select"
                title="Scénario Playground pour cette conversation"
                aria-label="Scénario Playground pour cette conversation"
                disabled={
                  playgroundFlowsLoading ||
                  playgroundFlowPending ||
                  botTogglePending
                }
                value={conversation.playground_flow_id || ""}
                onChange={async (e) => {
                  const v = e.target.value;
                  const nextId = v === "" ? null : v;
                  const cur = conversation.playground_flow_id || null;
                  if (nextId === cur) return;
                  setPlaygroundFlowError(null);
                  setPlaygroundFlowPending(true);
                  try {
                    await onPlaygroundFlowChange(conversation, nextId);
                  } catch (err) {
                    console.error(err);
                    const msg =
                      err?.response?.data?.detail ||
                      err?.message ||
                      "Impossible de changer le scénario.";
                    setPlaygroundFlowError(
                      typeof msg === "string" ? msg : "Impossible de changer le scénario."
                    );
                  } finally {
                    setPlaygroundFlowPending(false);
                  }
                }}
              >
                <option value="">Scénario du compte (défaut)</option>
                {playgroundFlows.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name || f.id}
                    {f.is_default ? " · défaut" : ""}
                  </option>
                ))}
              </select>
              {playgroundFlowError ? (
                <span className="chat-playground-flow__error" role="alert">
                  {playgroundFlowError}
                </span>
              ) : null}
            </div>
          ) : null}
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
                      handleUnpin(pinnedMsg);
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

        <div className="messages-wrapper">
          <div className="messages" ref={messagesContainerRef}>
            {isLoadingMore && (
              <div style={{ textAlign: "center", padding: "8px 0", color: "#888", fontSize: "0.85rem" }}>
                Chargement des messages plus anciens...
              </div>
            )}
            {!hasMoreMessages && messages.length > MESSAGES_PAGE_SIZE && (
              <div style={{ textAlign: "center", padding: "8px 0", color: "#aaa", fontSize: "0.8rem" }}>
                Début de la conversation
              </div>
            )}
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
                  onReactionChange={(messageId, emoji) => handleReactionChange(messageId, emoji)}
                  forceReactionOpen={reactionTargetId === m.id}
                  onResend={resendMessage}
                  onReply={handleReply}
                  onCopy={handleCopy}
                  onPin={handlePin}
                  onUnpin={handleUnpin}
                  onDelete={handleDelete}
                  onAudioTranscript={handleAudioTranscript}
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
      </div>

      {/* Affichage du message quoted au-dessus de la barre de saisie */}
      {replyingToMessage && !conversationInternallyBlocked && (
        <div className="message-input__reply-preview">
          <div className="message-input__reply-content">
            <div className="message-input__reply-indicator"></div>
            <div className="message-input__reply-info">
              <div className="message-input__reply-author">
                {replyingToMessage.direction === "outbound" ? "Vous" : (displayName || "Contact")}
              </div>
              <div className="message-input__reply-text">
                {replyingToMessage.content_text || "Message"}
              </div>
            </div>
            <button
              className="message-input__reply-close"
              onClick={() => setReplyingToMessage(null)}
              aria-label="Annuler la réponse"
            >
              <FiX />
            </button>
          </div>
        </div>
      )}
      
      {conversationInternallyBlocked ? (
        <div className="chat-internal-block-banner" role="status">
          <p>
            Ce contact est <strong>bloqué dans l’app</strong> sur cette ligne.
          </p>
        </div>
      ) : (
        <AdvancedMessageInput
          conversation={conversation}
          onSend={onSend}
          disabled={!canSend || !conversationId}
          accountId={conversation?.account_id}
          messages={messages}
          replyingToMessage={replyingToMessage}
          onCancelReply={() => setReplyingToMessage(null)}
        />
      )}

    </div>
  );
}