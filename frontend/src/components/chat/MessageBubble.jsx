import { useEffect, useState, useRef, memo } from "react";
import { createPortal } from "react-dom";
import { formatRelativeDateTime, parseDateAsUTC } from "../../utils/date";
import {
  FiHeadphones,
  FiImage,
  FiVideo,
  FiFileText,
  FiMapPin,
  FiMessageSquare,
  FiPhone,
  FiList,
  FiArrowLeft,
  FiMoreVertical,
  FiCornerUpLeft,
  FiCopy,
  FiTrash2,
  FiX,
  FiAlertCircle,
  FiMic,
} from "react-icons/fi";
import { MdPushPin } from "react-icons/md";
import { api } from "../../api/axiosClient";
import { transcribeMessageAudio } from "../../api/messagesApi";
import MessageReactions from "./MessageReactions";
import MessageStatus from "./MessageStatus";
import PDFThumbnail from "../gallery/PDFThumbnail";
import ChatAudioPlayer from "./ChatAudioPlayer";
import "./MediaGallery.css";

const FETCHABLE_MEDIA = new Set(["audio", "voice", "image", "video", "document", "sticker"]);

const MEDIA_PLACEHOLDERS = new Set([
  "[image]",
  "[sticker]",
  "[audio]",
  "[video]",
  "[document]",
  "[voice]",
]);

function lightboxCaptionFromMessage(message) {
  const ct = (message?.content_text || "").trim();
  if (!ct || MEDIA_PLACEHOLDERS.has(ct)) return null;
  return ct;
}

const TRANSCRIBE_ERROR_FR = {
  media_not_available: "Média non disponible ou pas encore téléchargé.",
  transcription_inbound_only: "La transcription ne s’applique qu’aux messages reçus.",
  not_audio_message: "Ce message n’est pas un audio.",
  audio_file_too_large: "Fichier audio trop volumineux.",
  media_expired_or_invalid: "Le média WhatsApp a expiré ou n’est plus disponible.",
  media_not_found: "Média introuvable.",
  gemini_not_configured: "Transcription indisponible (clé Gemini manquante).",
  audio_transcription_disabled: "La transcription est désactivée.",
  transcription_failed: "La transcription a échoué. Réessaie plus tard.",
  transcription_save_failed: "Erreur d’enregistrement de la transcription.",
  media_fetch_failed: "Impossible de récupérer le fichier audio.",
};

const _mediaBlobCache = new Map();
const MEDIA_CACHE_MAX = 200;

function getCachedBlobUrl(messageId) {
  const entry = _mediaBlobCache.get(messageId);
  if (!entry) return null;
  entry.refs++;
  _mediaBlobCache.delete(messageId);
  _mediaBlobCache.set(messageId, entry);
  return entry.url;
}

function setCachedBlobUrl(messageId, url) {
  if (_mediaBlobCache.has(messageId)) {
    const entry = _mediaBlobCache.get(messageId);
    entry.refs++;
    return;
  }
  if (_mediaBlobCache.size >= MEDIA_CACHE_MAX) {
    for (const [key, entry] of _mediaBlobCache) {
      if (entry.refs <= 0) {
        URL.revokeObjectURL(entry.url);
        _mediaBlobCache.delete(key);
        break;
      }
    }
  }
  _mediaBlobCache.set(messageId, { url, refs: 1 });
}

function releaseCachedBlobUrl(messageId) {
  const entry = _mediaBlobCache.get(messageId);
  if (entry) entry.refs = Math.max(0, entry.refs - 1);
}

function parseOutboundMeta(raw) {
  if (raw == null) return null;
  if (typeof raw === "object" && !Array.isArray(raw)) return raw;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return null;
}

