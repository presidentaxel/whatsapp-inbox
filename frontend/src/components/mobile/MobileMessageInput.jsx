import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { IoSend } from "react-icons/io5";
import { FiPaperclip, FiCamera, FiImage, FiFileText, FiClock, FiGrid, FiLink, FiPhone } from "react-icons/fi";
import { uploadMedia } from "../../api/whatsappApi";
import { sendMediaMessage, sendMessageWithAutoTemplate, sendMessage, getMessagePrice, getAvailableTemplates, sendTemplateMessage } from "../../api/messagesApi";
import { useTheme } from "../../hooks/useTheme";
import TemplateVariablesModal from "../chat/TemplateVariablesModal";
import { hasTemplateVariables } from "../../utils/templateVariables";

export default function MobileMessageInput({ conversationId, accountId, onSend, onMediaSent, disabled, messages = [] }) {
  const [text, setText] = useState("");
  const [showTemplates, setShowTemplates] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [isOutsideFreeWindow, setIsOutsideFreeWindow] = useState(false);
  const [templateSent, setTemplateSent] = useState(false);
  const [lastInboundMessageId, setLastInboundMessageId] = useState(null);
  const [useAutoTemplate, setUseAutoTemplate] = useState(true); // Mode auto-template par défaut
  const [mobileTemplates, setMobileTemplates] = useState([]);
  const [loadingMobileTemplates, setLoadingMobileTemplates] = useState(false);
  const [mobileTemplatesAccountNotConfigured, setMobileTemplatesAccountNotConfigured] = useState(false);
  const [mobilePreviewTemplate, setMobilePreviewTemplate] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [freeWindowDetail, setFreeWindowDetail] = useState(null); // { lastInboundTime, hoursElapsed } pour expliquer "hors fenêtre"
  const [sending, setSending] = useState(false); // évite double envoi (clic rapide / Enter + clic)
  const textareaRef = useRef(null);
  const cameraInputRef = useRef(null);
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
        getMessagePrice(conversationId, true)
          .then(response => {
            const isFree = response.data?.is_free ?? true;
            const lastInbound = response.data?.last_inbound_time ?? null;
            setIsOutsideFreeWindow(!isFree);
            previousIsOutsideFreeWindowRef.current = !isFree;
            setFreeWindowDetail(lastInbound ? {
              lastInboundTime: lastInbound,
              hoursElapsed: lastInbound ? Math.round((Date.now() - new Date(lastInbound).getTime()) / 3600000) : null
            } : null);
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
      setFreeWindowDetail(null);
      lastCheckedOutboundMessageIdRef.current = null;
      previousIsOutsideFreeWindowRef.current = false;
      return;
    }
    
    setLastInboundMessageId(null);
    setFreeWindowDetail(null);
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

    const checkFreeWindow = async (useFresh = false) => {
      try {
        const response = await getMessagePrice(conversationId, useFresh);
        const isFree = response.data?.is_free ?? true;
        const lastInbound = response.data?.last_inbound_time ?? null;
        const wasOutsideFreeWindow = previousIsOutsideFreeWindowRef.current;
        const isNowOutsideFreeWindow = !isFree;
        
        setIsOutsideFreeWindow(isNowOutsideFreeWindow);
        previousIsOutsideFreeWindowRef.current = isNowOutsideFreeWindow;
        setFreeWindowDetail(lastInbound ? {
          lastInboundTime: lastInbound,
          hoursElapsed: lastInbound ? Math.round((Date.now() - new Date(lastInbound).getTime()) / 3600000) : null
        } : null);
        
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

    checkFreeWindow(true); // fresh au chargement pour éviter d'afficher "payant" à tort
  }, [conversationId, templateSent]);

  // Polling: quand on est hors fenêtre gratuite, revérifier toutes les 45s avec fresh pour mettre à jour vite
  useEffect(() => {
    if (!conversationId || !isOutsideFreeWindow) return;
    const intervalMs = 45000;
    const timer = setInterval(async () => {
      try {
        const response = await getMessagePrice(conversationId, true);
        const isFree = response.data?.is_free ?? true;
        if (isFree) {
          const lastInbound = response.data?.last_inbound_time ?? null;
          setIsOutsideFreeWindow(false);
          previousIsOutsideFreeWindowRef.current = false;
          setFreeWindowDetail(lastInbound ? {
            lastInboundTime: lastInbound,
            hoursElapsed: lastInbound ? Math.round((Date.now() - new Date(lastInbound).getTime()) / 3600000) : null
          } : null);
          setTemplateSent((prev) => (prev ? false : prev));
        }
      } catch (_) {}
    }, intervalMs);
    return () => clearInterval(timer);
  }, [conversationId, isOutsideFreeWindow]);

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
    if (!text.trim() || disabled || !conversationId || sending) return;
    setSending(true);

    const messageText = text.trim();
    const tempId = `temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Créer le message optimiste
    const optimisticMessage = {
      id: tempId,
      conversation_id: conversationId,
      direction: "outbound",
      content_text: messageText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: "text",
      _isOptimistic: true,
      _optimisticContent: messageText,
      _optimisticTime: Date.now()
    };
    
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
      
      // Envoyer et récupérer le wa_message_id retourné
      let result;
      if (!isOutsideFreeWindow) {
        result = await sendMessage(payload);
      } else {
        result = await sendMessageWithAutoTemplate(payload);
      }

      const waMessageId = result?.data?.message_id;

      // Signaler que l'envoi est terminé avec le wa_message_id pour matcher
      if (onSend) {
        onSend(null, false, { tempId, waMessageId });
      }
      
      // Vérifier si on est toujours hors fenêtre gratuite après l'envoi
      getMessagePrice(conversationId, true)
        .then(response => {
          const isFree = response.data?.is_free ?? true;
          const lastInbound = response.data?.last_inbound_time ?? null;
          setIsOutsideFreeWindow(!isFree);
          previousIsOutsideFreeWindowRef.current = !isFree;
          setFreeWindowDetail(lastInbound ? {
            lastInboundTime: lastInbound,
            hoursElapsed: lastInbound ? Math.round((Date.now() - new Date(lastInbound).getTime()) / 3600000) : null
          } : null);
        })
        .catch(error => {
          console.error("Error checking free window after send:", error);
        });
    } catch (error) {
      console.error("❌ [MOBILE] Erreur lors de l'envoi:", error);

      // En cas d'erreur, supprimer les messages optimistes
      if (onSend) {
        onSend(null, true, null);
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
    } finally {
      setSending(false);
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

  // Charger les templates quand on ouvre le sheet templates
  useEffect(() => {
    if (showTemplates && conversationId) {
      setLoadingMobileTemplates(true);
      getAvailableTemplates(conversationId)
        .then((res) => {
          const list = res.data?.templates || [];
          setMobileTemplates(list);
          setMobileTemplatesAccountNotConfigured(res.data?.account_not_configured === true);
          if (list.length > 0 && !mobilePreviewTemplate) setMobilePreviewTemplate(list[0]);
        })
        .catch((err) => {
          setMobileTemplates([]);
          setMobileTemplatesAccountNotConfigured(err.response?.data?.detail?.includes?.("account_not_configured"));
        })
        .finally(() => setLoadingMobileTemplates(false));
    } else {
      setMobilePreviewTemplate(null);
    }
  }, [showTemplates, conversationId]);

  const handleSendTemplate = async (template, components = null) => {
    if (disabled || !conversationId) return;
    const hasVariables = hasTemplateVariables(template);
    if (hasVariables && !components) {
      setSelectedTemplate(template);
      setShowTemplateModal(true);
      return;
    }
    const bodyComponent = template.components?.find(c => c.type === "BODY");
    const headerComponent = template.components?.find(c => c.type === "HEADER");
    const footerComponent = template.components?.find(c => c.type === "FOOTER");
    const buttonsComponent = template.components?.find(c => c.type === "BUTTONS");
    const replaceVariablesInText = (text, comps) => {
      if (!text || !comps) return text;
      let result = text;
      comps.forEach(comp => {
        if (comp.parameters) {
          comp.parameters.forEach((param, idx) => {
            if (param.type === "text" && param.text) {
              result = result.replace(new RegExp(`\\{\\{${idx + 1}\\}\\}`, 'g'), param.text);
            }
          });
        }
      });
      return result;
    };
    let templateText = "";
    if (headerComponent?.text && headerComponent.format !== "IMAGE" && headerComponent.format !== "VIDEO" && headerComponent.format !== "DOCUMENT") {
      const headerText = replaceVariablesInText(headerComponent.text, components);
      if (headerText) templateText = headerText + "\n\n";
    }
    if (bodyComponent?.text) {
      templateText += replaceVariablesInText(bodyComponent.text, components);
    } else {
      templateText += template.name;
    }
    if (footerComponent?.text) {
      const footerText = replaceVariablesInText(footerComponent.text, components);
      if (footerText) templateText = templateText ? `${templateText}\n\n${footerText}` : footerText;
    }
    const tempId = `temp-template-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const headerImageUrl = template.header_media_url ||
      (headerComponent?.example?.header_handle?.[0]) ||
      (headerComponent?.format === "IMAGE" && headerComponent?.example?.header_handle?.[0]);
    const optimisticMessage = {
      id: tempId,
      client_temp_id: tempId,
      conversation_id: conversationId,
      direction: "outbound",
      content_text: templateText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: headerImageUrl ? "image" : "template",
      template_name: template.name,
      template_language: template.language || "fr",
      storage_url: headerImageUrl || null,
      _isOptimistic: true,
      _optimisticContent: templateText,
      _optimisticTime: Date.now(),
    };
    if (buttonsComponent?.buttons) {
      optimisticMessage.interactive_data = JSON.stringify({
        type: "button",
        buttons: buttonsComponent.buttons.slice(0, 5).map(btn => ({
          type: btn.type || "QUICK_REPLY",
          text: btn.text || "",
          url: btn.url || "",
          phone_number: btn.phone_number || ""
        }))
      });
    }
    if (components) {
      const variables = {};
      components.forEach(comp => {
        if (comp.parameters) {
          comp.parameters.forEach((param, idx) => {
            if (param.type === "text" && param.text) variables[String(idx + 1)] = param.text;
          });
        }
      });
      if (Object.keys(variables).length > 0) optimisticMessage.template_variables = JSON.stringify(variables);
    }
    if (onSend) onSend(templateText, false, optimisticMessage);
    setShowTemplates(false);
    setMobilePreviewTemplate(null);
    setUploading(true);
    try {
      const payload = { template_name: template.name, language_code: template.language || "fr" };
      if (components && components.length > 0) payload.components = components;
      const result = await sendTemplateMessage(conversationId, payload);
      const waMessageId = result?.data?.message_id;
      if (onSend && tempId && waMessageId) {
        onSend(null, false, { tempId, waMessageId });
      }
      getMessagePrice(conversationId, true).then(r => {
        const isFree = r.data?.is_free ?? true;
        const lastInbound = r.data?.last_inbound_time ?? null;
        setIsOutsideFreeWindow(!isFree);
        setFreeWindowDetail(lastInbound ? {
          lastInboundTime: lastInbound,
          hoursElapsed: Math.round((Date.now() - new Date(lastInbound).getTime()) / 3600000)
        } : null);
      }).catch(() => {});
    } catch (err) {
      alert(`Erreur lors de l'envoi du template: ${err.response?.data?.detail || err.message}`);
      if (onSend) onSend("", true, optimisticMessage.id);
    } finally {
      setUploading(false);
    }
  };

  const handleTemplateModalClose = () => {
    setShowTemplateModal(false);
    setSelectedTemplate(null);
  };

  const handleTemplateModalSend = (components) => {
    if (selectedTemplate) {
      handleSendTemplate(selectedTemplate, components);
      setShowTemplateModal(false);
      setSelectedTemplate(null);
    }
  };

  const handleCameraClick = () => {
    setShowMenu(false);
    cameraInputRef.current?.click();
  };

  const processSelectedFile = async (file, type) => {
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
        
        const caption = text.trim() || undefined;
        const fileUrl = URL.createObjectURL(file);
        
        // Message optimiste avec preview locale
        const optimisticMessage = {
          id: `temp-media-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          conversation_id: conversationId,
          direction: "outbound",
          content_text: caption || `[${mediaType}]`,
          message_type: mediaType,
          status: "pending",
          timestamp: new Date().toISOString(),
          _localPreview: fileUrl,
          _isOptimistic: true,
          _optimisticMediaType: mediaType,
          _optimisticTime: Date.now()
        };
        
        // Afficher le message optimiste IMMÉDIATEMENT
        if (onMediaSent) {
          onMediaSent(optimisticMessage);
        }
        
        // Envoyer le message média
        await sendMediaMessage({
          conversation_id: conversationId,
          media_id: mediaId,
          media_type: mediaType,
          caption: caption
        });
        
        console.log("✅ Message média envoyé");
        
        // Signaler que l'envoi est terminé -> supprime les optimistes et refresh
        if (onMediaSent) {
          onMediaSent(null);
        }
        
        // Nettoyer l'URL locale après un délai
        setTimeout(() => URL.revokeObjectURL(fileUrl), 5000);
        
        setText("");
      } catch (error) {
        console.error("❌ Erreur upload/envoi:", error);
        alert(`Erreur lors de l'envoi du fichier: ${error.message}`);
      } finally {
        setUploading(false);
      }
  };

  const handleFileSelect = (type, fileFromCamera = null) => {
    setShowMenu(false);
    if (fileFromCamera) {
      processSelectedFile(fileFromCamera, type);
      return;
    }
    const input = document.createElement('input');
    input.type = 'file';
    if (type === 'image') input.accept = 'image/*,video/*';
    else if (type === 'document') input.accept = '.pdf,.doc,.docx,.xls,.xlsx,.txt';
    input.onchange = (e) => {
      const file = e.target.files?.[0];
      if (file) processSelectedFile(file, type);
    };
    input.click();
  };

  const renderInputBar = () => (
    <>
      <div className="mobile-input-pill">
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
          disabled={disabled || uploading || sending}
          rows={1}
          className="mobile-input-textarea"
        />

        <button
          type="button"
          className="mobile-input-btn"
          onClick={() => setShowMenu(!showMenu)}
          disabled={disabled}
          title="Joindre"
          aria-label="Joindre un fichier"
        >
          <FiPaperclip />
        </button>
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="mobile-input-camera-hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) handleFileSelect('image', file);
          }}
        />
      </div>

      <button
        type="button"
        className="mobile-input-send"
        onClick={handleSendClick}
          disabled={disabled || !text.trim() || uploading || sending}
        title="Envoyer"
        aria-label="Envoyer"
      >
        <IoSend />
      </button>
    </>
  );

  return (
    <div className="mobile-simple-input">
      {/* Sheet Templates (style WhatsApp) */}
      {showTemplates && (
        <div className="mobile-template-overlay" onClick={() => setShowTemplates(false)}>
          <div className="mobile-template-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-template-sheet__header">
              <span className="mobile-template-sheet__title">Templates</span>
              <button type="button" className="mobile-template-sheet__close" onClick={() => setShowTemplates(false)} aria-label="Fermer">×</button>
            </div>
            {loadingMobileTemplates ? (
              <div className="mobile-template-sheet__loading">Chargement des templates...</div>
            ) : mobileTemplates.length === 0 ? (
              <div className="mobile-template-sheet__empty">
                {mobileTemplatesAccountNotConfigured
                  ? "Connectez votre compte WhatsApp Business (access_token et WABA ID) dans les paramètres du compte pour afficher les templates."
                  : "Aucun template disponible. Créez-en un dans Meta Business Manager."}
              </div>
            ) : (
              <div className="mobile-template-sheet__body">
                <div className="mobile-template-sheet__list">
                  {mobileTemplates.map((t, i) => {
                    const bodyComp = t.components?.find(c => c.type === "BODY");
                    const previewText = bodyComp?.text || t.name;
                    const isSelected = mobilePreviewTemplate?.name === t.name;
                    return (
                      <button
                        type="button"
                        key={i}
                        className={`mobile-template-sheet__item ${isSelected ? "mobile-template-sheet__item--selected" : ""}`}
                        onClick={() => setMobilePreviewTemplate(t)}
                      >
                        <span className="mobile-template-sheet__item-name">{t.name}</span>
                        <span className="mobile-template-sheet__item-preview">{previewText}</span>
                        {hasTemplateVariables(t) && <span className="mobile-template-sheet__item-badge">Variables</span>}
                      </button>
                    );
                  })}
                </div>
                {mobilePreviewTemplate && (
                  <div className="mobile-template-sheet__preview">
                    <div className="mobile-template-sheet__preview-bubble">
                      {(() => {
                        const headerComp = mobilePreviewTemplate.components?.find(c => c.type === "HEADER");
                        const bodyComp = mobilePreviewTemplate.components?.find(c => c.type === "BODY");
                        const footerComp = mobilePreviewTemplate.components?.find(c => c.type === "FOOTER");
                        const buttonsComp = mobilePreviewTemplate.components?.find(c => c.type === "BUTTONS");
                        const headerImg = mobilePreviewTemplate.header_media_url || headerComp?.example?.header_handle?.[0];
                        return (
                          <>
                            {headerImg && <img src={headerImg} alt="" className="mobile-template-sheet__preview-img" />}
                            {headerComp?.text && <div className="mobile-template-sheet__preview-header">{headerComp.text}</div>}
                            <div className="mobile-template-sheet__preview-body">{bodyComp?.text || mobilePreviewTemplate.name}</div>
                            {footerComp?.text && <div className="mobile-template-sheet__preview-footer">{footerComp.text}</div>}
                            {buttonsComp?.buttons?.length > 0 && (
                              <div className="mobile-template-sheet__preview-buttons">
                                {buttonsComp.buttons.map((btn, bi) => (
                                  <span key={bi} className="mobile-template-sheet__preview-btn">
                                    {btn.type === "URL" && <FiLink />}
                                    {btn.type === "PHONE_NUMBER" && <FiPhone />}
                                    {btn.text || btn.url || btn.phone_number}
                                  </span>
                                ))}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                    <button
                      type="button"
                      className="mobile-template-sheet__send"
                      onClick={() => handleSendTemplate(mobilePreviewTemplate)}
                      disabled={disabled || uploading}
                    >
                      <IoSend /> Envoyer
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Menu pièce jointe - au-dessus de l'input, pas par-dessus */}
      {showMenu && (
        <>
          <div className="mobile-attach-overlay" onClick={() => setShowMenu(false)} aria-hidden />
          <div className="mobile-attach-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-attach-grid">
              <button type="button" className="mobile-attach-item mobile-attach-item--gallery" onClick={() => { setShowMenu(false); handleFileSelect('image'); }}>
                <span className="mobile-attach-icon"><FiImage /></span>
                <span>Galerie</span>
              </button>
              <button type="button" className="mobile-attach-item mobile-attach-item--camera" onClick={() => { setShowMenu(false); handleCameraClick(); }}>
                <span className="mobile-attach-icon"><FiCamera /></span>
                <span>Caméra</span>
              </button>
              <button type="button" className="mobile-attach-item mobile-attach-item--template" onClick={() => { setShowMenu(false); setShowTemplates(true); }}>
                <span className="mobile-attach-icon"><FiGrid /></span>
                <span>Template</span>
              </button>
              <button type="button" className="mobile-attach-item mobile-attach-item--document" onClick={() => { setShowMenu(false); handleFileSelect('document'); }}>
                <span className="mobile-attach-icon"><FiFileText /></span>
                <span>Document</span>
              </button>
            </div>
          </div>
        </>
      )}

      <TemplateVariablesModal
        template={selectedTemplate}
        isOpen={showTemplateModal}
        onClose={handleTemplateModalClose}
        onSend={handleTemplateModalSend}
      />

      {/* Affichage conditionnel selon l'état de la fenêtre gratuite */}
      {isOutsideFreeWindow && !useAutoTemplate && hasRecentTemplate ? (
        <div className="mobile-input-bar mobile-input-bar--waiting">
          <div className="mobile-input-waiting">
            <FiClock style={{ marginRight: '8px' }} />
            <span>En attente d'une réponse client</span>
            {freeWindowDetail?.hoursElapsed != null && (
              <span className="mobile-input-waiting-hint" title="La fenêtre gratuite WhatsApp = 24h après le dernier message reçu du client (pas après votre dernier envoi).">
                - Dernier message client il y a {freeWindowDetail.hoursElapsed}h
              </span>
            )}
            <button
              type="button"
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
      ) : (
        <div className="mobile-input-bar">
          {isOutsideFreeWindow && freeWindowDetail?.hoursElapsed != null && (
            <div className="mobile-input-free-window-hint" title="La fenêtre gratuite = 24h après le dernier message reçu du client.">
              Envoi en template - dernier message client il y a {freeWindowDetail.hoursElapsed}h
            </div>
          )}
          {renderInputBar()}
        </div>
      )}
    </div>
  );
}

