import { useEffect, useState, useRef } from "react";
import { formatRelativeDateTime } from "../../utils/date";
import {
  FiHeadphones,
  FiImage,
  FiVideo,
  FiFileText,
  FiMapPin,
  FiMessageSquare,
  FiPhone,
  FiList,
  FiLink,
  FiSend,
} from "react-icons/fi";
import { MdPushPin } from "react-icons/md";
import { api } from "../../api/axiosClient";
import MessageReactions from "./MessageReactions";
import MessageStatus from "./MessageStatus";
import PDFThumbnail from "../gallery/PDFThumbnail";

const FETCHABLE_MEDIA = new Set(["audio", "voice", "image", "video", "document", "sticker"]);

const TYPE_MAP = {
  audio: { icon: <FiHeadphones />, label: "Message audio" },
  voice: { icon: <FiHeadphones />, label: "Message vocal" },
  image: { icon: <FiImage />, label: "Image reçue" },
  video: { icon: <FiVideo />, label: "Vidéo" },
  document: { icon: <FiFileText />, label: "Document" },
  sticker: { icon: <FiImage />, label: "Sticker" },
  location: { icon: <FiMapPin />, label: "Localisation" },
  contacts: { icon: <FiMessageSquare />, label: "Carte de contact" },
  interactive: { icon: <FiMessageSquare />, label: "Réponse interactive" },
  call: { icon: <FiPhone />, label: "Appel WhatsApp" },
};

function MediaRenderer({ message, messageType, onLoadingChange }) {
  const [source, setSource] = useState(message._localPreview || message.storage_url || null);
  const [loading, setLoading] = useState(!message._localPreview && !message.storage_url);
  const [error, setError] = useState(false);

  useEffect(() => {
    // Si on a un aperçu local, l'utiliser directement
    if (message._localPreview) {
      setSource(message._localPreview);
      setLoading(false);
      setError(false);
      onLoadingChange?.(false, false);
      return;
    }

    // Si on a une URL de stockage Supabase, l'utiliser directement
    if (message.storage_url) {
      setSource(message.storage_url);
      setLoading(false);
      setError(false);
      onLoadingChange?.(false, false);
      return;
    }

    // Si on n'a ni media_id ni storage_url, on ne peut pas charger le média
    if ((!message.media_id && !message.storage_url) || !FETCHABLE_MEDIA.has(messageType)) {
      console.warn(`⚠️ [FRONTEND MEDIA] Cannot load media for message ${message.id}:`, {
        has_media_id: !!message.media_id,
        has_storage_url: !!message.storage_url,
        is_fetchable: FETCHABLE_MEDIA.has(messageType)
      });
      setSource(null);
      setLoading(false);
      onLoadingChange?.(false, false);
      return;
    }

    console.log(`📥 [FRONTEND MEDIA] Fetching media from API for message ${message.id} (media_id: ${message.media_id})`);
    let cancelled = false;
    let objectUrl = null;

    api
      .get(`/messages/media/${message.id}`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) {
          console.log(`🚫 [FRONTEND MEDIA] Request cancelled for message ${message.id}`);
          return;
        }
        console.log(`✅ [FRONTEND MEDIA] Media fetched successfully for message ${message.id}, size: ${res.data.size} bytes`);
        objectUrl = URL.createObjectURL(res.data);
        setSource(objectUrl);
        setError(false);
        onLoadingChange?.(false, false);
      })
      .catch((err) => {
        if (!cancelled) {
          console.error(`❌ [FRONTEND MEDIA] Error fetching media for message ${message.id}:`, err);
          setSource(null);
          setError(true);
          onLoadingChange?.(false, true);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [message.id, message.media_id, messageType, message._localPreview, message.storage_url]);

  if (loading) {
    return <span className="media-loading">Chargement…</span>;
  }

  if (!source || error) {
    return <span className="media-error">{message.content_text || "Média non disponible"}</span>;
  }

  if (messageType === "image" || messageType === "sticker") {
    return <img src={source} alt="" className="bubble-media__image" />;
  }

  if (messageType === "video") {
    return <video src={source} controls className="bubble-media__video" />;
  }

  if (messageType === "audio" || messageType === "voice") {
    return <audio src={source} controls className="bubble-media__audio" />;
  }

  if (messageType === "document") {
    // Vérifier si c'est un PDF
    const isPDF = source && (
      source.toLowerCase().endsWith(".pdf") || 
      source.includes(".pdf") || 
      message.media_mime_type?.toLowerCase().includes("pdf") ||
      message.media_filename?.toLowerCase().endsWith(".pdf")
    );
    
    if (isPDF && source) {
      // Afficher une prévisualisation PDF comme dans la galerie
      // Utiliser useMemo pour éviter les re-renders inutiles
      const pdfUrl = source; // Mémoriser l'URL pour éviter les changements de référence
      
      return (
        <div className="bubble-media__document-preview">
          <div className="bubble-media__document-preview-wrapper">
            <div className="bubble-media__document-preview-canvas">
              <PDFThumbnail 
                key={pdfUrl} // Utiliser key pour forcer le remontage si l'URL change vraiment
                url={pdfUrl} 
                width={300} 
                height={350}
              />
            </div>
            <a 
              href={pdfUrl} 
              download 
              className="bubble-media__document-link" 
              target="_blank" 
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              <FiFileText /> Télécharger le PDF
            </a>
          </div>
        </div>
      );
    }
    
    return (
      <a href={source} download className="bubble-media__document" target="_blank" rel="noreferrer">
        <FiFileText /> Télécharger le document
      </a>
    );
  }

  return <span>{message.content_text}</span>;
}

function RichMediaBubble({ message, messageType }) {
  // Si on a déjà storage_url ou _localPreview, ne pas afficher l'icône
  const hasSource = !!(message.storage_url || message._localPreview);
  const [showIcon, setShowIcon] = useState(!hasSource);
  const typeEntry = TYPE_MAP[messageType];

  // Ne pas afficher le content_text s'il contient juste un placeholder
  const isPlaceholder = message.content_text && 
    (message.content_text.trim() === '[image]' || 
     message.content_text.trim() === '[audio]' ||
     message.content_text.trim() === '[video]' ||
     message.content_text.trim() === '[document]');
  
  const caption = isPlaceholder ? null : message.content_text;
  
  // Parser les boutons depuis interactive_data si présent
  let buttons = [];
  if (message.interactive_data) {
    try {
      const interactiveData = typeof message.interactive_data === 'string' 
        ? JSON.parse(message.interactive_data) 
        : message.interactive_data;
      
      if (interactiveData.buttons && Array.isArray(interactiveData.buttons)) {
        // Format pour les templates: {type: "QUICK_REPLY", text: "..."}
        buttons = interactiveData.buttons.map(btn => ({
          text: btn.text || btn.reply?.title || '',
          type: btn.type || 'QUICK_REPLY',
          url: btn.url || '',
          phone_number: btn.phone_number || ''
        }));
      } else if (interactiveData.type === 'button' && interactiveData.buttons) {
        buttons = interactiveData.buttons.map(btn => ({
          text: btn.reply?.title || btn.text || '',
          type: btn.type || 'reply'
        }));
      }
    } catch (e) {
      console.warn('Error parsing interactive_data:', e);
    }
  }

  const handleLoadingChange = (loading, error) => {
    // Cacher l'icône si l'image/vidéo est chargée sans erreur
    if (messageType === 'image' || messageType === 'video' || messageType === 'sticker') {
      setShowIcon(loading || error);
    }
  };

  return {
    content: (
      <div className="bubble-media bubble-media--rich">
        {showIcon && (
          <div className="bubble-media__icon">{typeEntry?.icon}</div>
        )}
        <div className="bubble-media__content">
          <MediaRenderer 
            message={message} 
            messageType={messageType}
            onLoadingChange={handleLoadingChange}
          />
          {caption && (
            <p className="bubble-media__caption" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowWrap: 'break-word' }}>
              {caption}
            </p>
          )}
        </div>
      </div>
    ),
    buttons: buttons.length > 0 ? (
      <div className="bubble-media__buttons-container">
        {buttons.map((button, index) => (
          <div key={index} className="bubble-media__button">
            {button.text || button.title || button.reply?.title || button.url || button.phone_number || ''}
          </div>
        ))}
      </div>
    ) : null
  };
}

