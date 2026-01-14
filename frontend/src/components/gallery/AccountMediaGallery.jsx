import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { FiImage, FiVideo, FiFileText, FiDownload, FiX } from "react-icons/fi";
import { getAccountMediaGallery } from "../../api/messagesApi";
import { supabaseClient } from "../../api/supabaseClient";
import PDFThumbnail from "./PDFThumbnail";
import "./AccountMediaGallery.css";

// Composant wrapper pour gérer le fallback si le PDF ne charge pas
function PDFThumbnailWrapper({ item, onDownload, getMediaIcon }) {
  const [pdfError, setPdfError] = useState(false);

  if (pdfError) {
    // Fallback: afficher l'icône si le PDF ne peut pas être chargé
    return (
      <div className="account-media-gallery__thumbnail account-media-gallery__thumbnail--non-image">
        <div className="account-media-gallery__icon">{getMediaIcon(item.type)}</div>
        <div className="account-media-gallery__non-image-label">PDF</div>
        <div className="account-media-gallery__overlay">
          <button
            className="account-media-gallery__download-btn"
            onClick={(e) => onDownload(item, e)}
            title="Télécharger"
          >
            <FiDownload />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="account-media-gallery__thumbnail account-media-gallery__thumbnail--pdf">
      <PDFThumbnail 
        url={item.url} 
        width={200} 
        height={200}
        onError={() => setPdfError(true)}
      />
      <div className="account-media-gallery__overlay">
        <button
          className="account-media-gallery__download-btn"
          onClick={(e) => onDownload(item, e)}
          title="Télécharger"
        >
          <FiDownload />
        </button>
      </div>
    </div>
  );
}

export default function AccountMediaGallery({ accountId, mediaType = "image" }) {
  const [mediaItems, setMediaItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedMedia, setSelectedMedia] = useState(null);
  const [error, setError] = useState(null);

  // Fonction pour charger la galerie
  const loadGallery = useCallback(() => {
    if (!accountId) {
      setMediaItems([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    getAccountMediaGallery(accountId, mediaType, 500)
      .then((res) => {
        setMediaItems(res.data?.items || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error loading account media gallery:", err);
        setError("Erreur lors du chargement de la galerie");
        setLoading(false);
      });
  }, [accountId, mediaType]);

  // Charger la galerie au montage et quand accountId/mediaType change
  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  // Écouter les changements de messages via Supabase Realtime pour rafraîchir automatiquement
  useEffect(() => {
    if (!accountId) {
      return;
    }

    // Types de médias supportés selon le mediaType
    const mediaTypes = {
      image: ["image", "sticker"],
      video: ["video"],
      document: ["document"],
      audio: ["audio", "voice"],
      all: ["image", "video", "document", "audio", "sticker", "voice"]
    };
    
    const supportedTypes = mediaTypes[mediaType] || mediaTypes.image;

    // Écouter tous les messages et filtrer côté client par account_id via conversations
    // Note: On écoute tous les messages car Supabase Realtime ne supporte pas les filtres complexes
    const channel = supabaseClient
      .channel(`account-media-gallery:${accountId}:${mediaType}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
        },
        async (payload) => {
          const newMessage = payload.new;
          // Vérifier si le message appartient à ce compte en vérifiant la conversation
          if (supportedTypes.includes(newMessage.message_type?.toLowerCase())) {
            const { data: conv } = await supabaseClient
              .from("conversations")
              .select("account_id")
              .eq("id", newMessage.conversation_id)
              .single();
            
            if (conv && conv.account_id === accountId) {
              console.log("🔄 [ACCOUNT GALLERY] New media detected, refreshing gallery");
              setTimeout(() => {
                loadGallery();
              }, 1000);
            }
          }
        }
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "messages",
        },
        async (payload) => {
          const updatedMessage = payload.new;
          if (
            supportedTypes.includes(updatedMessage.message_type?.toLowerCase()) &&
            updatedMessage.storage_url
          ) {
            // Vérifier si le message appartient à ce compte
            const { data: conv } = await supabaseClient
              .from("conversations")
              .select("account_id")
              .eq("id", updatedMessage.conversation_id)
              .single();
            
            if (conv && conv.account_id === accountId) {
              console.log("🔄 [ACCOUNT GALLERY] Media storage_url updated, refreshing gallery");
              loadGallery();
            }
          }
        }
      )
      .subscribe();

    return () => {
      supabaseClient.removeChannel(channel);
    };
  }, [accountId, mediaType, loadGallery]);

  // Fonction pour vérifier si un fichier est un PDF
  const isPDF = (item) => {
    if (!item || !item.url) return false;
    const type = item.type?.toLowerCase();
    const url = item.url.toLowerCase();
    return type === "document" && (url.endsWith(".pdf") || url.includes(".pdf") || url.includes("application/pdf"));
  };

  // Fonction pour tronquer la caption si elle est trop longue
  const truncateCaption = (caption, maxLength = 80) => {
    if (!caption) return "";
    if (caption.length <= maxLength) return caption;
    return caption.substring(0, maxLength) + "...";
  };

  const handleImageClick = (item) => {
    setSelectedMedia(item);
  };

  const handleCloseModal = () => {
    setSelectedMedia(null);
  };

  const getFileExtension = (item) => {
    // Essayer d'extraire l'extension depuis l'URL
    if (item.url) {
      const urlMatch = item.url.match(/\.([a-zA-Z0-9]+)(?:[?#]|$)/);
      if (urlMatch) {
        return urlMatch[1];
      }
    }
    
    // Sinon, déterminer par type de message
    switch (item.type?.toLowerCase()) {
      case "image":
      case "sticker":
        return "jpg";
      case "video":
        return "mp4";
      case "document":
        return "pdf";
      case "audio":
      case "voice":
        return "mp3";
      default:
        return "bin";
    }
  };

  const handleDownload = (item, event) => {
    if (event) {
      event.stopPropagation();
    }
    if (item.url) {
      const extension = getFileExtension(item);
      const link = document.createElement("a");
      link.href = item.url;
      link.download = `${item.message_id}.${extension}`;
      link.target = "_blank";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const getMediaIcon = (type) => {
    switch (type?.toLowerCase()) {
      case "image":
      case "sticker":
        return <FiImage />;
      case "video":
        return <FiVideo />;
      case "document":
        return <FiFileText />;
      case "audio":
      case "voice":
        return <FiFileText />;
      default:
        return <FiFileText />;
    }
  };

  const getThumbnailUrl = (url) => {
    if (!url) return url;
    
    if (url.includes("supabase.co/storage")) {
      const separator = url.includes("?") ? "&" : "?";
      return `${url}${separator}width=200&height=200&resize=cover&quality=80`;
    }
    
    return url;
  };

  if (loading) {
    return (
      <div className="account-media-gallery">
        <div className="account-media-gallery__loading">Chargement...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="account-media-gallery">
        <div className="account-media-gallery__error">{error}</div>
      </div>
    );
  }

  if (mediaItems.length === 0) {
    return (
      <div className="account-media-gallery">
        <div className="account-media-gallery__empty">
          Aucun {mediaType === "image" ? "image" : mediaType === "video" ? "vidéo" : mediaType === "document" ? "document" : mediaType === "all" ? "média" : "élément"} dans ce compte
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="account-media-gallery">
        <div className="account-media-gallery__header">
          <h3>{mediaItems.length} {mediaType === "image" ? "images" : mediaType === "video" ? "vidéos" : mediaType === "document" ? "documents" : mediaType === "all" ? "médias" : "éléments"}</h3>
        </div>
        <div className="account-media-gallery__grid">
          {mediaItems.map((item) => (
            <div
              key={item.id}
              className="account-media-gallery__item"
              onClick={() => handleImageClick(item)}
            >
              {item.type?.toLowerCase() === "image" || item.type?.toLowerCase() === "sticker" ? (
                <div className="account-media-gallery__thumbnail">
                  <img
                    src={getThumbnailUrl(item.url)}
                    alt={item.caption || "Image"}
                    loading="lazy"
                    onError={(e) => {
                      e.target.style.display = "none";
                      e.target.parentElement.innerHTML = `<div class="account-media-gallery__icon">${getMediaIcon(item.type)}</div>`;
                    }}
                  />
                  <div className="account-media-gallery__overlay">
                    <button
                      className="account-media-gallery__download-btn"
                      onClick={(e) => handleDownload(item, e)}
                      title="Télécharger en qualité complète"
                    >
                      <FiDownload />
                    </button>
                  </div>
                </div>
              ) : item.type?.toLowerCase() === "document" && item.url && (item.url.toLowerCase().endsWith(".pdf") || item.url.includes(".pdf")) ? (
                <PDFThumbnailWrapper
                  item={item}
                  onDownload={handleDownload}
                  getMediaIcon={getMediaIcon}
                />
              ) : (
                <div className="account-media-gallery__thumbnail account-media-gallery__thumbnail--non-image">
                  {item.type?.toLowerCase() === "video" && item.url ? (
                    <video
                      src={item.url}
                      className="account-media-gallery__video-thumbnail"
                      muted
                      preload="metadata"
                    />
                  ) : null}
                  <div className="account-media-gallery__icon">{getMediaIcon(item.type)}</div>
                  <div className="account-media-gallery__non-image-label">
                    {item.type === "document" ? "PDF" : 
                     item.type === "video" ? "Vidéo" : 
                     item.type === "audio" || item.type === "voice" ? "Audio" : 
                     item.type || "Fichier"}
                  </div>
                  <div className="account-media-gallery__overlay">
                    <button
                      className="account-media-gallery__download-btn"
                      onClick={(e) => handleDownload(item, e)}
                      title="Télécharger"
                    >
                      <FiDownload />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Modal pour afficher le média en grand */}
      {selectedMedia && 
        createPortal(
          <div className="account-media-gallery__modal" onClick={handleCloseModal}>
            <div className="account-media-gallery__modal-content" onClick={(e) => e.stopPropagation()}>
              <button className="account-media-gallery__modal-close" onClick={handleCloseModal}>
                <FiX />
              </button>
              {(selectedMedia.type?.toLowerCase() === "image" || selectedMedia.type?.toLowerCase() === "sticker") ? (
                <>
                  <img
                    src={selectedMedia.url}
                    alt={selectedMedia.caption || "Image"}
                    className="account-media-gallery__modal-image"
                  />
                  {selectedMedia.caption && (
                    <div className="account-media-gallery__modal-caption" title={selectedMedia.caption}>
                      {truncateCaption(selectedMedia.caption)}
                    </div>
                  )}
                  <button
                    className="account-media-gallery__modal-download"
                    onClick={(e) => handleDownload(selectedMedia, e)}
                  >
                    <FiDownload /> Télécharger en qualité complète
                  </button>
                </>
              ) : selectedMedia.type?.toLowerCase() === "video" ? (
                <>
                  <video
                    src={selectedMedia.url}
                    controls
                    className="account-media-gallery__modal-video"
                  />
                  {selectedMedia.caption && (
                    <div className="account-media-gallery__modal-caption" title={selectedMedia.caption}>
                      {truncateCaption(selectedMedia.caption)}
                    </div>
                  )}
                  <button
                    className="account-media-gallery__modal-download"
                    onClick={(e) => handleDownload(selectedMedia, e)}
                  >
                    <FiDownload /> Télécharger
                  </button>
                </>
              ) : isPDF(selectedMedia) ? (
                <>
                  <iframe
                    src={selectedMedia.url}
                    className="account-media-gallery__modal-pdf"
                    title="PDF Viewer"
                    allow="fullscreen"
                  />
                  {selectedMedia.caption && (
                    <div className="account-media-gallery__modal-caption" title={selectedMedia.caption}>
                      {truncateCaption(selectedMedia.caption)}
                    </div>
                  )}
                  <button
                    className="account-media-gallery__modal-download"
                    onClick={(e) => handleDownload(selectedMedia, e)}
                  >
                    <FiDownload /> Télécharger
                  </button>
                </>
              ) : (
                <>
                  <div className="account-media-gallery__modal-document">
                    <div className="account-media-gallery__modal-document-icon">
                      {getMediaIcon(selectedMedia.type)}
                    </div>
                    <div className="account-media-gallery__modal-document-label">
                      {selectedMedia.type === "document" ? "Document PDF" : 
                       selectedMedia.type === "audio" || selectedMedia.type === "voice" ? "Fichier audio" : 
                       "Fichier"}
                    </div>
                    {selectedMedia.caption && (
                      <div className="account-media-gallery__modal-caption">{selectedMedia.caption}</div>
                    )}
                  </div>
                  <button
                    className="account-media-gallery__modal-download"
                    onClick={(e) => handleDownload(selectedMedia, e)}
                  >
                    <FiDownload /> Télécharger
                  </button>
                </>
              )}
            </div>
          </div>,
          document.body
        )
      }
    </>
  );
}

