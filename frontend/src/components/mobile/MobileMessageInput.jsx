import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { FiSend, FiSmile, FiPlus, FiImage, FiFileText, FiClock } from "react-icons/fi";
import EmojiPicker from "emoji-picker-react";
import { uploadMedia } from "../../api/whatsappApi";
import { sendMediaMessage, sendMessageWithAutoTemplate, sendMessage, getMessagePrice, getAvailableTemplates } from "../../api/messagesApi";
import { useTheme } from "../../hooks/useTheme";

export default function MobileMessageInput({ conversationId, accountId, onSend, onMediaSent, disabled, messages = [] }) {
  const [text, setText] = useState("");
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [isOutsideFreeWindow, setIsOutsideFreeWindow] = useState(false);
  const [templateSent, setTemplateSent] = useState(false);
  const [lastInboundMessageId, setLastInboundMessageId] = useState(null);
  const [useAutoTemplate, setUseAutoTemplate] = useState(true); // Mode auto-template par défaut
  const textareaRef = useRef(null);
  const discussionPrefs = useTheme();
  const previousIsOutsideFreeWindowRef = useRef(false);
  const lastCheckedOutboundMessageIdRef = useRef(null);

  // Fonction helper pour obtenir le timestamp d'un message
  const getMessageTimestamp = useCallback((msg) => {
    const ts = msg.timestamp || msg.created_at;
    if (!ts) return 0;
    if (typeof ts === 'number') return ts;
    const date = new Date(ts);
    return isNaN(date.getTime()) ? 0 : date.getTime();
  }, []);

  // Calculer dynamiquement si un template a été envoyé récemment
  const hasRecentTemplate = useMemo(() => {
    if (!messages || messages.length === 0) {
      return false;
    }
    
    // Trouver le dernier message client (inbound)
    const inboundMessages = messages
      .filter(msg => {
        const isInbound = msg.direction === 'inbound';
        const isNotTemp = !msg.id?.startsWith('temp-');
        const isNotStatus = msg.message_type !== 'status';
        return isInbound && isNotTemp && isNotStatus;
      });
    
    const lastInboundMessage = inboundMessages
      .sort((a, b) => {
        const aTime = getMessageTimestamp(a);
        const bTime = getMessageTimestamp(b);
        return bTime - aTime;
      })[0];
    
    // Trouver le dernier template envoyé (outbound)
    const templateMessages = messages
      .filter(msg => {
        if (msg.direction !== 'outbound') return false;
        if (msg.id?.startsWith('temp-')) return false;
        if (msg.message_type === 'status') return false;
        
        const hasTemplateName = msg.template_name && msg.template_name.trim() !== '';
        const isTemplateType = msg.message_type === 'template';
        const isImageWithTemplate = msg.message_type === 'image' && hasTemplateName;
        const isTextWithTemplate = msg.message_type === 'text' && hasTemplateName;
        
        return hasTemplateName || isTemplateType || isImageWithTemplate || isTextWithTemplate;
      });
    
    const lastTemplateMessage = templateMessages
      .sort((a, b) => {
        const aTime = getMessageTimestamp(a);
        const bTime = getMessageTimestamp(b);
        return bTime - aTime;
      })[0];
    
    if (!lastTemplateMessage) {
      return false;
    }
    
    const lastTemplateTime = getMessageTimestamp(lastTemplateMessage);
    
    if (!lastInboundMessage) {
      return true;
    }
    
    const lastInboundTime = getMessageTimestamp(lastInboundMessage);
    const isRecent = lastTemplateTime > lastInboundTime;
    
    return isRecent;
  }, [messages, getMessageTimestamp]);

  // Détecter les nouveaux messages clients pour réinitialiser templateSent
  useEffect(() => {
    if (!messages || messages.length === 0 || !conversationId) return;
    
    const lastInboundMessage = messages
      .filter(msg => {
        const isInbound = msg.direction === 'inbound';
        const isNotTemp = !msg.id?.startsWith('temp-');
        const isNotStatus = msg.message_type !== 'status';
        return isInbound && isNotTemp && isNotStatus;
      })
      .sort((a, b) => {
        const aTime = getMessageTimestamp(a);
        const bTime = getMessageTimestamp(b);
        return bTime - aTime;
      })[0];
    
    if (lastInboundMessage) {
      const currentLastId = lastInboundMessage.id;
      
      if (lastInboundMessageId !== null && currentLastId !== lastInboundMessageId) {
        console.log("✅ Nouveau message client détecté, réinitialisation de templateSent");
        setTemplateSent(false);
        
        // Vérifier IMMÉDIATEMENT si on est toujours hors fenêtre gratuite
        getMessagePrice(conversationId)
          .then(response => {
            const isFree = response.data?.is_free ?? true;
            setIsOutsideFreeWindow(!isFree);
            previousIsOutsideFreeWindowRef.current = !isFree;
          })
          .catch(error => {
            console.error("Error checking free window after new message:", error);
          });
      }
      
      setLastInboundMessageId(currentLastId);
    }
  }, [messages, lastInboundMessageId, conversationId, getMessageTimestamp]);

  // Réinitialiser les états quand on change de conversation
  useEffect(() => {
    if (!conversationId) {
      setIsOutsideFreeWindow(false);
      setTemplateSent(false);
      setLastInboundMessageId(null);
      lastCheckedOutboundMessageIdRef.current = null;
      previousIsOutsideFreeWindowRef.current = false;
      return;
    }
    
    setLastInboundMessageId(null);
    lastCheckedOutboundMessageIdRef.current = null;
    previousIsOutsideFreeWindowRef.current = false;
  }, [conversationId]);

  // Vérifier si on est hors fenêtre gratuite
  useEffect(() => {
    if (!conversationId) {
      setIsOutsideFreeWindow(false);
      setTemplateSent(false);
      return;
    }

    const checkFreeWindow = async () => {
      try {
        const response = await getMessagePrice(conversationId);
        const isFree = response.data?.is_free ?? true;
        const wasOutsideFreeWindow = previousIsOutsideFreeWindowRef.current;
        const isNowOutsideFreeWindow = !isFree;
        
        setIsOutsideFreeWindow(isNowOutsideFreeWindow);
        previousIsOutsideFreeWindowRef.current = isNowOutsideFreeWindow;
        
        if (isFree) {
          // Si on passe de "hors fenêtre" à "dans la fenêtre", réinitialiser templateSent
          if (wasOutsideFreeWindow && templateSent) {
            console.log("✅ Passage de 'hors fenêtre' à 'dans la fenêtre' (nouveau message client), réinitialisation de templateSent");
            setTemplateSent(false);
          }
        }
      } catch (error) {
        console.error("Error checking free window:", error);
        setIsOutsideFreeWindow(false);
        previousIsOutsideFreeWindowRef.current = false;
      }
    };

    checkFreeWindow();
  }, [conversationId, templateSent]);

  // Auto-resize du textarea
  const handleTextChange = (e) => {
    const value = e.target.value;
    const withEmoji = discussionPrefs?.emojiReplace
      ? value
          .replace(/:\)/g, "😊")
          .replace(/:\("/g, "☹️")
          .replace(/<3/g, "❤️")
          .replace(/;\)/g, "😉")
      : value;
    setText(withEmoji);
    
    // Ajuster la hauteur automatiquement
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  };

  const handleSendClick = async () => {
    if (!text.trim() || disabled || !conversationId) return;
    
    const messageText = text.trim();
    
    // Créer un ID temporaire unique avec timestamp et contenu hash pour faciliter le matching
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const optimisticMessage = {
      id: tempId,
      client_temp_id: tempId, // ID unique pour faciliter le remplacement
      conversation_id: conversationId,
      direction: "outbound",
      content_text: messageText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: "text",
      _isOptimistic: true, // Flag pour identifier facilement les messages optimistes
      _optimisticContent: messageText, // Contenu pour matching
      _optimisticTime: Date.now() // Timestamp pour matching
    };
    
    // Ajouter le message optimiste IMMÉDIATEMENT
    if (onSend) {
      onSend(messageText, false, optimisticMessage);
    }
    
    // Vider le champ de texte immédiatement
    setText("");
    
    // Reset la hauteur du textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    
    try {
      const payload = {
        conversation_id: conversationId,
        content: messageText
      };
      
      // Utiliser l'API appropriée selon l'état de la fenêtre gratuite
      // Si dans la fenêtre gratuite : utiliser sendMessage (gratuit)
      // Si hors fenêtre : utiliser sendMessageWithAutoTemplate (gère les templates automatiquement)
      if (!isOutsideFreeWindow) {
        // Dans la fenêtre gratuite : envoi normal gratuit
        console.log("✅ [MOBILE] Envoi dans la fenêtre gratuite - message gratuit");
        await sendMessage(payload);
      } else {
        // Hors fenêtre gratuite : utiliser auto-template
        console.log("💰 [MOBILE] Envoi hors fenêtre gratuite - utilisation auto-template");
        await sendMessageWithAutoTemplate(payload);
      }
      
      // Le message optimiste sera remplacé automatiquement par le message réel
      // via le webhook Supabase ou le refreshMessages
      
      // Vérifier si on est toujours hors fenêtre gratuite après l'envoi
      getMessagePrice(conversationId)
        .then(response => {
          const isFree = response.data?.is_free ?? true;
          setIsOutsideFreeWindow(!isFree);
          previousIsOutsideFreeWindowRef.current = !isFree;
        })
        .catch(error => {
          console.error("Error checking free window after send:", error);
        });
    } catch (error) {
      console.error("❌ [MOBILE] Erreur lors de l'envoi:", error);
      
      // En cas d'erreur, supprimer le message optimiste spécifique
      if (onSend) {
        onSend("", true, tempId); // Passer l'ID du message optimiste à supprimer
      }
      setText(messageText);
      
      // Afficher les erreurs
      const errorData = error.response?.data;
      if (errorData?.detail?.errors) {
        alert(`Erreur de validation:\n${errorData.detail.errors.join('\n')}`);
      } else if (errorData?.detail?.message) {
        alert(`Erreur: ${errorData.detail.message}`);
      } else if (errorData?.detail) {
        alert(`Erreur: ${errorData.detail}`);
      } else {
        alert(`Erreur lors de l'envoi: ${error.message || "Erreur inconnue"}`);
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      if (discussionPrefs?.enterToSend) {
        if (!e.shiftKey) {
          e.preventDefault();
          handleSendClick();
        }
      } else if (e.metaKey || e.ctrlKey) {
        e.preventDefault();
        handleSendClick();
      }
    }
  };

  const onEmojiClick = (emojiData) => {
    setText(prev => prev + emojiData.emoji);
    setShowEmojiPicker(false);
  };

  const handleFileSelect = async (type) => {
    setShowMenu(false);
    
    // Créer un input file temporaire
    const input = document.createElement('input');
    input.type = 'file';
    
    if (type === 'image') {
      input.accept = 'image/*,video/*';
    } else if (type === 'document') {
      input.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt';
    }
    
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setUploading(true);
      try {
        if (!accountId) {
          throw new Error("Compte non trouvé (account_id manquant)");
        }

        console.log("📤 Upload de fichier:", file.name, file.type, "Account:", accountId);

        // Upload le fichier
        const uploadResult = await uploadMedia(accountId, file);
        
        console.log("✅ Upload réussi:", uploadResult.data);
        
        // Le backend peut retourner soit:
        // {"success": true, "data": {"id": "MEDIA_ID"}} ou {"id": "MEDIA_ID"}
        const mediaId = uploadResult.data?.data?.id || uploadResult.data?.id;
        
        if (!mediaId) {
          console.error("❌ Pas de media_id dans la réponse:", uploadResult.data);
          throw new Error("Aucun ID de média retourné");
        }
        
        console.log("✅ Media ID extrait:", mediaId);
        
        // Déterminer le type de média
        let mediaType = type;
        if (type === 'image' && file.type.startsWith('video/')) {
          mediaType = 'video';
        }
        
        console.log("📨 Envoi message média:", { mediaType, mediaId });
        
        // Créer un aperçu local du fichier pour affichage immédiat
        const fileUrl = URL.createObjectURL(file);
        
        // Créer un ID temporaire unique pour le message optimiste
        const tempId = `temp-media-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const caption = text.trim() || undefined;
        
        // Message optimiste pour le média avec flags pour faciliter le matching
        const tempMediaMessage = {
          id: tempId,
          client_temp_id: tempId,
          conversation_id: conversationId,
          direction: "outbound",
          content_text: caption || `[${mediaType}]`,
          message_type: mediaType,
          status: "pending",
          timestamp: new Date().toISOString(),
          // Stocker l'URL locale temporaire
          _localPreview: fileUrl,
          media_id: mediaId,
          // Flags pour faciliter le matching avec le message réel
          _isOptimistic: true,
          _optimisticMediaId: mediaId, // ID du média pour matching
          _optimisticMediaType: mediaType, // Type de média pour matching
          _optimisticCaption: caption, // Caption pour matching
          _optimisticTime: Date.now() // Timestamp pour matching
        };
        
        console.log("🎨 Affichage aperçu optimiste");
        
        // Appeler le callback pour ajouter le message optimiste
        if (onMediaSent) {
          onMediaSent(tempMediaMessage);
        }
        
        // Envoyer le message média
        await sendMediaMessage({
          conversation_id: conversationId,
          media_id: mediaId,
          media_type: mediaType,
          caption: caption
        });
        
        console.log("✅ Message média envoyé");
        
        // Nettoyer l'URL locale après un délai
        setTimeout(() => {
          URL.revokeObjectURL(fileUrl);
        }, 5000);
        
        setText("");
      } catch (error) {
        console.error("❌ Erreur upload/envoi:", error);
        alert(`Erreur lors de l'envoi du fichier: ${error.message}`);
      } finally {
        setUploading(false);
      }
    };
    
    input.click();
  };

  return (
    <div className="mobile-simple-input">
      {/* Emoji picker */}
      {showEmojiPicker && (
        <div className="mobile-emoji-overlay" onClick={() => setShowEmojiPicker(false)}>
          <div className="mobile-emoji-picker" onClick={(e) => e.stopPropagation()}>
            <EmojiPicker 
              onEmojiClick={onEmojiClick}
              width="100%"
              height="350px"
            />
          </div>
        </div>
      )}

      {/* Menu */}
      {showMenu && (
        <div className="mobile-menu-overlay" onClick={() => setShowMenu(false)}>
          <div className="mobile-menu-sheet" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => handleFileSelect('document')}>
              <FiFileText />
              <span>Document</span>
            </button>
            <button onClick={() => handleFileSelect('image')}>
              <FiImage />
              <span>Photos et vidéos</span>
            </button>
          </div>
        </div>
      )}

      {/* Affichage conditionnel selon l'état de la fenêtre gratuite */}
      {(() => {
        // Si on est dans la fenêtre gratuite : toujours afficher l'input
        if (!isOutsideFreeWindow) {
          return (
            <div className="mobile-input-bar">
              <button
                className="mobile-input-btn"
                onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                disabled={disabled}
              >
                <FiSmile />
              </button>

              <button
                className="mobile-input-btn"
                onClick={() => setShowMenu(!showMenu)}
                disabled={disabled}
              >
                <FiPlus />
              </button>

              <textarea
                ref={textareaRef}
                value={text}
                onChange={handleTextChange}
                onKeyDown={handleKeyDown}
                spellCheck={discussionPrefs?.spellCheck ?? true}
                lang="fr"
                placeholder={
                  discussionPrefs?.enterToSend
                    ? "Message"
                    : "Message (Ctrl+Entrée pour envoyer)"
                }
                disabled={disabled || uploading}
                rows={1}
                className="mobile-input-textarea"
              />

              <button
                className="mobile-input-send"
                onClick={handleSendClick}
                disabled={disabled || !text.trim() || uploading}
              >
                <FiSend />
              </button>
            </div>
          );
        }
        
        // Si on est hors fenêtre gratuite ET mode auto-template : afficher l'input
        if (isOutsideFreeWindow && useAutoTemplate) {
          return (
            <div className="mobile-input-bar">
              <button
                className="mobile-input-btn"
                onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                disabled={disabled}
              >
                <FiSmile />
              </button>

              <button
                className="mobile-input-btn"
                onClick={() => setShowMenu(!showMenu)}
                disabled={disabled}
              >
                <FiPlus />
              </button>

              <textarea
                ref={textareaRef}
                value={text}
                onChange={handleTextChange}
                onKeyDown={handleKeyDown}
                spellCheck={discussionPrefs?.spellCheck ?? true}
                lang="fr"
                placeholder="Message"
                disabled={disabled || uploading}
                rows={1}
                className="mobile-input-textarea"
              />

              <button
                className="mobile-input-send"
                onClick={handleSendClick}
                disabled={disabled || !text.trim() || uploading}
              >
                <FiSend />
              </button>
            </div>
          );
        }
        
        // Si on est hors fenêtre gratuite ET mode manuel ET template récent : afficher message d'attente
        if (isOutsideFreeWindow && !useAutoTemplate && hasRecentTemplate) {
          return (
            <div className="mobile-input-bar mobile-input-bar--waiting">
              <div className="mobile-input-waiting">
                <FiClock style={{ marginRight: '8px' }} />
                <span>En attente d'une réponse client</span>
                <button
                  className="mobile-input-waiting-btn"
                  onClick={() => setUseAutoTemplate(true)}
                  style={{
                    marginLeft: '12px',
                    padding: '4px 12px',
                    background: 'rgba(37, 211, 102, 0.1)',
                    border: '1px solid rgba(37, 211, 102, 0.3)',
                    borderRadius: '4px',
                    color: '#25d366',
                    fontSize: '12px',
                    cursor: 'pointer'
                  }}
                >
                  Activer l'auto-template
                </button>
              </div>
            </div>
          );
        }
        
        // Sinon (hors fenêtre + mode manuel + pas de template récent) : afficher l'input normal
        return (
          <div className="mobile-input-bar">
            <button
              className="mobile-input-btn"
              onClick={() => setShowEmojiPicker(!showEmojiPicker)}
              disabled={disabled}
            >
              <FiSmile />
            </button>

            <button
              className="mobile-input-btn"
              onClick={() => setShowMenu(!showMenu)}
              disabled={disabled}
            >
              <FiPlus />
            </button>

            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleTextChange}
              onKeyDown={handleKeyDown}
              spellCheck={discussionPrefs?.spellCheck ?? true}
              lang="fr"
              placeholder="Message"
              disabled={disabled || uploading}
              rows={1}
              className="mobile-input-textarea"
            />

            <button
              className="mobile-input-send"
              onClick={handleSendClick}
              disabled={disabled || !text.trim() || uploading}
            >
              <FiSend />
            </button>
          </div>
        );
      })()}
    </div>
  );
}