function InteractiveBubble({ message }) {
  const content = message.content_text || "";
  
  // Extraire les parties du message interactif
  const lines = content.split("\n");
  const bodyText = lines[0] || "";
  const buttonInfo = lines.find(line => line.startsWith("[Boutons:") || line.startsWith("[Liste"));
  
  if (buttonInfo) {
    // C'est un message avec boutons
    const buttonsMatch = buttonInfo.match(/\[Boutons: (.*)\]/);
    if (buttonsMatch) {
      const buttonTitles = buttonsMatch[1].split(", ");
      return (
        <div className="interactive-bubble">
          <div className="interactive-bubble__body">{bodyText}</div>
          <div className="interactive-bubble__buttons">
            {buttonTitles.map((title, i) => (
              <div key={i} className="interactive-bubble__button">{title}</div>
            ))}
          </div>
        </div>
      );
    }
    
    // C'est une liste
    return (
      <div className="interactive-bubble">
        <div className="interactive-bubble__body">{bodyText}</div>
        <div className="interactive-bubble__list-indicator">
          <FiList /> Liste interactive
        </div>
      </div>
    );
  }
  
  // Fallback au texte simple
  return <span className="bubble__text">{content}</span>;
}

function renderBody(message) {
  const messageType = (message.message_type || "text").toLowerCase();
  const typeEntry = TYPE_MAP[messageType];

  // Afficher le média si on a un media_id OU un storage_url (média stocké dans Supabase)
  // Pour les templates avec image, le message_type peut être "image" ou "template" avec storage_url
  const hasMedia = message.media_id || message.storage_url;
  const isMediaType = FETCHABLE_MEDIA.has(messageType);
  // Un template avec image : message_type === "image" avec template_name OU message_type === "template" avec storage_url
  const isTemplateWithImage = (messageType === "image" && message.template_name) || 
                               (messageType === "template" && hasMedia);
  
  if ((isMediaType || isTemplateWithImage) && hasMedia) {
    // Utiliser "image" comme type pour l'affichage si c'est un template avec image
    const displayType = isTemplateWithImage ? "image" : messageType;
    const result = RichMediaBubble({ message, messageType: displayType });
    return result;
  }

  // Messages interactifs
  if (messageType === "interactive") {
    return { content: <InteractiveBubble message={message} />, buttons: null };
  }

  if (!typeEntry || messageType === "text" || messageType === "template") {
    // Préserver les retours à la ligne pour les templates et textes
    const text = message.content_text || "";
    const lines = text.split('\n');
    return {
      content: (
        <span className="bubble__text">
          {lines.map((line, index) => (
            <span key={index}>
              {line}
              {index < lines.length - 1 && <br />}
            </span>
          ))}
        </span>
      ),
      buttons: null
    };
  }

  return {
    content: (
      <div className="bubble-media">
        <div className="bubble-media__icon">{typeEntry.icon}</div>
        <div className="bubble-media__content">
          <strong>{typeEntry.label}</strong>
          {message.content_text && <p className="bubble__text">{message.content_text}</p>}
        </div>
      </div>
    ),
    buttons: null
  };
}