/** Ligne discrète : origine du message sortant (équipe, scénario, assistant IA). */
function OutboundAttribution({ message }) {
  if (message.direction !== "outbound" || message.is_system) return null;
  const meta = parseOutboundMeta(message.outbound_meta);
  if (message.sent_by_user_id) {
    return (
      <div className="bubble__source" title="Envoyé manuellement depuis l’app">
        Équipe
      </div>
    );
  }
  if (!meta && (!message.sent_via || message.sent_via === "ui")) return null;
  const sv = message.sent_via || "";
  let label = "";
  let title = "";
  if (meta?.source === "gemini_bot") {
    label = "IA · Assistant";
    title = "Réponse générée par l’assistant Gemini (mode conversation).";
  } else if (meta?.source === "flow") {
    const nt = meta.node_type || "";
    const mode = meta.gemini_mode || "";
    const kind = meta.ui_kind || "";
    if (nt === "sendText") {
      label = "Scénario · texte";
      title = `Message issu du scénario (nœud ${meta.node_id || "?"})`;
    } else if (nt === "interactiveNode") {
      label = kind === "list" ? "Scénario · liste" : "Scénario · boutons";
      title = `Message interactif du scénario (nœud ${meta.node_id || "?"})`;
    } else if (nt === "gemini") {
      label = mode === "playbook_fallback" ? "Scénario · IA (playbook)" : "Scénario · IA";
      title = `Réponse générée dans un nœud IA du scénario (${meta.node_id || "?"})`;
    } else {
      label = "Scénario";
      title = meta.node_id ? `Nœud ${meta.node_id}` : "Message issu du scénario";
    }
  } else if (sv === "bot") {
    label = "IA · Assistant";
    title = "Réponse automatique (assistant).";
  } else if (sv === "flow") {
    label = "Scénario";
    title = "Envoyé par le scénario automatisé.";
  } else if (sv === "broadcast") {
    label = "Campagne";
    title = "Diffusion / campagne.";
  } else {
    return null;
  }
  return (
    <div className="bubble__source" title={title}>
      {label}
    </div>
  );
}

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
  unsupported: { icon: <FiAlertCircle />, label: "Format non pris en charge" },
};

