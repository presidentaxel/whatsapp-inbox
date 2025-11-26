import { useEffect, useState } from "react";
import {
  FiHeadphones,
  FiImage,
  FiVideo,
  FiFileText,
  FiMapPin,
  FiMessageSquare,
  FiPhone,
  FiList,
} from "react-icons/fi";
import { api } from "../../api/axiosClient";

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
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!message.media_id || !FETCHABLE_MEDIA.has(messageType)) {
      setSource(null);
      setLoading(false);
      onLoadingChange?.(false, false);
      return;
    }

    let cancelled = false;
    let objectUrl = null;

    api
      .get(`/messages/media/${message.id}`, { responseType: "blob" })
      .then((res) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(res.data);
        setSource(objectUrl);
        setError(false);
        onLoadingChange?.(false, false);
      })
      .catch(() => {
        if (!cancelled) {
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
  }, [message.id, message.media_id, messageType]);

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
    return (
      <a href={source} download className="bubble-media__document" target="_blank" rel="noreferrer">
        📄 Télécharger le document
      </a>
    );
  }

  return <span>{message.content_text}</span>;
}

function RichMediaBubble({ message, messageType }) {
  const [showIcon, setShowIcon] = useState(true);
  const typeEntry = TYPE_MAP[messageType];

  // Ne pas afficher le content_text s'il contient juste un placeholder
  const isPlaceholder = message.content_text && 
    (message.content_text.trim() === '[image]' || 
     message.content_text.trim() === '[audio]' ||
     message.content_text.trim() === '[video]' ||
     message.content_text.trim() === '[document]');
  
  const caption = isPlaceholder ? null : message.content_text;

  const handleLoadingChange = (loading, error) => {
    // Cacher l'icône si l'image/vidéo est chargée sans erreur
    if (messageType === 'image' || messageType === 'video' || messageType === 'sticker') {
      setShowIcon(loading || error);
    }
  };

    return (
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
        {caption && <p className="bubble-media__caption">{caption}</p>}
      </div>
    </div>
  );
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
  return <span>{content}</span>;
}

function renderBody(message) {
  const messageType = (message.message_type || "text").toLowerCase();
  const typeEntry = TYPE_MAP[messageType];

  if (FETCHABLE_MEDIA.has(messageType) && message.media_id) {
    return <RichMediaBubble message={message} messageType={messageType} />;
  }

  // Messages interactifs
  if (messageType === "interactive") {
    return <InteractiveBubble message={message} />;
  }

  if (!typeEntry || messageType === "text") {
    return <span>{message.content_text}</span>;
  }

  return (
    <div className="bubble-media">
      <div className="bubble-media__icon">{typeEntry.icon}</div>
      <div className="bubble-media__content">
        <strong>{typeEntry.label}</strong>
        {message.content_text && <p>{message.content_text}</p>}
      </div>
    </div>
  );
}

export default function MessageBubble({ message }) {
  const mine = message.direction === "outbound";
  const timestamp = message.timestamp
    ? new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";

  const messageType = (message.message_type || "text").toLowerCase();
  const isMedia = FETCHABLE_MEDIA.has(messageType) && message.media_id;

  return (
    <div className={`bubble ${mine ? "me" : "them"} ${isMedia ? "bubble--media" : ""}`}>
      {renderBody(message)}
      <small className="bubble__timestamp">{timestamp}</small>
    </div>
  );
}