export default function MessageBubble({ message, conversation, onReactionChange, onContextMenu, forceReactionOpen = false, onResend }) {
  const mine = message.direction === "outbound";
  const timestamp = message.timestamp ? formatRelativeDateTime(message.timestamp) : "";

  const messageType = (message.message_type || "text").toLowerCase();
  const hasMedia = message.media_id || message.storage_url;
  // Un template avec image : message_type === "image" avec template_name OU message_type === "template" avec storage_url
  const isTemplateWithImage = (messageType === "image" && message.template_name) || 
                               (messageType === "template" && hasMedia);
  const isMedia = (FETCHABLE_MEDIA.has(messageType) || isTemplateWithImage) && hasMedia;
  const isDeletedForAll = !!message.deleted_for_all_at;
  const isEdited = !!message.edited_at;
  const isPinned = !!message.is_pinned;

  const bodyResult = renderBody(message);
  const bodyContent = bodyResult?.content || bodyResult;
  const buttons = bodyResult?.buttons || null;

  const bubbleRef = useRef(null);
  const buttonsWrapperRef = useRef(null);

  // Synchroniser la largeur du conteneur de boutons avec la bulle
  useEffect(() => {
    if (buttons && bubbleRef.current && buttonsWrapperRef.current) {
      const syncWidth = () => {
        const bubbleWidth = bubbleRef.current.offsetWidth;
        if (bubbleWidth > 0) {
          buttonsWrapperRef.current.style.width = `${bubbleWidth}px`;
        }
      };

      // Synchroniser immédiatement
      syncWidth();

      // Observer les changements de taille de la bulle
      const resizeObserver = new ResizeObserver(syncWidth);
      resizeObserver.observe(bubbleRef.current);

      return () => {
        resizeObserver.disconnect();
      };
    }
  }, [buttons, bodyContent]);

  return (
    <div className="message-with-buttons-wrapper">
      <div
        ref={bubbleRef}
        className={`bubble ${mine ? "me" : "them"} ${isMedia ? "bubble--media" : ""} ${isDeletedForAll ? "bubble--deleted" : ""} ${isPinned ? "bubble--pinned" : ""}`}
        onContextMenu={onContextMenu}
        style={{ position: "relative" }}
      >
        {isPinned && (
          <div className="bubble__pinned-indicator" title="Message épinglé">
            <MdPushPin />
          </div>
        )}
        {isDeletedForAll ? (
          <span className="bubble__text bubble__text--deleted">
            {mine ? "Vous avez supprimé ce message" : "Ce message a été supprimé"}
          </span>
        ) : (
          bodyContent
        )}
        <div className="bubble__footer">
          <div className="bubble__footer-left">
            <small className="bubble__timestamp">
              {timestamp}
              {isEdited && !isDeletedForAll ? " · modifié" : ""}
            </small>
            {!isDeletedForAll && (
              <MessageReactions 
                message={message} 
                conversation={conversation} 
                onReactionChange={onReactionChange}
                forceOpen={forceReactionOpen}
              />
            )}
          </div>
          {!isDeletedForAll && (
            <MessageStatus 
              status={message.status} 
              isOwnMessage={mine}
              conversation={conversation}
              messageTimestamp={message.timestamp}
              message={message}
              onResend={onResend}
            />
          )}
        </div>
      </div>
      {buttons && (
        <div 
          ref={buttonsWrapperRef}
          className={`bubble-buttons-wrapper ${mine ? "bubble-buttons-wrapper--me" : "bubble-buttons-wrapper--them"}`}
        >
          {buttons}
        </div>
      )}
    </div>
  );
}