function MediaRenderer({ message, messageType, onLoadingChange, onAudioTranscript }) {
  const [source, setSource] = useState(message._localPreview || message.storage_url || null);
  const [loading, setLoading] = useState(!message._localPreview && !message.storage_url);
  const [error, setError] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [localTranscript, setLocalTranscript] = useState(() =>
    (message.audio_transcript || "").trim()
  );
  const [transcribing, setTranscribing] = useState(false);
  const [transcribeError, setTranscribeError] = useState(null);

  useEffect(() => {
    setLocalTranscript((message.audio_transcript || "").trim());
    setTranscribeError(null);
  }, [message.id, message.audio_transcript]);

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

    const cached = getCachedBlobUrl(message.id);
    if (cached) {
      setSource(cached);
      setLoading(false);
      setError(false);
      onLoadingChange?.(false, false);
      return () => { releaseCachedBlobUrl(message.id); };
    }

    let cancelled = false;

    api
      .get(`/messages/media/${message.id}`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        const headerType = res.headers?.["content-type"];
        const mimeFromHeader = headerType ? headerType.split(";")[0].trim() : "";
        const fallbackMime =
          message.media_mime_type ||
          (messageType === "audio" || messageType === "voice"
            ? "audio/ogg"
            : "application/octet-stream");
        let blob = res.data;
        if (!(blob instanceof Blob)) {
          blob = new Blob([blob], { type: mimeFromHeader || fallbackMime });
        } else if (!blob.type) {
          blob = new Blob([blob], { type: mimeFromHeader || fallbackMime });
        }
        if (blob.size === 0) {
          throw new Error("empty_media_blob");
        }
        const objectUrl = URL.createObjectURL(blob);
        setCachedBlobUrl(message.id, objectUrl);
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
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      releaseCachedBlobUrl(message.id);
    };
  }, [message.id, message.media_id, messageType, message._localPreview, message.storage_url]);

  useEffect(() => {
    if (!lightboxOpen) return;
    const onKey = (e) => {
      if (e.key === "Escape") setLightboxOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [lightboxOpen]);

  if (loading) {
    return <span className="media-loading">Chargement…</span>;
  }

  if (messageType === "audio" || messageType === "voice") {
    const playerOk = !!(source && !error);
    const directionIn = (message.direction || "").toLowerCase() === "inbound";
    const canRequestTranscript =
      directionIn && !!(message.storage_url || message.media_id);
    const showTranscribeBtn = canRequestTranscript && !localTranscript;

    const runTranscribe = async (e) => {
      e.stopPropagation();
      if (!canRequestTranscript || transcribing) return;
      setTranscribing(true);
      setTranscribeError(null);
      try {
        const { data } = await transcribeMessageAudio(message.id);
        const t = (data?.transcript || "").trim();
        setLocalTranscript(t);
        onAudioTranscript?.(message.id, t);
      } catch (err) {
        const d = err.response?.data?.detail;
        let msg = "Échec de la transcription";
        if (typeof d === "string") {
          msg = TRANSCRIBE_ERROR_FR[d] || d;
        } else if (Array.isArray(d) && d[0]?.msg) {
          msg = d[0].msg;
        }
        setTranscribeError(msg);
      } finally {
        setTranscribing(false);
      }
    };

    const showFooter =
      showTranscribeBtn || transcribing || !!transcribeError || !!localTranscript;

    return (
      <div
        className="bubble-media__audio-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bubble-media__audio-card-main">
          {playerOk ? (
            <ChatAudioPlayer src={source} mimeType={message.media_mime_type} />
          ) : (
            <span className="bubble-media__audio-card-error">
              {message.content_text || "Média non disponible"}
            </span>
          )}
        </div>
        {showFooter ? (
          <div className="bubble-media__audio-card-footer">
            {showTranscribeBtn || transcribing ? (
              <button
                type="button"
                className="bubble-media__transcribe-btn"
                disabled={transcribing || !canRequestTranscript}
                onClick={runTranscribe}
              >
                <FiMic className="bubble-media__transcribe-btn-icon" aria-hidden />
                {transcribing ? "Transcription en cours…" : "Transcrire le message"}
              </button>
            ) : null}
            {transcribeError ? (
              <p className="bubble-media__transcribe-error" role="alert">
                {transcribeError}
              </p>
            ) : null}
            {localTranscript ? (
              <div className="bubble-media__transcript-block">
                <span className="bubble-media__transcript-label">Transcription</span>
                <p className="bubble-media__transcript-text" dir="auto">
                  {localTranscript}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }

  if (!source || error) {
    return <span className="media-error">{message.content_text || "Média non disponible"}</span>;
  }

  if (messageType === "image" || messageType === "sticker") {
    const caption = lightboxCaptionFromMessage(message);
    return (
      <>
        <img
          src={source}
          alt=""
          className="bubble-media__image bubble-media__image--clickable"
          role="button"
          tabIndex={0}
          aria-label="Agrandir l’image"
          onClick={(e) => {
            e.stopPropagation();
            setLightboxOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              setLightboxOpen(true);
            }
          }}
        />
        {lightboxOpen &&
          createPortal(
            <div
              className="media-gallery__modal"
              role="dialog"
              aria-modal="true"
              aria-label="Aperçu image"
              onClick={() => setLightboxOpen(false)}
            >
              <div className="media-gallery__modal-content" onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  className="media-gallery__modal-close"
                  onClick={() => setLightboxOpen(false)}
                  aria-label="Fermer"
                >
                  <FiX />
                </button>
                <img src={source} alt="" className="media-gallery__modal-image" />
                {caption ? <div className="media-gallery__modal-caption">{caption}</div> : null}
              </div>
            </div>,
            document.body
          )}
      </>
    );
  }

  if (messageType === "video") {
    return <video src={source} controls className="bubble-media__video" />;
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

function RichMediaBubble({ message, messageType, onAudioTranscript }) {
  // Si on a déjà storage_url ou _localPreview, ne pas afficher l'icône
  const hasSource = !!(message.storage_url || message._localPreview);
  const [showIcon, setShowIcon] = useState(!hasSource);
  const typeEntry = TYPE_MAP[messageType];

  // Ne pas afficher le content_text s'il contient juste un placeholder
  const isPlaceholder = message.content_text && 
    (message.content_text.trim() === '[image]' || 
     message.content_text.trim() === '[audio]' ||
     message.content_text.trim() === '[video]' ||
     message.content_text.trim() === '[document]' ||
     message.content_text.trim() === '[voice]' ||
     message.content_text.trim() === '[sticker]');
  
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
    // Cacher l'icône si le média est chargé sans erreur
    if (
      messageType === "image" ||
      messageType === "video" ||
      messageType === "sticker" ||
      messageType === "audio" ||
      messageType === "voice"
    ) {
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
            onAudioTranscript={onAudioTranscript}
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
          <div
            key={`${message.id}-rich-btn-${button.reply?.id || button.url || button.phone_number || index}`}
            className="bubble-media__button"
          >
            <FiArrowLeft className="bubble-media__button-icon" />
            <span className="bubble-media__button-text">
              {button.text || button.title || button.reply?.title || button.url || button.phone_number || ''}
            </span>
          </div>
        ))}
      </div>
    ) : null
  };
}

function InteractiveBubble({ message }) {
  // Parser interactive_data pour obtenir header, body, footer et boutons
  let headerText = null;
  let bodyText = message.content_text || "";
  let footerText = null;
  let buttons = [];
  let interactiveType = null;
  
  if (message.interactive_data) {
    try {
      const interactiveData = typeof message.interactive_data === 'string' 
        ? JSON.parse(message.interactive_data) 
        : message.interactive_data;
      
      interactiveType = interactiveData.type;
      
      // Extraire header, body, footer depuis interactive_data
      if (interactiveData.header) {
        headerText = interactiveData.header;
      }
      if (interactiveData.body) {
        bodyText = interactiveData.body;
      }
      if (interactiveData.footer) {
        footerText = interactiveData.footer;
      }
      
      // Extraire les boutons depuis action
      if (interactiveData.action) {
        if (interactiveData.action.buttons && Array.isArray(interactiveData.action.buttons)) {
          // Format pour messages interactifs: {type: "reply", reply: {id: "...", title: "..."}}
          buttons = interactiveData.action.buttons.map(btn => ({
            text: btn.reply?.title || btn.text || '',
            type: btn.type || 'reply'
          }));
        } else if (interactiveData.action.button && interactiveData.action.sections) {
          // Format pour listes interactives
          interactiveType = 'list';
        }
      }
      
      // Si les boutons sont directement dans interactiveData.buttons (format template)
      if (interactiveData.buttons && Array.isArray(interactiveData.buttons) && buttons.length === 0) {
        buttons = interactiveData.buttons.map(btn => ({
          text: btn.text || btn.reply?.title || '',
          type: btn.type || 'QUICK_REPLY',
          url: btn.url || '',
          phone_number: btn.phone_number || ''
        }));
      }
    } catch (e) {
      console.warn('Error parsing interactive_data:', e);
    }
  }
  
  // Si on n'a pas pu parser interactive_data, essayer de parser le content_text
  if (!headerText && !footerText && buttons.length === 0) {
    const content = message.content_text || "";
    const lines = content.split("\n");
    bodyText = lines[0] || "";
    const buttonInfo = lines.find(line => line.startsWith("[Boutons:") || line.startsWith("[Liste"));
    
    if (buttonInfo) {
      const buttonsMatch = buttonInfo.match(/\[Boutons: (.*)\]/);
      if (buttonsMatch) {
        const buttonTitles = buttonsMatch[1].split(", ");
        buttons = buttonTitles.map(title => ({ text: title, type: 'reply' }));
      }
    }
  }
  
  // Afficher le message avec header, body, footer et boutons (comme les templates)
  return (
    <div className="interactive-bubble">
      {headerText && (
        <div className="interactive-bubble__header">{headerText}</div>
      )}
      <div className="interactive-bubble__body">{bodyText}</div>
      {footerText && (
        <div className="interactive-bubble__footer">{footerText}</div>
      )}
      {interactiveType === 'list' && (
        <div className="interactive-bubble__list-indicator">
          <FiList /> Liste interactive
        </div>
      )}
    </div>
  );
}

function renderBody(message, { onAudioTranscript } = {}) {
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
    const result = RichMediaBubble({ message, messageType: displayType, onAudioTranscript });
    return result;
  }

  // Messages interactifs
  if (messageType === "interactive") {
    // Parser interactive_data pour extraire les boutons
    let buttons = [];
    if (message.interactive_data) {
      try {
        const interactiveData = typeof message.interactive_data === 'string' 
          ? JSON.parse(message.interactive_data) 
          : message.interactive_data;
        
        // Extraire les boutons depuis action
        if (interactiveData.action) {
          if (interactiveData.action.buttons && Array.isArray(interactiveData.action.buttons)) {
            // Format pour messages interactifs: {type: "reply", reply: {id: "...", title: "..."}}
            buttons = interactiveData.action.buttons.map(btn => ({
              text: btn.reply?.title || btn.text || '',
              type: btn.type || 'reply'
            }));
          }
        }
        
        // Si les boutons sont directement dans interactiveData.buttons (format template)
        if (interactiveData.buttons && Array.isArray(interactiveData.buttons) && buttons.length === 0) {
          buttons = interactiveData.buttons.map(btn => ({
            text: btn.text || btn.reply?.title || '',
            type: btn.type || 'QUICK_REPLY',
            url: btn.url || '',
            phone_number: btn.phone_number || ''
          }));
        }
      } catch (e) {
        console.warn('Error parsing interactive_data for buttons:', e);
      }
    }
    
    // Si on n'a pas de boutons dans interactive_data, essayer de parser le content_text
    if (buttons.length === 0) {
      const content = message.content_text || "";
      const buttonInfo = content.split("\n").find(line => line.startsWith("[Boutons:"));
      if (buttonInfo) {
        const buttonsMatch = buttonInfo.match(/\[Boutons: (.*)\]/);
        if (buttonsMatch) {
          const buttonTitles = buttonsMatch[1].split(", ");
          buttons = buttonTitles.map(title => ({ text: title, type: 'reply' }));
        }
      }
    }
    
    return { 
      content: <InteractiveBubble message={message} />, 
      buttons: buttons.length > 0 ? (
        <div className="bubble-media__buttons-container">
          {buttons.map((button, index) => (
            <div
              key={`${message.id}-int-btn-${button.reply?.id || button.text || index}`}
              className="bubble-media__button"
            >
              <FiArrowLeft className="bubble-media__button-icon" />
              <span className="bubble-media__button-text">
                {button.text || button.title || ''}
              </span>
            </div>
          ))}
        </div>
      ) : null
    };
  }

  if (!typeEntry || messageType === "text" || messageType === "template") {
    // Préserver les retours à la ligne pour les templates et textes
    const text = message.content_text || "";
    const lines = text.split('\n');
    return {
      content: (
        <span className="bubble__text">
          {lines.map((line, index) => (
            <span key={`${message.id}-line-${index}`}>
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
      <div
        className={`bubble-media${messageType === "unsupported" ? " bubble-media--unsupported" : ""}`}
      >
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

function MessageBubbleInner({ message, conversation, onReactionChange, onContextMenu, forceReactionOpen = false, onResend, onReply, onCopy, onPin, onUnpin, onDelete, onOpenMenu, onAudioTranscript }) {
  const mine = message.direction === "outbound";
  const timestamp = message.timestamp ? formatRelativeDateTime(message.timestamp) : "";
  const timestampDetail = (() => {
    const d = message.timestamp ? parseDateAsUTC(message.timestamp) : null;
    if (!d) return undefined;
    return d.toLocaleString("fr-FR", {
      timeZone: "Europe/Paris",
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  })();

  const messageType = (message.message_type || "text").toLowerCase();
  const hasMedia = message.media_id || message.storage_url;
  // Un template avec image : message_type === "image" avec template_name OU message_type === "template" avec storage_url
  const isTemplateWithImage = (messageType === "image" && message.template_name) || 
                               (messageType === "template" && hasMedia);
  const isMedia = (FETCHABLE_MEDIA.has(messageType) || isTemplateWithImage) && hasMedia;
  const isDeletedForAll = !!message.deleted_for_all_at;
  const isEdited = !!message.edited_at;
  const isPinned = !!message.is_pinned;
  
  const [showMenuIcon, setShowMenuIcon] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const menuRef = useRef(null);
  const menuIconRef = useRef(null);

  const bodyResult = renderBody(message, { onAudioTranscript });
  const bodyContent = bodyResult?.content || bodyResult;
  const buttons = bodyResult?.buttons || null;

  // Récupérer le message cité (quoted message)
  const quotedMessage = message.reply_to_message;

  const calculateMenuPosition = (elementRect, menuWidth = 200) => {
    const menuHeight = 300; // Hauteur approximative du menu (réactions + options)
    const windowHeight = window.innerHeight;
    const windowWidth = window.innerWidth;
    const spaceBelow = windowHeight - elementRect.bottom;
    const spaceAbove = elementRect.top;
    
    // Si pas assez d'espace en dessous mais assez au-dessus, afficher au-dessus
    const showAbove = spaceBelow < menuHeight && spaceAbove > menuHeight;
    
    // Positionner le menu en dessous ou au-dessus selon l'espace disponible
    let newPosition = {
      top: showAbove ? elementRect.top - menuHeight + 46 : elementRect.bottom + 8,
      left: mine ? elementRect.left : elementRect.right - menuWidth,
    };
    
    // S'assurer que le menu ne dépasse pas à droite
    const padding = 8;
    if (newPosition.left + menuWidth > windowWidth - padding) {
      newPosition.left = windowWidth - menuWidth - padding;
    }
    
    // S'assurer que le menu ne dépasse pas à gauche
    if (newPosition.left < padding) {
      newPosition.left = padding;
    }
    
    return newPosition;
  };

  // Fermer le menu quand on clique ailleurs
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false);
      }
    }
    if (showMenu) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showMenu]);

  // Ajuster la position du menu après le rendu pour éviter le débordement
  useEffect(() => {
    if (showMenu && menuRef.current && menuIconRef.current) {
      // Utiliser requestAnimationFrame pour s'assurer que le menu est rendu
      requestAnimationFrame(() => {
        if (menuRef.current && menuIconRef.current) {
          const menuRect = menuRef.current.getBoundingClientRect();
          const iconRect = menuIconRef.current.getBoundingClientRect();
          const menuWidth = menuRect.width;
          const windowWidth = window.innerWidth;
          const padding = 8;
          
          // Vérifier si le menu dépasse à droite
          const currentLeft = menuRect.left;
          const maxLeft = windowWidth - menuWidth - padding;
          
          if (currentLeft > maxLeft || currentLeft < padding) {
            // Recalculer la position avec la largeur réelle du menu
            const virtualRect = {
              top: iconRect.top,
              bottom: iconRect.bottom,
              left: iconRect.left,
              right: iconRect.right,
            };
            
            const adjustedPosition = calculateMenuPosition(virtualRect, menuWidth);
            setMenuPosition(adjustedPosition);
          }
        }
      });
    }
  }, [showMenu]);

  const handleMenuClick = (e) => {
    e.stopPropagation();
    if (menuIconRef.current) {
      const rect = menuIconRef.current.getBoundingClientRect();
      setMenuPosition(calculateMenuPosition(rect));
    }
    setShowMenu(!showMenu);
  };

  // Gérer le clic droit pour ouvrir le même menu
  const handleRightClick = (e) => {
    if (onContextMenu) {
      e.preventDefault();
      // Calculer la position du menu basée sur la position du clic
      const clickX = e.clientX;
      const clickY = e.clientY;
      
      // Créer un rectangle virtuel pour la position du menu
      const virtualRect = {
        top: clickY,
        bottom: clickY,
        left: clickX,
        right: clickX,
      };
      
      setMenuPosition(calculateMenuPosition(virtualRect));
      setShowMenu(true);
      
      // Appeler le callback si fourni
      if (onOpenMenu) {
        onOpenMenu(message);
      }
    }
  };

  const handleMenuAction = (action, e) => {
    e.stopPropagation();
    setShowMenu(false);
    
    switch (action) {
      case "reply":
        onReply?.(message);
        break;
      case "copy":
        onCopy?.(message);
        break;
      case "pin":
        onPin?.(message);
        break;
      case "unpin":
        onUnpin?.(message);
        break;
      case "delete":
        onDelete?.(message);
        break;
      default:
        break;
    }
  };

  // Fonction pour rendre le message cité de manière compacte
  const renderQuotedMessage = (quotedMsg) => {
    if (!quotedMsg) return null;

    // Extraire le texte à afficher
    let quotedText = quotedMsg.content_text || "";
    
    // Si c'est un message interactif, extraire header, body, footer
    if (quotedMsg.interactive_data) {
      try {
        const interactiveData = typeof quotedMsg.interactive_data === 'string' 
          ? JSON.parse(quotedMsg.interactive_data) 
          : quotedMsg.interactive_data;
        
        const parts = [];
        if (interactiveData.header) parts.push(interactiveData.header);
        if (interactiveData.body) parts.push(interactiveData.body);
        if (interactiveData.footer) parts.push(interactiveData.footer);
        
        if (parts.length > 0) {
          quotedText = parts.join("\n");
        }
      } catch (e) {
        console.warn('Error parsing quoted message interactive_data:', e);
      }
    }

    // Limiter la longueur pour l'affichage compact
    const maxLength = 100;
    const displayText = quotedText.length > maxLength 
      ? quotedText.substring(0, maxLength) + "..." 
      : quotedText;

    // Déterminer si c'est un message sortant ou entrant
    const quotedMine = quotedMsg.direction === "outbound";
    const quotedName = quotedMine ? "Vous" : (conversation?.contacts?.display_name || "Contact");

    return (
      <div className="bubble__quoted-message">
        <div className="bubble__quoted-message-indicator"></div>
        <div className="bubble__quoted-message-content">
          <div className="bubble__quoted-message-author">{quotedName}</div>
          <div className="bubble__quoted-message-text">{displayText}</div>
        </div>
      </div>
    );
  };

  return (
    <div 
      className="message-with-buttons-wrapper"
      onMouseEnter={() => !isDeletedForAll && setShowMenuIcon(true)}
      onMouseLeave={() => setShowMenuIcon(false)}
      style={{ position: "relative" }}
    >
      <div
        className={`bubble ${mine ? "me" : "them"} ${isMedia ? "bubble--media" : ""} ${isDeletedForAll ? "bubble--deleted" : ""} ${isPinned ? "bubble--pinned" : ""} ${buttons ? "bubble--with-buttons" : ""} ${quotedMessage ? "bubble--with-quote" : ""}`}
        onContextMenu={handleRightClick}
        style={{ position: "relative" }}
      >
        {isPinned && (
          <div className="bubble__pinned-indicator" title="Message épinglé">
            <MdPushPin />
          </div>
        )}
        {/* Icône de menu au hover pour tous les messages */}
        {!isDeletedForAll && showMenuIcon && (
          <div className="bubble__menu-icon-wrapper">
            <button
              ref={menuIconRef}
              className="bubble__menu-icon"
              onClick={handleMenuClick}
              aria-label="Options du message"
            >
              <FiMoreVertical />
            </button>
          </div>
        )}
        {/* Menu contextuel en position fixed pour éviter d'être coupé */}
        {showMenu && !isDeletedForAll && (
          <>
            <div 
              className="bubble__menu-overlay"
              onClick={() => setShowMenu(false)}
            />
            <div 
              className="bubble__menu"
              style={{
                top: `${menuPosition.top}px`,
                left: `${menuPosition.left}px`,
              }}
              ref={menuRef}
              onClick={(e) => e.stopPropagation()}
            >
                {/* Réactions en haut */}
                <div className="bubble__menu-reactions">
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      // Ajouter réaction 👍
                      if (onReactionChange) {
                        onReactionChange(message.id, "👍");
                      }
                    }}
                    title="👍"
                  >
                    👍
                  </button>
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      if (onReactionChange) {
                        onReactionChange(message.id, "❤️");
                      }
                    }}
                    title="❤️"
                  >
                    ❤️
                  </button>
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      if (onReactionChange) {
                        onReactionChange(message.id, "😂");
                      }
                    }}
                    title="😂"
                  >
                    😂
                  </button>
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      if (onReactionChange) {
                        onReactionChange(message.id, "😮");
                      }
                    }}
                    title="😮"
                  >
                    😮
                  </button>
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      if (onReactionChange) {
                        onReactionChange(message.id, "😥");
                      }
                    }}
                    title="😥"
                  >
                    😥
                  </button>
                  <button
                    className="bubble__menu-reaction"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      if (onReactionChange) {
                        onReactionChange(message.id, "🙏");
                      }
                    }}
                    title="🙏"
                  >
                    🙏
                  </button>
                  <button
                    className="bubble__menu-reaction bubble__menu-reaction--more"
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                      // Ouvrir le sélecteur de réactions
                      if (onContextMenu) {
                        const fakeEvent = { preventDefault: () => {}, stopPropagation: () => {} };
                        onContextMenu(fakeEvent, message);
                      }
                    }}
                    title="Plus de réactions"
                  >
                    +
                  </button>
                </div>
                {/* Options du menu */}
                <div className="bubble__menu-divider"></div>
                <button
                  className="bubble__menu-item"
                  onClick={(e) => handleMenuAction("reply", e)}
                >
                  <FiCornerUpLeft />
                  <span>Répondre</span>
                </button>
                <button
                  className="bubble__menu-item"
                  onClick={(e) => handleMenuAction("copy", e)}
                >
                  <FiCopy />
                  <span>Copier</span>
                </button>
                {isPinned ? (
                  <button
                    className="bubble__menu-item"
                    onClick={(e) => handleMenuAction("unpin", e)}
                  >
                    <MdPushPin />
                    <span>Désépingler</span>
                  </button>
                ) : (
                  <button
                    className="bubble__menu-item"
                    onClick={(e) => handleMenuAction("pin", e)}
                  >
                    <MdPushPin />
                    <span>Épingler</span>
                  </button>
                )}
                <button
                  className="bubble__menu-item bubble__menu-item--danger"
                  onClick={(e) => handleMenuAction("delete", e)}
                >
                  <FiTrash2 />
                  <span>Supprimer</span>
                </button>
              </div>
            </>
        )}
        {isDeletedForAll ? (
          <span className="bubble__text bubble__text--deleted">
            {mine ? "Vous avez supprimé ce message" : "Ce message a été supprimé"}
          </span>
        ) : (
          <>
            <OutboundAttribution message={message} />
            {quotedMessage && renderQuotedMessage(quotedMessage)}
            {bodyContent}
            {buttons && (
              <div className="bubble__buttons">
                {buttons}
              </div>
            )}
          </>
        )}
        <div className="bubble__footer">
          <div className="bubble__footer-left">
            <small className="bubble__timestamp" title={timestampDetail}>
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
    </div>
  );
}

const MessageBubble = memo(MessageBubbleInner, (prev, next) => {
  return (
    prev.message.id === next.message.id &&
    prev.message.status === next.message.status &&
    prev.message.content_text === next.message.content_text &&
    prev.message.audio_transcript === next.message.audio_transcript &&
    prev.message.storage_url === next.message.storage_url &&
    prev.message.is_pinned === next.message.is_pinned &&
    prev.message.reactions === next.message.reactions &&
    prev.message.sent_via === next.message.sent_via &&
    prev.message.sent_by_user_id === next.message.sent_by_user_id &&
    JSON.stringify(prev.message.outbound_meta ?? null) ===
      JSON.stringify(next.message.outbound_meta ?? null) &&
    prev.forceReactionOpen === next.forceReactionOpen &&
    prev.conversation?.id === next.conversation?.id &&
    prev.onAudioTranscript === next.onAudioTranscript
  );
});

export default MessageBubble;