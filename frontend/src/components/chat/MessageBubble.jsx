import { useEffect, useState } from "react";
import {
  FiHeadphones,
  FiImage,
  FiVideo,
  FiFileText,
  FiMapPin,
  FiMessageSquare,
  FiPhone,
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

function MediaRenderer({ message, messageType }) {
  const [source, setSource] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!message.media_id || !FETCHABLE_MEDIA.has(messageType)) {
      setSource(null);
      setLoading(false);
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
      })
      .catch(() => {
        if (!cancelled) {
          setSource(null);
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
    return <span>Chargement…</span>;
  }

  if (!source) {
    return <span>{message.content_text || "Média non disponible"}</span>;
  }

  if (messageType === "image" || messageType === "sticker") {
    return <img src={source} alt={message.content_text || "Image reçue"} className="bubble-media__preview" />;
  }

  if (messageType === "video") {
    return <video src={source} controls className="bubble-media__preview" />;
  }

  if (messageType === "audio" || messageType === "voice") {
    return <audio src={source} controls />;
  }

  if (messageType === "document") {
    return (
      <a href={source} target="_blank" rel="noreferrer">
        Télécharger le document
      </a>
    );
  }

  return <span>{message.content_text}</span>;
}

function renderBody(message) {
  const messageType = (message.message_type || "text").toLowerCase();
  const typeEntry = TYPE_MAP[messageType];

  if (FETCHABLE_MEDIA.has(messageType) && message.media_id) {
    return (
      <div className="bubble-media bubble-media--rich">
        <div className="bubble-media__icon">{typeEntry?.icon}</div>
        <div className="bubble-media__content">
          <strong>{typeEntry?.label}</strong>
          <MediaRenderer message={message} messageType={messageType} />
          {message.content_text && <p>{message.content_text}</p>}
        </div>
      </div>
    );
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

  return (
    <div className={`bubble ${mine ? "me" : "them"}`}>
      {renderBody(message)}
      <small>{timestamp}</small>
    </div>
  );
}