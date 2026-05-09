import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { FiSend, FiGrid, FiList, FiX, FiHelpCircle, FiSmile, FiImage, FiFileText, FiClock, FiLink, FiPhone, FiEdit, FiDollarSign, FiFile } from "react-icons/fi";
import { uploadMedia } from "../../api/whatsappApi";
import { sendMediaMessage, sendInteractiveMessage, getMessagePrice, getAvailableTemplates, sendTemplateMessage, sendMessageWithAutoTemplate, sendMessage } from "../../api/messagesApi";
import EmojiPicker from "emoji-picker-react";
import { useTheme } from "../../hooks/useTheme";
import TemplateVariablesModal from "./TemplateVariablesModal";
import { hasTemplateVariables } from "../../utils/templateVariables";
import { devLog } from "../../utils/devLog";
import { platformAlert } from "../../platform/platformDialogs";

export default function AdvancedMessageInput({ conversation, onSend, disabled = false, editingMessage = null, onCancelEdit, accountId = null, messages = [], replyingToMessage = null, onCancelReply = null }) {
  const [text, setText] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [mode, setMode] = useState("text"); // text, media, buttons, list, template
  const [uploading, setUploading] = useState(false);
  const [priceInfo, setPriceInfo] = useState(null);
  const [loadingPrice, setLoadingPrice] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [isOutsideFreeWindow, setIsOutsideFreeWindow] = useState(false);
  const [templateSent, setTemplateSent] = useState(false); // État pour savoir si un template a été envoyé récemment
  const [lastInboundMessageId, setLastInboundMessageId] = useState(null); // Pour détecter les nouveaux messages clients
  const lastCheckedOutboundMessageIdRef = useRef(null); // Pour éviter de vérifier plusieurs fois le même message sortant
  const previousIsOutsideFreeWindowRef = useRef(false); // Pour suivre l'état précédent de isOutsideFreeWindow
  const [selectedTemplate, setSelectedTemplate] = useState(null); // Template sélectionné pour remplir les variables
  const [showTemplateModal, setShowTemplateModal] = useState(false); // Afficher la modale de variables
  const [forceTemplateMode, setForceTemplateMode] = useState(false); // État pour forcer l'affichage des templates
  const [previewTemplate, setPreviewTemplate] = useState(null); // Template sélectionné pour l'aperçu dans le menu latéral
  const [menuTemplates, setMenuTemplates] = useState([]); // Templates pour le menu (différents des templates hors fenêtre)
  const [loadingMenuTemplates, setLoadingMenuTemplates] = useState(false); // Chargement des templates du menu
  const [menuTemplatesAccountNotConfigured, setMenuTemplatesAccountNotConfigured] = useState(false); // Compte WhatsApp non configuré
  const [menuPreviewTemplate, setMenuPreviewTemplate] = useState(null); // Template sélectionné dans le menu
  const [useAutoTemplate, setUseAutoTemplate] = useState(true); // Utiliser le système auto-template (true) ou sélection manuelle (false)
  const discussionPrefs = useTheme();
  
  const menuRef = useRef(null);
  const emojiRef = useRef(null);
  const mediaInputRef = useRef(null); // Input pour photos et vidéos
  const documentInputRef = useRef(null); // Input pour documents
  const textAreaRef = useRef(null);
  
  // States pour boutons interactifs
  const [buttons, setButtons] = useState([{ id: "", title: "" }]);
  const [headerText, setHeaderText] = useState("");
  const [footerText, setFooterText] = useState("");
  
  // States pour listes
  const [listSections, setListSections] = useState([
    { title: "", rows: [{ id: "", title: "", description: "" }] }
  ]);
  const [buttonText, setButtonText] = useState("Voir les options");

  const replaceEmojiShortcuts = (value) => {
    if (!discussionPrefs?.emojiReplace) return value;
    return value
      .replace(/:\)/g, "😊")
      .replace(/:\("/g, "☹️")
      .replace(/<3/g, "❤️")
      .replace(/;\)/g, "😉");
  };

  // Fermer les menus quand on clique dehors
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
      if (emojiRef.current && !emojiRef.current.contains(event.target)) {
        setShowEmojiPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    // Pré-remplir en mode édition
    if (editingMessage) {
      setText(editingMessage.content_text || "");
    }
  }, [editingMessage]);

  // Fonction helper pour obtenir le timestamp d'un message de manière robuste
  const getMessageTimestamp = useCallback((msg) => {
    const ts = msg.timestamp || msg.created_at;
    if (!ts) return 0;
    if (typeof ts === 'number') return ts;
    const date = new Date(ts);
    return isNaN(date.getTime()) ? 0 : date.getTime();
  }, []);

  // Calculer dynamiquement si un template a été envoyé récemment
  // Un template est considéré comme "récent" s'il a été envoyé et qu'on attend une réponse client
  // On affiche "en attente de réponse client" si :
  // 1. Un template a été envoyé (avec ou sans boutons)
  // 2. Le template est plus récent que le dernier message client (ou il n'y a pas de message client)
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
    // Un template est identifié par :
    // - template_name présent (peu importe le message_type)
    // - message_type === 'template'
    // - message_type === 'image' avec template_name (template avec image dans le header)
    const templateMessages = messages
      .filter(msg => {
        if (msg.direction !== 'outbound') return false;
        if (msg.id?.startsWith('temp-')) return false;
        if (msg.message_type === 'status') return false;
        
        // Vérifier si c'est un template
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

    // Si il n'y a pas de message client, considérer le template comme récent
    // (on attend toujours une réponse si aucun message client n'est arrivé)
    if (!lastInboundMessage) {
      return true;
    }
    
    const lastInboundTime = getMessageTimestamp(lastInboundMessage);
    
    // Un template est "récent" s'il a été envoyé après le dernier message client
    // Cela signifie qu'on attend toujours une réponse du client
    const isRecent = lastTemplateTime > lastInboundTime;
    
    return isRecent;
  }, [messages, getMessageTimestamp]);

  // Détecter les nouveaux messages clients pour réinitialiser templateSent si nécessaire
  // ET vérifier immédiatement si on est toujours hors fenêtre gratuite
  useEffect(() => {
    if (!messages || messages.length === 0 || !conversation?.id) return;
    
    // Trouver le dernier message entrant (client)
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
      
      // Si c'est un nouveau message client (différent du précédent), réinitialiser templateSent
      // Car un nouveau message client signifie qu'on peut repasser en mode normal
      if (lastInboundMessageId !== null && currentLastId !== lastInboundMessageId) {
        devLog("✅ Nouveau message client détecté, réinitialisation de templateSent et vérification immédiate de la fenêtre gratuite");
        setTemplateSent(false);
        setForceTemplateMode(false); // Réinitialiser aussi forceTemplateMode
        
        // Vérifier IMMÉDIATEMENT si on est toujours hors fenêtre gratuite
        // Cela permet une transition plus rapide vers la barre de saisie normale
        getMessagePrice(conversation.id, true)
          .then(response => {
            const isFree = response.data?.is_free ?? true;
            setIsOutsideFreeWindow(!isFree);
            previousIsOutsideFreeWindowRef.current = !isFree;
            
            // Si on est maintenant dans la fenêtre gratuite, charger les templates n'est plus nécessaire
            if (isFree) {
              setTemplates([]);
            }
          })
          .catch(error => {
            console.error("Error checking free window after new message:", error);
          });
      }
      
      setLastInboundMessageId(currentLastId);
    }
  }, [messages, lastInboundMessageId, conversation?.id, getMessageTimestamp]);

  // Réinitialiser les états quand on change de conversation
  useEffect(() => {
    if (!conversation?.id) {
      setIsOutsideFreeWindow(false);
      setTemplates([]);
      setTemplateSent(false);
      setLastInboundMessageId(null);
      setForceTemplateMode(false);
      setPreviewTemplate(null);
      setMenuTemplates([]);
      setMenuPreviewTemplate(null);
      setUseAutoTemplate(true); // Réinitialiser à true par défaut
      lastCheckedOutboundMessageIdRef.current = null;
      previousIsOutsideFreeWindowRef.current = false;
      return;
    }
    
    // Réinitialiser lastInboundMessageId et les refs quand on change de conversation
    setLastInboundMessageId(null);
    setForceTemplateMode(false);
    setPreviewTemplate(null);
    setMenuTemplates([]);
    setMenuPreviewTemplate(null);
    // Ne pas réinitialiser useAutoTemplate - garder le choix de l'utilisateur
    lastCheckedOutboundMessageIdRef.current = null;
    previousIsOutsideFreeWindowRef.current = false;
  }, [conversation?.id]);

  // Vérifier si on est hors fenêtre gratuite et charger les templates si nécessaire
  // Cette vérification se fait au changement de conversation, pas à chaque nouveau message
  // (les nouveaux messages sont gérés dans le useEffect de détection des messages clients)
  useEffect(() => {
    if (!conversation?.id) {
      setIsOutsideFreeWindow(false);
      setTemplates([]);
      setTemplateSent(false);
      return;
    }

    const checkFreeWindow = async (useFresh = false) => {
      try {
        const response = await getMessagePrice(conversation.id, useFresh);
        const isFree = response.data?.is_free ?? true;
        const wasOutsideFreeWindow = previousIsOutsideFreeWindowRef.current;
        const isNowOutsideFreeWindow = !isFree;
        
        setIsOutsideFreeWindow(isNowOutsideFreeWindow);
        previousIsOutsideFreeWindowRef.current = isNowOutsideFreeWindow;
        
        // Si hors fenêtre, charger les templates
        if (!isFree) {
          setLoadingTemplates(true);
          try {
            const templatesResponse = await getAvailableTemplates(conversation.id);
            const newTemplates = templatesResponse.data?.templates || [];
            setTemplates(newTemplates);
            // Réinitialiser le preview si le template sélectionné n'est plus dans la liste
            // Sinon, sélectionner automatiquement le premier template si aucun n'est sélectionné
            if (previewTemplate && !newTemplates.find(t => t.name === previewTemplate.name)) {
              setPreviewTemplate(newTemplates.length > 0 ? newTemplates[0] : null);
            } else if (!previewTemplate && newTemplates.length > 0) {
              setPreviewTemplate(newTemplates[0]);
            }
          } catch (error) {
            console.error("Error loading templates:", error);
            setTemplates([]);
            setPreviewTemplate(null);
          } finally {
            setLoadingTemplates(false);
          }
          
          // Si on est toujours hors fenêtre, NE PAS réinitialiser templateSent
          // templateSent sera réinitialisé uniquement par :
          // 1. Un nouveau message client (dans le useEffect de détection)
          // 2. Un message libre réussi (dans handleSend ou le useEffect de détection des messages sortants)
        } else {
          setTemplates([]);
          // Si on passe de "hors fenêtre" à "dans la fenêtre", c'est qu'un nouveau message client est arrivé
          // Dans ce cas, on peut réinitialiser templateSent
          if (wasOutsideFreeWindow && templateSent) {
            devLog("✅ Passage de 'hors fenêtre' à 'dans la fenêtre' (nouveau message client), réinitialisation de templateSent");
            setTemplateSent(false);
          }
        }
      } catch (error) {
        console.error("Error checking free window:", error);
        setIsOutsideFreeWindow(false);
        previousIsOutsideFreeWindowRef.current = false;
        setTemplates([]);
        // Ne pas réinitialiser templateSent en cas d'erreur si on était en mode template
      }
    };

    checkFreeWindow(true); // fresh au chargement pour éviter d'afficher "payant" à tort
  }, [conversation?.id]);

  // Polling: quand on est hors fenêtre gratuite, revérifier toutes les 45s avec fresh pour mettre à jour vite
  useEffect(() => {
    if (!conversation?.id || !isOutsideFreeWindow) return;
    const intervalMs = 45000;
    const timer = setInterval(async () => {
      try {
        const response = await getMessagePrice(conversation.id, true);
        const isFree = response.data?.is_free ?? true;
        if (isFree) {
          setIsOutsideFreeWindow(false);
          previousIsOutsideFreeWindowRef.current = false;
          setTemplates([]);
          setTemplateSent((prev) => (prev ? false : prev));
        }
      } catch (_) {}
    }, intervalMs);
    return () => clearInterval(timer);
  }, [conversation?.id, isOutsideFreeWindow]);

  // Charger le prix du message quand le texte change
  useEffect(() => {
    if (!conversation?.id || !text.trim() || mode !== "text" || isOutsideFreeWindow) {
      setPriceInfo(null);
      return;
    }

    const loadPrice = async () => {
      setLoadingPrice(true);
      try {
        const response = await getMessagePrice(conversation.id);
        setPriceInfo(response.data);
      } catch (error) {
        console.error("Error loading price:", error);
        setPriceInfo(null);
      } finally {
        setLoadingPrice(false);
      }
    };

    // Debounce pour éviter trop de requêtes
    const timeoutId = setTimeout(loadPrice, 500);
    return () => clearTimeout(timeoutId);
  }, [text, conversation?.id, mode, isOutsideFreeWindow]);

  const handleSend = async () => {
    if (disabled || !text.trim() || !conversation?.id) return;
    
    const messageText = text;
    
    // Créer le message optimiste IMMÉDIATEMENT avant l'appel API pour un affichage instantané
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage = {
      id: tempId,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: messageText,
      status: "pending", // Statut par défaut, sera mis à jour par le serveur
      timestamp: new Date().toISOString(),
      message_type: "text"
    };
    
    // Ajouter le message optimiste IMMÉDIATEMENT
    if (onSend) {
      onSend(messageText, false, optimisticMessage);
    }
    
    // Vider le champ de texte immédiatement
    setText("");
    setShowAdvanced(false);
    setMode("text");
    
    // Annuler la réponse après l'envoi
    if (replyingToMessage && onCancelReply) {
      onCancelReply();
    }
    
    try {
      // Appeler l'API en arrière-plan
      // Le message réel remplacera l'optimiste quand il arrivera via le webhook
      const payload = {
        conversation_id: conversation.id,
        content: messageText
      };
      
      // Ajouter reply_to_message_id si on répond à un message
      if (replyingToMessage?.id) {
        payload.reply_to_message_id = replyingToMessage.id;
        optimisticMessage.reply_to_message = replyingToMessage;
      }
      
      // Utiliser l'API appropriée selon l'état de la fenêtre gratuite
      // Si dans la fenêtre gratuite : utiliser sendMessage (gratuit)
      // Si hors fenêtre : utiliser sendMessageWithAutoTemplate (gère les templates automatiquement)
      if (!isOutsideFreeWindow) {
        // Dans la fenêtre gratuite : envoi normal gratuit
        devLog("✅ [DESKTOP] Envoi dans la fenêtre gratuite - message gratuit");
        await sendMessage(payload);
      } else {
        // Hors fenêtre gratuite : utiliser auto-template
        devLog("💰 [DESKTOP] Envoi hors fenêtre gratuite - utilisation auto-template");
        await sendMessageWithAutoTemplate(payload);
      }
      
      // Le message optimiste sera remplacé automatiquement par le message réel
      // via le webhook Supabase ou le refreshMessages
    } catch (error) {
      console.error("❌ [FRONTEND] Erreur lors de l'envoi:", error);
      console.error("❌ [FRONTEND] Détails de l'erreur:", {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status,
        url: error.config?.url
      });
      
      // En cas d'erreur, supprimer le message optimiste et remettre le texte
      // Le refreshMessages supprimera automatiquement le message optimiste
      if (onSend) {
        onSend("", true); // Force refresh pour supprimer le message optimiste
      }
      setText(messageText);
      
      // Afficher les erreurs de validation si disponibles
      const errorData = error.response?.data;
      if (errorData?.detail?.errors) {
        console.error("❌ [FRONTEND] Erreurs de validation:", errorData.detail.errors);
        await platformAlert(`Erreur de validation:\n${errorData.detail.errors.join('\n')}`);
      } else if (errorData?.detail?.message) {
        console.error("❌ [FRONTEND] Message d'erreur:", errorData.detail.message);
        await platformAlert(`Erreur: ${errorData.detail.message}`);
      } else if (errorData?.detail) {
        // Si detail est une string directement
        console.error("❌ [FRONTEND] Erreur (string):", errorData.detail);
        await platformAlert(`Erreur: ${errorData.detail}`);
      } else {
        console.error("❌ [FRONTEND] Erreur inconnue:", error);
        await platformAlert(`Erreur lors de l'envoi: ${error.message || "Erreur inconnue"}`);
      }
    }
  };

  const handleSendTemplate = async (template, components = null) => {
    devLog("🎯 [FRONTEND] handleSendTemplate appelé", { 
      disabled, 
      conversationId: conversation?.id, 
      template: template.name,
      hasComponents: !!components,
      templateComponents: template.components
    });
    
    if (disabled || !conversation?.id) {
      devLog("❌ [FRONTEND] handleSendTemplate annulé - disabled:", disabled, "conversationId:", conversation?.id);
      return;
    }
    
    // Vérifier si le template a des variables
    const hasVariables = hasTemplateVariables(template);
    devLog("🔍 [FRONTEND] Vérification variables:", { 
      templateName: template.name, 
      hasVariables, 
      components: template.components,
      hasComponentsParam: !!components
    });
    
    // Si le template a des variables et qu'on n'a pas encore de components, ouvrir la modale
    if (hasVariables && !components) {
      devLog("📝 [FRONTEND] Template avec variables détecté, ouverture de la modale");
      setSelectedTemplate(template);
      setShowTemplateModal(true);
      return;
    }
    
    // Construire le texte du template avec variables remplies pour l'affichage optimiste
    const bodyComponent = template.components?.find(c => c.type === "BODY");
    const headerComponent = template.components?.find(c => c.type === "HEADER");
    const footerComponent = template.components?.find(c => c.type === "FOOTER");
    const buttonsComponent = template.components?.find(c => c.type === "BUTTONS");
    
    // Fonction pour remplacer les variables dans un texte
    const replaceVariablesInText = (text, components) => {
      if (!text || !components) return text;
      let result = text;
      components.forEach(comp => {
        if (comp.parameters) {
          comp.parameters.forEach((param, idx) => {
            if (param.type === "text" && param.text) {
              // Remplacer {{idx+1}} par la valeur
              result = result.replace(new RegExp(`\\{\\{${idx + 1}\\}\\}`, 'g'), param.text);
            }
          });
        }
      });
      return result;
    };
    
    let templateText = "";
    
    // Header (texte seulement, pas les images)
    if (headerComponent?.text && headerComponent.format !== "IMAGE" && headerComponent.format !== "VIDEO" && headerComponent.format !== "DOCUMENT") {
      const headerText = replaceVariablesInText(headerComponent.text, components);
      if (headerText) {
        templateText = headerText + "\n\n";
      }
    }
    
    // Body
    if (bodyComponent?.text) {
      const bodyText = replaceVariablesInText(bodyComponent.text, components);
      templateText += bodyText;
    } else {
      templateText += template.name;
    }
    
    // Footer
    if (footerComponent?.text) {
      const footerText = replaceVariablesInText(footerComponent.text, components);
      if (footerText) {
        templateText = templateText ? `${templateText}\n\n${footerText}` : footerText;
      }
    }
    
    // Créer un message optimiste
    const tempId = `temp-template-${Date.now()}`;
    const headerImageUrl = template.header_media_url || 
      (headerComponent?.example?.header_handle?.[0]) ||
      (headerComponent?.format === "IMAGE" && headerComponent?.example?.header_handle?.[0]);
    
    const optimisticMessage = {
      id: tempId,
      client_temp_id: tempId,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: templateText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: headerImageUrl ? "image" : "template",
      template_name: template.name,
      template_language: template.language || "fr",
      storage_url: headerImageUrl || null,
    };
    
    // Ajouter les boutons dans interactive_data si présents
    if (buttonsComponent?.buttons) {
      const buttons = buttonsComponent.buttons.slice(0, 5).map(btn => ({
        type: btn.type || "QUICK_REPLY",
        text: btn.text || "",
        url: btn.url || "",
        phone_number: btn.phone_number || ""
      }));
      optimisticMessage.interactive_data = JSON.stringify({
        type: "button",
        buttons: buttons
      });
    }
    
    // Ajouter les variables si components fournis
    if (components) {
      const variables = {};
      components.forEach(comp => {
        if (comp.parameters) {
          comp.parameters.forEach((param, idx) => {
            if (param.type === "text" && param.text) {
              variables[String(idx + 1)] = param.text;
            }
          });
        }
      });
      if (Object.keys(variables).length > 0) {
        optimisticMessage.template_variables = JSON.stringify(variables);
      }
    }
    
    // Ajouter le message optimiste à la liste
    if (onSend) {
      // Utiliser une fonction callback pour ajouter le message optimiste
      // On va passer le message optimiste via un paramètre spécial
      onSend(templateText, false, optimisticMessage);
    }
    
    setUploading(true);
    try {
      const payload = {
        template_name: template.name,
        language_code: template.language || "fr"
      };
      
      // Ajouter les components si fournis (variables remplies)
      if (components && components.length > 0) {
        payload.components = components;
      }
      
      devLog("📤 [FRONTEND] ========== ENVOI TEMPLATE ==========");
      devLog("📤 [FRONTEND] Template info:", {
        conversationId: conversation.id,
        templateName: template.name,
        languageCode: template.language || "fr",
        componentsCount: components?.length || 0,
        hasHeaderImage: template.header_media_url ? true : false,
        headerMediaType: template.header_media_type || null,
        headerMediaUrl: template.header_media_url || null
      });
      devLog("📤 [FRONTEND] Payload complet:", JSON.stringify(payload, null, 2));
      devLog("📤 [FRONTEND] Components détaillés:", components?.map((c, idx) => ({
        index: idx,
        type: c.type,
        format: c.format || null,
        parametersCount: c.parameters?.length || 0,
        parameters: c.parameters?.map((p, pIdx) => ({
          index: pIdx,
          type: p.type,
          text: p.text?.substring(0, 100) + (p.text?.length > 100 ? '...' : ''),
          textLength: p.text?.length || 0,
          image: p.image || null,
          video: p.video || null,
          document: p.document || null
        }))
      })));
      devLog("📤 [FRONTEND] ====================================");
      
      const response = await sendTemplateMessage(conversation.id, payload);
      devLog("✅ [FRONTEND] Template envoyé avec succès:", response);
      
      // Réinitialiser forceTemplateMode et previewTemplate car un nouveau template a été envoyé
      setForceTemplateMode(false);
      setPreviewTemplate(null);
      
      // Attendre un peu pour que le message soit sauvegardé dans la base
      // Puis rafraîchir plusieurs fois pour s'assurer que le message est bien chargé
      // Rafraîchir immédiatement les messages pour détecter le nouveau template
      // Le webhook Supabase devrait ajouter le message rapidement
      onSend?.("", true); // Refresh immédiat
      
      // Vérifier si on est toujours hors fenêtre gratuite
      // Après l'envoi du premier template, on devrait pouvoir envoyer des messages normaux
      // Faire cette vérification en parallèle pour ne pas bloquer
      getMessagePrice(conversation.id, true)
        .then(response => {
          const isFree = response.data?.is_free ?? true;
          setIsOutsideFreeWindow(!isFree);
          previousIsOutsideFreeWindowRef.current = !isFree;
        })
        .catch(error => {
          console.error("Error checking free window after template:", error);
        });
      
      // Un seul refresh supplémentaire après un court délai pour s'assurer que tout est à jour
      setTimeout(() => {
        onSend?.("", true);
      }, 500);
    } catch (error) {
      console.error("❌ [FRONTEND] Erreur lors de l'envoi du template:", error);
      console.error("❌ [FRONTEND] Détails de l'erreur:", {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status,
        url: error.config?.url
      });
      await platformAlert(`Erreur lors de l'envoi du template: ${error.response?.data?.detail || error.message}`);
      // Supprimer le message optimiste en cas d'erreur
      if (onSend) {
        onSend("", true); // Force refresh pour supprimer le message optimiste
      }
    } finally {
      setUploading(false);
    }
  };
  
  const handleTemplateModalSend = (components) => {
    if (selectedTemplate) {
      handleSendTemplate(selectedTemplate, components);
    }
    setShowTemplateModal(false);
    setSelectedTemplate(null);
  };
  
  const handleTemplateModalClose = () => {
    setShowTemplateModal(false);
    setSelectedTemplate(null);
  };

  // Ajuster la hauteur du textarea pour suivre le contenu
  useEffect(() => {
    if (!textAreaRef.current) return;
    const el = textAreaRef.current;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const handleMediaSend = async (file) => {
    devLog("handleMediaSend called with file:", file?.name, file?.type);
    
    if (!conversation?.id) {
      console.error("No conversation ID");
      await platformAlert("Aucune conversation sélectionnée");
      return;
    }
    
    // Récupérer l'account_id depuis la prop ou depuis la conversation
    const accountIdToUse = accountId || conversation?.account_id;
    devLog("Account ID to use:", accountIdToUse, "from prop:", accountId, "from conversation:", conversation?.account_id);
    
    if (!accountIdToUse) {
      console.error("Conversation object:", conversation);
      console.error("AccountId prop:", accountId);
      await platformAlert("Impossible de déterminer le compte WhatsApp. Veuillez recharger la page.");
      return;
    }
    
    setUploading(true);
    setShowMenu(false);
    try {
      devLog("Uploading media to account:", accountIdToUse);
      // Upload le fichier
      const uploadResult = await uploadMedia(accountIdToUse, file);
      devLog("Upload result:", uploadResult);
      const mediaId = uploadResult.data?.id;
      
      if (!mediaId) {
        console.error("No media ID returned from upload");
        await platformAlert("Erreur lors de l'upload du fichier. Aucun ID média retourné.");
        return;
      }

      devLog("Media uploaded successfully, media ID:", mediaId);

      // Détermine le type de média
      let mediaType = "document";
      if (file.type.startsWith("image/")) mediaType = "image";
      else if (file.type.startsWith("audio/")) mediaType = "audio";
      else if (file.type.startsWith("video/")) mediaType = "video";

      devLog("Sending media message, type:", mediaType, "conversation:", conversation.id);

      // Envoie le message via notre API backend qui gère le stockage
      await sendMediaMessage({
        conversation_id: conversation.id,
        media_type: mediaType,
        media_id: mediaId,
        caption: text || undefined
      });

      devLog("Media message sent successfully");
      setText("");
      setShowAdvanced(false);
      setMode("text");
      onSend?.(""); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi média:", error);
      console.error("Error details:", error.response?.data || error.message);
      await platformAlert(`Erreur lors de l'envoi du fichier: ${error.response?.data?.detail || error.message || "Erreur inconnue"}`);
    } finally {
      setUploading(false);
    }
  };

  const handleEmojiClick = (emojiData) => {
    setText(text + emojiData.emoji);
    setShowEmojiPicker(false);
  };

  const openMediaPicker = () => {
    devLog("openMediaPicker called for photos/videos");
    setShowMenu(false);
    if (mediaInputRef.current) {
      devLog("Clicking media input");
      mediaInputRef.current.click();
    } else {
      console.error("mediaInputRef.current is null");
    }
  };

  const openDocumentPicker = () => {
    devLog("openDocumentPicker called");
    setShowMenu(false);
    if (documentInputRef.current) {
      devLog("Clicking document input");
      documentInputRef.current.click();
    } else {
      console.error("documentInputRef.current is null");
    }
  };

  const openMode = async (newMode) => {
    setMode(newMode);
    setShowMenu(false);
    setShowAdvanced(true);
    
    // Si on ouvre le mode template, charger les templates
    if (newMode === "template" && conversation?.id) {
      setLoadingMenuTemplates(true);
      setMenuTemplatesAccountNotConfigured(false);
      try {
        const templatesResponse = await getAvailableTemplates(conversation.id);
        const newTemplates = templatesResponse.data?.templates || [];
        const notConfigured = templatesResponse.data?.account_not_configured === true;
        setMenuTemplates(newTemplates);
        setMenuTemplatesAccountNotConfigured(notConfigured);
        // Sélectionner automatiquement le premier template si disponible
        if (newTemplates.length > 0 && !menuPreviewTemplate) {
          setMenuPreviewTemplate(newTemplates[0]);
        }
      } catch (error) {
        const notConfigured = error.response?.data?.detail?.includes?.("account_not_configured");
        setMenuTemplates([]);
        setMenuTemplatesAccountNotConfigured(notConfigured);
        if (!notConfigured) console.error("Error loading templates for menu:", error);
      } finally {
        setLoadingMenuTemplates(false);
      }
    }
  };

  const handleButtonsSend = async () => {
    devLog("🔘 [FRONTEND] handleButtonsSend appelé", { mode, text, buttons, headerText, footerText });
    if (!conversation?.id || !text.trim()) {
      console.warn("🔘 [FRONTEND] handleButtonsSend annulé: conversation ou text manquant");
      return;
    }
    
    const validButtons = buttons.filter(b => b.id && b.title).slice(0, 3);
    devLog("🔘 [FRONTEND] Boutons valides:", validButtons);
    if (validButtons.length === 0) {
      await platformAlert("Ajoutez au moins un bouton");
      return;
    }

    // Construire le texte complet pour l'affichage optimiste
    let fullText = "";
    if (headerText) {
      fullText += `${headerText}\n\n`;
    }
    fullText += text;
    if (footerText) {
      fullText += `\n\n${footerText}`;
    }
    
    // Créer un message optimiste
    const tempId = `temp-buttons-${Date.now()}`;
    const optimisticMessage = {
      id: tempId,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: fullText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: "interactive",
      interactive_data: JSON.stringify({
        type: "button",
        header: headerText || null,
        body: text,
        footer: footerText || null,
        buttons: validButtons.map(btn => ({
          type: "QUICK_REPLY",
          text: btn.title
        }))
      })
    };
    
    // Ajouter le message optimiste immédiatement
    if (onSend) {
      onSend(fullText, false, optimisticMessage);
    }

    // Reset immédiatement pour une meilleure UX
    setText("");
    setButtons([{ id: "", title: "" }]);
    setHeaderText("");
    setFooterText("");
    setShowAdvanced(false);
    setMode("text");

    try {
      const payload = {
        conversation_id: conversation.id,
        interactive_type: "button",
        body_text: text,
        buttons: validButtons,
        header_text: headerText || undefined,
        footer_text: footerText || undefined
      };
      devLog("🔘 [FRONTEND] Envoi sendInteractiveMessage avec payload:", payload);
      const response = await sendInteractiveMessage(payload);
      devLog("🔘 [FRONTEND] Réponse reçue:", response);

      // Le message optimiste sera remplacé automatiquement par le message réel
      // via le webhook Supabase ou le refreshMessages
      onSend?.("", true); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi boutons:", error);
      console.error("Détails de l'erreur:", {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      
      // En cas d'erreur, supprimer le message optimiste et remettre le texte
      if (onSend) {
        onSend("", true); // Force refresh pour supprimer le message optimiste
      }
      setText(fullText);
      
      // Afficher les erreurs de validation si disponibles
      const errorData = error.response?.data;
      if (errorData?.detail?.errors) {
        await platformAlert(`Erreur de validation:\n${errorData.detail.errors.join('\n')}`);
      } else if (errorData?.detail?.message) {
        await platformAlert(`Erreur: ${errorData.detail.message}`);
      } else if (errorData?.detail) {
        await platformAlert(`Erreur: ${errorData.detail}`);
      } else {
        await platformAlert(`Erreur lors de l'envoi: ${error.message || "Erreur inconnue"}`);
      }
    }
  };

  const handleListSend = async () => {
    devLog("📋 [FRONTEND] handleListSend appelé", { mode, text, listSections, headerText, footerText, buttonText });
    if (!conversation?.id || !text.trim()) {
      console.warn("📋 [FRONTEND] handleListSend annulé: conversation ou text manquant");
      return;
    }
    
    const validSections = listSections
      .map(section => ({
        title: section.title,
        rows: section.rows.filter(r => r.id && r.title)
      }))
      .filter(s => s.rows.length > 0);
    
    devLog("📋 [FRONTEND] Sections valides:", validSections);
    if (validSections.length === 0) {
      await platformAlert("Ajoutez au moins une section avec des lignes");
      return;
    }

    // Construire le texte complet pour l'affichage optimiste
    let fullText = "";
    if (headerText) {
      fullText += `${headerText}\n\n`;
    }
    fullText += text;
    if (footerText) {
      fullText += `\n\n${footerText}`;
    }
    
    // Créer un message optimiste
    const tempId = `temp-list-${Date.now()}`;
    const optimisticMessage = {
      id: tempId,
      conversation_id: conversation.id,
      direction: "outbound",
      content_text: fullText,
      status: "pending",
      timestamp: new Date().toISOString(),
      message_type: "interactive",
      interactive_data: JSON.stringify({
        type: "list",
        header: headerText || null,
        body: text,
        footer: footerText || null,
        button_text: buttonText,
        sections: validSections
      })
    };
    
    // Ajouter le message optimiste immédiatement
    if (onSend) {
      onSend(fullText, false, optimisticMessage);
    }

    // Reset immédiatement pour une meilleure UX
    setText("");
    setListSections([{ title: "", rows: [{ id: "", title: "", description: "" }] }]);
    setHeaderText("");
    setFooterText("");
    setButtonText("Voir les options");
    setShowAdvanced(false);
    setMode("text");

    try {
      const payload = {
        conversation_id: conversation.id,
        interactive_type: "list",
        body_text: text,
        button_text: buttonText,
        sections: validSections,
        header_text: headerText || undefined,
        footer_text: footerText || undefined
      };
      devLog("📋 [FRONTEND] Envoi sendInteractiveMessage avec payload:", payload);
      const response = await sendInteractiveMessage(payload);
      devLog("📋 [FRONTEND] Réponse reçue:", response);

      // Le message optimiste sera remplacé automatiquement par le message réel
      // via le webhook Supabase ou le refreshMessages
      onSend?.("", true); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi liste:", error);
      console.error("Détails de l'erreur:", {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      });
      
      // En cas d'erreur, supprimer le message optimiste et remettre le texte
      if (onSend) {
        onSend("", true); // Force refresh pour supprimer le message optimiste
      }
      setText(fullText);
      
      // Afficher les erreurs de validation si disponibles
      const errorData = error.response?.data;
      if (errorData?.detail?.errors) {
        await platformAlert(`Erreur de validation:\n${errorData.detail.errors.join('\n')}`);
      } else if (errorData?.detail?.message) {
        await platformAlert(`Erreur: ${errorData.detail.message}`);
      } else if (errorData?.detail) {
        await platformAlert(`Erreur: ${errorData.detail}`);
      } else {
        await platformAlert(`Erreur lors de l'envoi: ${error.message || "Erreur inconnue"}`);
      }
    }
  };

  const addButton = () => {
    if (buttons.length < 3) {
      setButtons([...buttons, { id: "", title: "" }]);
    }
  };

  const updateButton = (index, field, value) => {
    const newButtons = [...buttons];
    newButtons[index][field] = value;
    setButtons(newButtons);
  };

  const removeButton = (index) => {
    setButtons(buttons.filter((_, i) => i !== index));
  };

  const addSection = () => {
    setListSections([...listSections, { title: "", rows: [{ id: "", title: "", description: "" }] }]);
  };

  const updateSection = (sectionIndex, field, value) => {
    const newSections = [...listSections];
    newSections[sectionIndex][field] = value;
    setListSections(newSections);
  };

  const addRow = (sectionIndex) => {
    const newSections = [...listSections];
    newSections[sectionIndex].rows.push({ id: "", title: "", description: "" });
    setListSections(newSections);
  };

  const updateRow = (sectionIndex, rowIndex, field, value) => {
    const newSections = [...listSections];
    newSections[sectionIndex].rows[rowIndex][field] = value;
    setListSections(newSections);
  };

  const removeRow = (sectionIndex, rowIndex) => {
    const newSections = [...listSections];
    newSections[sectionIndex].rows = newSections[sectionIndex].rows.filter((_, i) => i !== rowIndex);
    setListSections(newSections);
  };

  // Rendu de l'aperçu pour les boutons
  const ButtonsPreview = () => (
    <div className="message-preview">
      <div className="message-preview__title">Aperçu du message</div>
      <div className="message-preview__container">
        <div className="message-preview__bubble">
          {headerText && <div className="message-preview__header">{headerText}</div>}
          <div className="message-preview__body">{text || "Votre texte principal..."}</div>
          {footerText && <div className="message-preview__footer">{footerText}</div>}
        </div>
        <div className="message-preview__buttons">
          {buttons.filter(b => b.title).map((btn, i) => (
            <button key={i} className="message-preview__button">{btn.title}</button>
          ))}
          {buttons.filter(b => b.title).length === 0 && (
            <button className="message-preview__button message-preview__button--placeholder">Bouton 1</button>
          )}
        </div>
      </div>
      <div className="message-preview__note">
        ℹ️ Les boutons permettent à l'utilisateur de répondre rapidement. La réponse apparaîtra comme un message normal dans le chat.
      </div>
    </div>
  );

  // Rendu de l'aperçu pour les listes
  const ListPreview = () => (
    <div className="message-preview">
      <div className="message-preview__title">Aperçu du message</div>
      <div className="message-preview__container">
        <div className="message-preview__bubble">
          {headerText && <div className="message-preview__header">{headerText}</div>}
          <div className="message-preview__body">{text || "Votre texte principal..."}</div>
          {footerText && <div className="message-preview__footer">{footerText}</div>}
        </div>
        <button className="message-preview__list-button">
          <FiList /> {buttonText}
        </button>
      </div>
      <div className="message-preview__note">
        ℹ️ L'utilisateur pourra choisir une option dans la liste. Sa sélection apparaîtra comme un message.
      </div>
    </div>
  );

  return (
    <div className={`input-area-advanced ${disabled ? "disabled" : ""}`}>
      {showAdvanced && (
        <div className="advanced-options">
          <div className="advanced-header">
            <h3 className="advanced-title">
              {mode === "buttons" ? "Message avec boutons" : mode === "list" ? "Message avec liste" : mode === "template" ? "Envoyer un template" : "Options"}
            </h3>
            <button 
              className="advanced-close"
              onClick={() => {
                setShowAdvanced(false);
                // Réinitialiser les états du template menu si on était en mode template
                if (mode === "template") {
                  setMenuPreviewTemplate(null);
                  setMenuTemplates([]);
                }
              }}
              title="Fermer"
            >
              <FiX />
            </button>
          </div>

          <div className="advanced-content">

            {mode === "buttons" && (
              <div className="interactive-config">
                <div className="interactive-form">
                  <div className="form-section">
                    <label className="form-label">
                      En-tête (optionnel)
                      <span className="tooltip" title="Titre qui apparaît en haut du message">
                        <FiHelpCircle />
                      </span>
                    </label>
                    <input
                      type="text"
                      placeholder="Ex: Choisissez une option"
                      value={headerText}
                      onChange={(e) => setHeaderText(e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-section">
                    <label className="form-label">
                      Pied de page (optionnel)
                      <span className="tooltip" title="Texte en petits caractères en bas du message">
                        <FiHelpCircle />
                      </span>
                    </label>
                    <input
                      type="text"
                      placeholder="Ex: Valable jusqu'au 31/12"
                      value={footerText}
                      onChange={(e) => setFooterText(e.target.value)}
                      className="form-input"
                    />
                  </div>
                  
                  <div className="form-section">
                    <label className="form-label">
                      Boutons (max 3)
                      <span className="tooltip" title="Les boutons sur lesquels l'utilisateur peut cliquer">
                        <FiHelpCircle />
                      </span>
                    </label>
                    <div className="buttons-list">
                      {buttons.map((btn, i) => (
                        <div key={i} className="button-row">
                          <div className="button-row__fields">
                            <input
                              type="text"
                              placeholder={`ID (ex: btn${i + 1})`}
                              value={btn.id}
                              onChange={(e) => updateButton(i, "id", e.target.value)}
                              className="form-input form-input--small"
                              title="Identifiant unique pour ce bouton (non visible par l'utilisateur)"
                            />
                            <input
                              type="text"
                              placeholder="Texte du bouton (max 20)"
                              value={btn.title}
                              onChange={(e) => updateButton(i, "title", e.target.value.slice(0, 20))}
                              className="form-input form-input--flex"
                              title="Texte visible sur le bouton"
                            />
                          </div>
                          {buttons.length > 1 && (
                            <button onClick={() => removeButton(i)} className="btn-remove" title="Supprimer">
                              <FiX />
                            </button>
                          )}
                        </div>
                      ))}
                      {buttons.length < 3 && (
                        <button onClick={addButton} className="btn-add">+ Ajouter un bouton</button>
                      )}
                    </div>
                  </div>
                </div>

                <ButtonsPreview />
              </div>
            )}

            {mode === "list" && (
              <div className="interactive-config">
                <div className="interactive-form">
                  <div className="form-section">
                    <label className="form-label">Texte du bouton</label>
                    <input
                      type="text"
                      placeholder="Ex: Voir les options"
                      value={buttonText}
                      onChange={(e) => setButtonText(e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-section">
                    <label className="form-label">En-tête (optionnel)</label>
                    <input
                      type="text"
                      placeholder="Titre du message"
                      value={headerText}
                      onChange={(e) => setHeaderText(e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-section">
                    <label className="form-label">Pied de page (optionnel)</label>
                    <input
                      type="text"
                      placeholder="Informations supplémentaires"
                      value={footerText}
                      onChange={(e) => setFooterText(e.target.value)}
                      className="form-input"
                    />
                  </div>
                  
                  {listSections.map((section, sectionIdx) => (
                    <div key={sectionIdx} className="form-section">
                      <label className="form-label">Section {sectionIdx + 1}</label>
                      <input
                        type="text"
                        placeholder="Titre de la section"
                        value={section.title}
                        onChange={(e) => updateSection(sectionIdx, "title", e.target.value)}
                        className="form-input section-title"
                      />
                      
                      {section.rows.map((row, rowIdx) => (
                        <div key={rowIdx} className="row-config">
                          <input
                            type="text"
                            placeholder="ID"
                            value={row.id}
                            onChange={(e) => updateRow(sectionIdx, rowIdx, "id", e.target.value)}
                            className="form-input form-input--small"
                          />
                          <input
                            type="text"
                            placeholder="Titre"
                            value={row.title}
                            onChange={(e) => updateRow(sectionIdx, rowIdx, "title", e.target.value)}
                            className="form-input"
                          />
                          <input
                            type="text"
                            placeholder="Description (opt.)"
                            value={row.description}
                            onChange={(e) => updateRow(sectionIdx, rowIdx, "description", e.target.value)}
                            className="form-input"
                          />
                          {section.rows.length > 1 && (
                            <button onClick={() => removeRow(sectionIdx, rowIdx)} className="btn-remove">
                              <FiX />
                            </button>
                          )}
                        </div>
                      ))}
                      <button onClick={() => addRow(sectionIdx)} className="btn-add-small">+ Ligne</button>
                    </div>
                  ))}
                  <button onClick={addSection} className="btn-add">+ Nouvelle section</button>
                </div>

                <ListPreview />
              </div>
            )}

            {mode === "template" && (
              <div className="template-selector-menu">
                {loadingMenuTemplates ? (
                  <div className="template-selector-menu__loading">Chargement des templates...</div>
                ) : menuTemplates.length === 0 ? (
                  <div className="template-selector-menu__empty">
                    {menuTemplatesAccountNotConfigured
                      ? "Connectez votre compte WhatsApp Business (access_token et WABA ID) dans les paramètres du compte pour afficher les templates."
                      : "Aucun template UTILITY, MARKETING ou AUTHENTICATION disponible. Créez-en un dans Meta Business Manager."}
                  </div>
                ) : (
                  <div className="template-selector-menu__container">
                    {/* Liste des templates */}
                    <div className="template-selector-menu__sidebar">
                      <div className="template-selector-menu__sidebar-list">
                        {menuTemplates.map((template) => {
                          const bodyComponent = template.components?.find(c => c.type === "BODY");
                          const templateText = bodyComponent?.text || template.name;
                          const hasVariables = hasTemplateVariables(template);
                          const isSelected = menuPreviewTemplate?.name === template.name;
                          
                          return (
                            <div
                              key={`${template.name}-${template.language || "default"}`}
                              className={`template-selector-menu__sidebar-item ${isSelected ? 'template-selector-menu__sidebar-item--selected' : ''}`}
                              onClick={() => !disabled && !uploading && setMenuPreviewTemplate(template)}
                            >
                              <div className="template-selector-menu__sidebar-item-header">
                                <div className="template-selector-menu__sidebar-item-name">
                                  {template.name}
                                </div>
                                {hasVariables && (
                                  <div className="template-selector-menu__sidebar-item-badge">
                                    <FiEdit style={{ fontSize: '10px' }} />
                                    Variables
                                  </div>
                                )}
                              </div>
                              <div className="template-selector-menu__sidebar-item-preview" title={templateText}>
                                {templateText}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Aperçu du template */}
                    <div className="template-selector-menu__preview">
                      {menuPreviewTemplate ? (
                        <>
                          <div className="template-selector-menu__preview-content">
                            <div className="template-selector-menu__preview-bubble-wrapper">
                              <div className="bubble me template-selector-menu__preview-bubble">
                                {(() => {
                                  const headerComponent = menuPreviewTemplate.components?.find(c => c.type === "HEADER");
                                  const headerImageUrl = menuPreviewTemplate.header_media_url || 
                                    (headerComponent?.example?.header_handle?.[0]) ||
                                    (headerComponent?.format === "IMAGE" && headerComponent?.example?.header_handle?.[0]);
                                  
                                  return headerImageUrl ? (
                                    <div className="template-selector-menu__preview-content-wrapper">
                                      <div className="template-selector-menu__preview-image-side">
                                        <img 
                                          src={headerImageUrl} 
                                          alt={headerComponent?.text || menuPreviewTemplate.name}
                                        />
                                      </div>
                                      <div className="template-selector-menu__preview-text-side">
                                        {headerComponent && headerComponent.text && (
                                          <div className="template-selector-menu__bubble-header">
                                            {headerComponent.text}
                                          </div>
                                        )}
                                        {(() => {
                                          const bodyComponent = menuPreviewTemplate.components?.find(c => c.type === "BODY");
                                          const templateText = bodyComponent?.text || menuPreviewTemplate.name;
                                          return <span className="bubble__text">{templateText}</span>;
                                        })()}
                                        {(() => {
                                          const footerComponent = menuPreviewTemplate.components?.find(c => c.type === "FOOTER");
                                          return footerComponent && (
                                            <div className="template-selector-menu__bubble-footer">
                                              {footerComponent.text}
                                            </div>
                                          );
                                        })()}
                                        {(() => {
                                          const buttonsComponent = menuPreviewTemplate.components?.find(c => c.type === "BUTTONS");
                                          const buttons = buttonsComponent?.buttons || [];
                                          return buttons.length > 0 && (
                                            <div className="template-selector-menu__bubble-buttons">
                                              {buttons.map((button, btnIndex) => (
                                                <div key={btnIndex} className="template-selector-menu__bubble-button">
                                                  {button.type === "URL" && <FiLink style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.type === "QUICK_REPLY" && <FiSend style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.type === "PHONE_NUMBER" && <FiPhone style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.text || button.url || button.phone_number}
                                                </div>
                                              ))}
                                            </div>
                                          );
                                        })()}
                                        <div className="bubble__footer">
                                          <div className="bubble__footer-left">
                                            <small className="bubble__timestamp">Maintenant</small>
                                            {hasTemplateVariables(menuPreviewTemplate) && (
                                              <small className="template-selector-menu__has-variables" title="Ce template contient des variables à remplir">
                                                <FiEdit style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                                Variables
                                              </small>
                                            )}
                                          </div>
                                          <div className="template-selector-menu__price">
                                            <FiDollarSign style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                            {parseFloat(menuPreviewTemplate.price_eur || menuPreviewTemplate.price_usd || 0.008).toFixed(2).replace(/\.0+$/, '')} {menuPreviewTemplate.price_eur ? 'EUR' : 'USD'}
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    <>
                                      {headerComponent && headerComponent.text && (
                                        <div className="template-selector-menu__bubble-header">
                                          {headerComponent.text}
                                        </div>
                                      )}
                                      {(() => {
                                        const bodyComponent = menuPreviewTemplate.components?.find(c => c.type === "BODY");
                                        const templateText = bodyComponent?.text || menuPreviewTemplate.name;
                                        return <span className="bubble__text">{templateText}</span>;
                                      })()}
                                      {(() => {
                                        const footerComponent = menuPreviewTemplate.components?.find(c => c.type === "FOOTER");
                                        return footerComponent && (
                                          <div className="template-selector-menu__bubble-footer">
                                            {footerComponent.text}
                                          </div>
                                        );
                                      })()}
                                      {(() => {
                                        const buttonsComponent = menuPreviewTemplate.components?.find(c => c.type === "BUTTONS");
                                        const buttons = buttonsComponent?.buttons || [];
                                        return buttons.length > 0 && (
                                          <div className="template-selector-menu__bubble-buttons">
                                            {buttons.map((button, btnIndex) => (
                                              <div key={btnIndex} className="template-selector-menu__bubble-button">
                                                {button.type === "URL" && <FiLink style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.type === "QUICK_REPLY" && <FiSend style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.type === "PHONE_NUMBER" && <FiPhone style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.text || button.url || button.phone_number}
                                              </div>
                                            ))}
                                          </div>
                                        );
                                      })()}
                                      <div className="bubble__footer">
                                        <div className="bubble__footer-left">
                                          <small className="bubble__timestamp">Maintenant</small>
                                          {hasTemplateVariables(menuPreviewTemplate) && (
                                            <small className="template-selector-menu__has-variables" title="Ce template contient des variables à remplir">
                                              <FiEdit style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                              Variables
                                            </small>
                                          )}
                                        </div>
                                        <div className="template-selector-menu__price">
                                          <FiDollarSign style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                          {parseFloat(menuPreviewTemplate.price_eur || menuPreviewTemplate.price_usd || 0.008).toFixed(2).replace(/\.0+$/, '')} {menuPreviewTemplate.price_eur ? 'EUR' : 'USD'}
                                        </div>
                                      </div>
                                    </>
                                  );
                                })()}
                              </div>
                            </div>
                          </div>
                          
                          {/* Bouton Envoyer */}
                          <div className="template-selector-menu__preview-actions">
                            <button
                              className="template-selector-menu__send-btn"
                              onClick={() => {
                                if (disabled || uploading || !menuPreviewTemplate) return;
                                handleSendTemplate(menuPreviewTemplate);
                                // Fermer le menu avancé après l'envoi
                                setShowAdvanced(false);
                                setMode("text");
                                setMenuPreviewTemplate(null);
                              }}
                              disabled={disabled || uploading}
                            >
                              <FiSend style={{ marginRight: '8px' }} />
                              Envoyer
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="template-selector-menu__preview-empty">
                          <div className="template-selector-menu__preview-empty-icon">
                            <FiFile />
                          </div>
                          <div className="template-selector-menu__preview-empty-text">
                            Sélectionnez un template dans le menu pour voir l'aperçu
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="input-area">
        {/* Input file pour photos et vidéos - doit être en dehors du menu pour fonctionner */}
        <input
          ref={mediaInputRef}
          type="file"
          style={{ display: "none" }}
          onChange={(e) => {
            devLog("Media input changed", e.target.files);
            if (e.target.files && e.target.files[0]) {
              devLog("File selected:", e.target.files[0].name, e.target.files[0].type);
              handleMediaSend(e.target.files[0]);
              // Réinitialiser l'input pour permettre de sélectionner le même fichier à nouveau
              e.target.value = '';
            } else {
              devLog("No file selected");
            }
          }}
          accept="image/*,video/*"
        />
        
        {/* Input file pour documents - doit être en dehors du menu pour fonctionner */}
        <input
          ref={documentInputRef}
          type="file"
          style={{ display: "none" }}
          onChange={(e) => {
            devLog("Document input changed", e.target.files);
            if (e.target.files && e.target.files[0]) {
              devLog("File selected:", e.target.files[0].name, e.target.files[0].type);
              handleMediaSend(e.target.files[0]);
              // Réinitialiser l'input pour permettre de sélectionner le même fichier à nouveau
              e.target.value = '';
            } else {
              devLog("No file selected");
            }
          }}
          accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,.csv,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/plain,text/csv"
        />

        {/* Boutons à gauche - toujours affichés maintenant */}
        <div className="left-buttons">
            {/* Bouton emoji */}
            <div className="emoji-container" ref={emojiRef}>
              <button
                onClick={() => {
                  setShowEmojiPicker(!showEmojiPicker);
                  setShowMenu(false);
                }}
                className="btn-emoji"
                disabled={disabled}
                title="Émojis"
              >
                <FiSmile />
              </button>
              
              {showEmojiPicker && (
                <div className="emoji-picker-wrapper">
                  <EmojiPicker
                    onEmojiClick={handleEmojiClick}
                    theme="dark"
                    width="350px"
                    height="400px"
                  />
                </div>
              )}
            </div>

            {/* Bouton + avec menu */}
            <div className="menu-container" ref={menuRef}>
              <button
                onClick={() => {
                  devLog("Menu button clicked, current showMenu:", showMenu);
                  setShowMenu(!showMenu);
                  setShowEmojiPicker(false);
                }}
                className="btn-menu"
                disabled={disabled}
                title="Plus d'options"
              >
                <svg viewBox="0 0 24 24" width="24" height="24">
                  <path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                </svg>
              </button>
              
              {showMenu && (
                <div className="dropdown-menu">
                  <button className="menu-item" onClick={openDocumentPicker}>
                    <div className="menu-icon menu-icon--document">
                      <FiFileText />
                    </div>
                    <span>Document</span>
                  </button>
                  <button className="menu-item" onClick={openMediaPicker}>
                    <div className="menu-icon menu-icon--media">
                      <FiImage />
                    </div>
                    <span>Photos et vidéos</span>
                  </button>
                  <button className="menu-item" onClick={() => openMode("buttons")}>
                    <div className="menu-icon menu-icon--buttons">
                      <FiGrid />
                    </div>
                    <span>Boutons interactifs</span>
                  </button>
                  {!isOutsideFreeWindow && (
                    <button className="menu-item" onClick={() => openMode("list")}>
                      <div className="menu-icon menu-icon--list">
                        <FiList />
                      </div>
                      <span>Liste interactive</span>
                    </button>
                  )}
                  <button className="menu-item" onClick={() => openMode("template")}>
                    <div className="menu-icon menu-icon--template">
                      <FiFile />
                    </div>
                    <span>Template</span>
                  </button>
                </div>
              )}
            </div>
          </div>

        {/* Affichage des templates si hors fenêtre gratuite ET mode manuel activé */}
        {isOutsideFreeWindow && !useAutoTemplate && (
          <div className="templates-selector">
            {hasRecentTemplate && !forceTemplateMode ? (
              // État "En attente d'une réponse client" après l'envoi d'un template
              <div className="templates-selector__waiting">
                <div className="templates-selector__waiting-message">
                  <FiClock style={{ marginRight: '8px', verticalAlign: 'middle' }} />
                  En attente d'une réponse client
                </div>
                <button
                  className="templates-selector__reactivate-btn"
                  onClick={() => {
                    // Forcer l'affichage des templates en activant forceTemplateMode
                    setForceTemplateMode(true);
                  }}
                  disabled={disabled || uploading}
                >
                  Réactiver le mode template
                </button>
              </div>
            ) : (
              // Affichage normal des templates (hors fenêtre gratuite et pas de template récent)
              <>
                {loadingTemplates ? (
                  <div className="templates-selector__loading">Chargement des templates...</div>
                ) : templates.length === 0 ? (
                  <div className="templates-selector__empty">
                    Aucun template UTILITY, MARKETING ou AUTHENTICATION disponible. Créez-en un dans Meta Business Manager.
                  </div>
                ) : (
                  <div className="templates-selector__container">
                    {/* Colonne de gauche : header et sidebar */}
                    <div className="templates-selector__left-column">
                      <div className="templates-selector__header">
                        <span className="templates-selector__title">
                          <FiClock style={{ marginRight: '6px', verticalAlign: 'middle' }} />
                          Plus de 24h depuis la dernière interaction client
                        </span>
                        <span className="templates-selector__subtitle">Sélectionnez un template pour envoyer un message</span>
                        <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
                          <button
                            onClick={() => setUseAutoTemplate(true)}
                            style={{
                              background: 'transparent',
                              border: '1px solid var(--border-light)',
                              color: 'var(--text-primary)',
                              padding: '4px 8px',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '11px'
                            }}
                            title="Activer l'envoi automatique via template (recommandé)"
                          >
                            Activer l'auto-template
                          </button>
                        </div>
                      </div>
                      {/* Menu latéral avec la liste des templates */}
                      <div className="templates-selector__sidebar">
                      <div className="templates-selector__sidebar-list">
                        {templates.map((template) => {
                          const bodyComponent = template.components?.find(c => c.type === "BODY");
                          const templateText = bodyComponent?.text || template.name;
                          const hasVariables = hasTemplateVariables(template);
                          const isSelected = previewTemplate?.name === template.name;
                          
                          return (
                            <div
                              key={`${template.name}-${template.language || "default"}`}
                              className={`templates-selector__sidebar-item ${isSelected ? 'templates-selector__sidebar-item--selected' : ''}`}
                              onClick={() => !disabled && !uploading && setPreviewTemplate(template)}
                            >
                              <div className="templates-selector__sidebar-item-header">
                                <div className="templates-selector__sidebar-item-name">
                                  {template.name}
                                </div>
                                {hasVariables && (
                                  <div className="templates-selector__sidebar-item-badge">
                                    <FiEdit style={{ fontSize: '10px' }} />
                                    Variables
                                  </div>
                                )}
                              </div>
                              <div className="templates-selector__sidebar-item-preview" title={templateText}>
                                {templateText}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      </div>
                    </div>

                    {/* Zone d'aperçu */}
                    <div className="templates-selector__preview">
                      {previewTemplate ? (
                        <>
                          <div className="templates-selector__preview-content">
                            <div className="templates-selector__preview-bubble-wrapper">
                              <div className="bubble me templates-selector__preview-bubble">
                                {(() => {
                                  const headerComponent = previewTemplate.components?.find(c => c.type === "HEADER");
                                  const headerImageUrl = previewTemplate.header_media_url || 
                                    (headerComponent?.example?.header_handle?.[0]) ||
                                    (headerComponent?.format === "IMAGE" && headerComponent?.example?.header_handle?.[0]);
                                  
                                  return headerImageUrl ? (
                                    <div className="templates-selector__preview-content-wrapper">
                                      <div className="templates-selector__preview-image-side">
                                        <img 
                                          src={headerImageUrl} 
                                          alt={headerComponent?.text || previewTemplate.name}
                                        />
                                      </div>
                                      <div className="templates-selector__preview-text-side">
                                        {headerComponent && headerComponent.text && (
                                          <div className="templates-selector__bubble-header">
                                            {headerComponent.text}
                                          </div>
                                        )}
                                        {(() => {
                                          const bodyComponent = previewTemplate.components?.find(c => c.type === "BODY");
                                          const templateText = bodyComponent?.text || previewTemplate.name;
                                          // Log pour debug
                                          devLog("🔍 Preview template text:", {
                                            templateName: previewTemplate.name,
                                            bodyText: bodyComponent?.text,
                                            templateText,
                                            hasVariables: hasTemplateVariables(previewTemplate)
                                          });
                                          return <span className="bubble__text">{templateText}</span>;
                                        })()}
                                        {(() => {
                                          const footerComponent = previewTemplate.components?.find(c => c.type === "FOOTER");
                                          return footerComponent && (
                                            <div className="templates-selector__bubble-footer">
                                              {footerComponent.text}
                                            </div>
                                          );
                                        })()}
                                        {(() => {
                                          const buttonsComponent = previewTemplate.components?.find(c => c.type === "BUTTONS");
                                          const buttons = buttonsComponent?.buttons || [];
                                          return buttons.length > 0 && (
                                            <div className="templates-selector__bubble-buttons">
                                              {buttons.map((button, btnIndex) => (
                                                <div key={btnIndex} className="templates-selector__bubble-button">
                                                  {button.type === "URL" && <FiLink style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.type === "QUICK_REPLY" && <FiSend style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.type === "PHONE_NUMBER" && <FiPhone style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                  {button.text || button.url || button.phone_number}
                                                </div>
                                              ))}
                                            </div>
                                          );
                                        })()}
                                        <div className="bubble__footer">
                                          <div className="bubble__footer-left">
                                            <small className="bubble__timestamp">Maintenant</small>
                                            {hasTemplateVariables(previewTemplate) && (
                                              <small className="templates-selector__has-variables" title="Ce template contient des variables à remplir">
                                                <FiEdit style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                                Variables
                                              </small>
                                            )}
                                          </div>
                                          <div className="templates-selector__price">
                                            <FiDollarSign style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                            {parseFloat(previewTemplate.price_eur || previewTemplate.price_usd || 0.008).toFixed(2).replace(/\.0+$/, '')} {previewTemplate.price_eur ? 'EUR' : 'USD'}
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    <>
                                      {headerComponent && headerComponent.text && (
                                        <div className="templates-selector__bubble-header">
                                          {headerComponent.text}
                                        </div>
                                      )}
                                      {(() => {
                                        const bodyComponent = previewTemplate.components?.find(c => c.type === "BODY");
                                        const templateText = bodyComponent?.text || previewTemplate.name;
                                        return <span className="bubble__text">{templateText}</span>;
                                      })()}
                                      {(() => {
                                        const footerComponent = previewTemplate.components?.find(c => c.type === "FOOTER");
                                        return footerComponent && (
                                          <div className="templates-selector__bubble-footer">
                                            {footerComponent.text}
                                          </div>
                                        );
                                      })()}
                                      {(() => {
                                        const buttonsComponent = previewTemplate.components?.find(c => c.type === "BUTTONS");
                                        const buttons = buttonsComponent?.buttons || [];
                                        return buttons.length > 0 && (
                                          <div className="templates-selector__bubble-buttons">
                                            {buttons.map((button, btnIndex) => (
                                              <div key={btnIndex} className="templates-selector__bubble-button">
                                                {button.type === "URL" && <FiLink style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.type === "QUICK_REPLY" && <FiSend style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.type === "PHONE_NUMBER" && <FiPhone style={{ marginRight: "6px", verticalAlign: "middle" }} />}
                                                {button.text || button.url || button.phone_number}
                                              </div>
                                            ))}
                                          </div>
                                        );
                                      })()}
                                      <div className="bubble__footer">
                                        <div className="bubble__footer-left">
                                          <small className="bubble__timestamp">Maintenant</small>
                                          {hasTemplateVariables(previewTemplate) && (
                                            <small className="templates-selector__has-variables" title="Ce template contient des variables à remplir">
                                              <FiEdit style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                              Variables
                                            </small>
                                          )}
                                        </div>
                                        <div className="templates-selector__price">
                                          <FiDollarSign style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                                          {parseFloat(previewTemplate.price_eur || previewTemplate.price_usd || 0.008).toFixed(2).replace(/\.0+$/, '')} {previewTemplate.price_eur ? 'EUR' : 'USD'}
                                        </div>
                                      </div>
                                    </>
                                  );
                                })()}
                              </div>
                            </div>
                          </div>
                          
                          {/* Bouton Envoyer en bas */}
                          <div className="templates-selector__preview-actions">
                            <button
                              className="templates-selector__send-btn"
                              onClick={() => {
                                if (disabled || uploading || !previewTemplate) return;
                                // handleSendTemplate vérifie déjà les variables et ouvre la modale si nécessaire
                                handleSendTemplate(previewTemplate);
                              }}
                              disabled={disabled || uploading}
                            >
                              <FiSend style={{ marginRight: '8px' }} />
                              Envoyer
                            </button>
                          </div>
                        </>
                      ) : (
                        <div className="templates-selector__preview-empty">
                          <div className="templates-selector__preview-empty-icon">
                            <FiGrid />
                          </div>
                          <div className="templates-selector__preview-empty-text">
                            Sélectionnez un template dans le menu pour voir l'aperçu
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Champ de saisie - logique d'affichage améliorée */}
        {(() => {
          // Si on est dans la fenêtre gratuite : toujours afficher l'input
          if (!isOutsideFreeWindow) {
            return (
              <>
                <div className="input-wrapper input-wrapper--flat">
                  <textarea
                    ref={textAreaRef}
                    rows={1}
                    value={text}
                    spellCheck={discussionPrefs?.spellCheck ?? true}
                    autoCorrect={discussionPrefs?.spellCheck ? "on" : "off"}
                    autoCapitalize={discussionPrefs?.spellCheck ? "sentences" : "off"}
                    lang="fr-FR"
                    onChange={(e) => setText(replaceEmojiShortcuts(e.target.value))}
                    placeholder={
                      discussionPrefs?.enterToSend
                        ? "Écrire un message..."
                        : "Écrire un message... (Ctrl+Entrée pour envoyer)"
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        if (discussionPrefs?.enterToSend) {
                          if (!e.shiftKey) {
                            e.preventDefault();
                            // Vérifier le mode avant d'appeler handleSend
                            if (mode === "buttons") handleButtonsSend();
                            else if (mode === "list") handleListSend();
                            else handleSend();
                          }
                        } else if (e.metaKey || e.ctrlKey) {
                          e.preventDefault();
                          // Vérifier le mode avant d'appeler handleSend
                          if (mode === "buttons") handleButtonsSend();
                          else if (mode === "list") handleListSend();
                          else handleSend();
                        }
                      }
                    }}
                    disabled={disabled}
                  />
                </div>
                
                {/* Bouton d'envoi */}
                <button
                  className="btn-send-whatsapp btn-send-flat"
                  onClick={() => {
                    if (mode === "buttons") handleButtonsSend();
                    else if (mode === "list") handleListSend();
                    else handleSend();
                  }}
                  disabled={disabled || !text.trim() || uploading || loadingPrice}
                  aria-label={editingMessage ? "Modifier" : "Envoyer"}
                >
                  <FiSend />
                </button>
              </>
            );
          }
          
          // Si on est hors fenêtre gratuite ET mode auto-template : afficher l'input
          if (isOutsideFreeWindow && useAutoTemplate) {
            return (
              <>
                <div className="input-wrapper input-wrapper--flat">
                  <textarea
                    ref={textAreaRef}
                    rows={1}
                    value={text}
                    spellCheck={discussionPrefs?.spellCheck ?? true}
                    autoCorrect={discussionPrefs?.spellCheck ? "on" : "off"}
                    autoCapitalize={discussionPrefs?.spellCheck ? "sentences" : "off"}
                    lang="fr-FR"
                    onChange={(e) => setText(replaceEmojiShortcuts(e.target.value))}
                    placeholder="Écrire un message..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        if (discussionPrefs?.enterToSend) {
                          if (!e.shiftKey) {
                            e.preventDefault();
                            // Vérifier le mode avant d'appeler handleSend
                            if (mode === "buttons") handleButtonsSend();
                            else if (mode === "list") handleListSend();
                            else handleSend();
                          }
                        } else if (e.metaKey || e.ctrlKey) {
                          e.preventDefault();
                          // Vérifier le mode avant d'appeler handleSend
                          if (mode === "buttons") handleButtonsSend();
                          else if (mode === "list") handleListSend();
                          else handleSend();
                        }
                      }
                    }}
                    disabled={disabled}
                  />
                </div>
                
                {/* Bouton d'envoi */}
                <button
                  className="btn-send-whatsapp btn-send-flat"
                  onClick={() => {
                    // Vérifier le mode avant d'appeler handleSend
                    if (mode === "buttons") handleButtonsSend();
                    else if (mode === "list") handleListSend();
                    else handleSend();
                  }}
                  disabled={disabled || !text.trim() || uploading}
                  aria-label="Envoyer"
                >
                  <FiSend />
                </button>
              </>
            );
          }
          
          // Si on est hors fenêtre gratuite ET mode manuel ET pas de template récent : afficher l'input (fallback)
          if (isOutsideFreeWindow && !useAutoTemplate && !hasRecentTemplate) {
            return (
              <>
                <div className="input-wrapper input-wrapper--flat">
                  <textarea
                    ref={textAreaRef}
                    rows={1}
                    value={text}
                    spellCheck={discussionPrefs?.spellCheck ?? true}
                    autoCorrect={discussionPrefs?.spellCheck ? "on" : "off"}
                    autoCapitalize={discussionPrefs?.spellCheck ? "sentences" : "off"}
                    lang="fr-FR"
                    onChange={(e) => setText(replaceEmojiShortcuts(e.target.value))}
                    placeholder="Écrire un message..."
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        if (discussionPrefs?.enterToSend) {
                          if (!e.shiftKey) {
                            e.preventDefault();
                            // Vérifier le mode avant d'appeler handleSend
                            if (mode === "buttons") handleButtonsSend();
                            else if (mode === "list") handleListSend();
                            else handleSend();
                          }
                        } else if (e.metaKey || e.ctrlKey) {
                          e.preventDefault();
                          // Vérifier le mode avant d'appeler handleSend
                          if (mode === "buttons") handleButtonsSend();
                          else if (mode === "list") handleListSend();
                          else handleSend();
                        }
                      }
                    }}
                    disabled={disabled}
                  />
                </div>

                {/* Bouton d'envoi */}
                <button
                  className="btn-send-whatsapp btn-send-flat"
                  onClick={() => {
                    // Vérifier le mode avant d'appeler handleSend
                    if (mode === "buttons") handleButtonsSend();
                    else if (mode === "list") handleListSend();
                    else handleSend();
                  }}
                  disabled={disabled || !text.trim() || uploading}
                  aria-label="Envoyer"
                >
                  <FiSend />
                </button>
              </>
            );
          }
          
          // Sinon (hors fenêtre + mode manuel + template récent) : ne rien afficher (le sélecteur de templates est affiché)
          return null;
        })()}
      </div>

      {editingMessage && (
        <div className="edit-banner">
          <span>Modification du message</span>
          <button type="button" onClick={() => { setText(""); onCancelEdit?.(); }}>
            Annuler
          </button>
        </div>
      )}
      
      <TemplateVariablesModal
        template={selectedTemplate}
        isOpen={showTemplateModal}
        onClose={handleTemplateModalClose}
        onSend={handleTemplateModalSend}
      />
    </div>
  );
}
