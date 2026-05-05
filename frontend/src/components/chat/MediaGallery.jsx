import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { FiImage, FiVideo, FiFileText, FiDownload, FiX } from "react-icons/fi";
import { getConversationMediaGallery } from "../../api/messagesApi";
import { supabaseClient } from "../../api/supabaseClient";
import { devLog } from "../../utils/devLog";
import "./MediaGallery.css";

export default function MediaGallery({ conversationId, mediaType = "image" }) {
  const [mediaItems, setMediaItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedMedia, setSelectedMedia] = useState(null);
  const [error, setError] = useState(null);

  // Fonction pour charger la galerie
  const loadGallery = useCallback(() => {
    if (!conversationId) {
      setMediaItems([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    getConversationMediaGallery(conversationId, mediaType, 100)
      .then((res) => {
        setMediaItems(res.data?.items || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error loading media gallery:", err);
        setError("Erreur lors du chargement de la galerie");
        setLoading(false);
      });
  }, [conversationId, mediaType]);

  // Charger la galerie au montage et quand conversationId/mediaType change
  useEffect(() => {
    loadGallery();
  }, [loadGallery]);

  // Écouter les changements de messages via Supabase Realtime pour rafraîchir automatiquement
  useEffect(() => {
    if (!conversationId) {
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

    const channel = supabaseClient
      .channel(`media-gallery:${conversationId}:${mediaType}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `conversation_id=eq.${conversationId}`,
        },
        (payload) => {
          const newMessage = payload.new;
          // Vérifier si c'est un média du type supporté
          if (supportedTypes.includes(newMessage.message_type?.toLowerCase())) {
            devLog("🔄 [MEDIA GALLERY] New media message detected, refreshing gallery");
            // Rafraîchir la galerie après un court délai pour laisser le temps au storage_url d'être mis à jour
            setTimeout(() => {
              loadGallery();
            }, 1000);
          }
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
          const updatedMessage = payload.new;
          // Si un message a obtenu un storage_url (téléchargement terminé), rafraîchir
          if (
            supportedTypes.includes(updatedMessage.message_type?.toLowerCase()) &&
            updatedMessage.storage_url
          ) {
            devLog("🔄 [MEDIA GALLERY] Media storage_url updated, refreshing gallery");
            loadGallery();
          }
        }
      )
      .subscribe();

    return () => {
      supabaseClient.removeChannel(channel);
    };
  }, [conversationId, mediaType, loadGallery]);

  const handleImageClick = (item) => {
    setSelectedMedia(item);
  };

  const handleCloseModal = () => {
    setSelectedMedia(null);
  };

  const handleDownload = (item, event) => {
    event.stopPropagation();
    if (item.url) {
      // Créer un lien de téléchargement
      const link = document.createElement("a");
      link.href = item.url;
      link.download = `${item.message_id}.${item.type === "image" ? "jpg" : item.type === "video" ? "mp4" : "pdf"}`;
      link.target = "_blank";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  const getMediaIcon = (type) => {
    switch (type) {
      case "image":
      case "sticker":
        return <FiImage />;
      case "video":
        return <FiVideo />;
      case "document":
        return <FiFileText />;
      default:
        return <FiFileText />;
    }
  };

  // Génère une URL de thumbnail compressé pour Supabase Storage
  // Utilise les transformations d'image de Supabase pour créer un thumbnail de 200x200px
  const getThumbnailUrl = (url) => {
    if (!url) return url;
    
    // Si c'est une URL Supabase Storage, ajouter les paramètres de transformation
    if (url.includes("supabase.co/storage")) {
      // Ajouter les paramètres de transformation d'image pour créer un thumbnail
      // width=200&height=200&resize=cover&quality=80 pour économiser la bande passante
      const separator = url.includes("?") ? "&" : "?";
      return `${url}${separator}width=200&height=200&resize=cover&quality=80`;
    }
    
    // Sinon, retourner l'URL originale
    return url;
  };

  if (loading) {
    return (
      <div className="media-gallery">
        <div className="media-gallery__loading">Chargement...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="media-gallery">
        <div className="media-gallery__error">{error}</div>
      </div>
    );
  }

  if (mediaItems.length === 0) {
    return (
      <div className="media-gallery">
        <div className="media-gallery__empty">
          Aucun {mediaType === "image" ? "image" : mediaType === "video" ? "vidéo" : "document"} dans cette conversation
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="media-gallery">
        <div className="media-gallery__grid">
          {mediaItems.map((item) => {
            const itemType = (item.type || "").toLowerCase();
            return (
              <div
                key={item.id}
                className="media-gallery__item"
                onClick={() => handleImageClick(item)}
              >
                {itemType === "image" || itemType === "sticker" ? (
                <div className="media-gallery__thumbnail">
                  <img
                    src={getThumbnailUrl(item.url)}
                    alt={item.caption || "Image"}
                    loading="lazy"
                    onError={(e) => {
                      // Si l'image ne charge pas, afficher une icône
                      e.target.style.display = "none";
                      e.target.parentElement.innerHTML = `<div class="media-gallery__icon">${getMediaIcon(item.type)}</div>`;
                    }}
                  />
                  <div className="media-gallery__overlay">
                    <button
                      className="media-gallery__download-btn"
                      onClick={(e) => handleDownload(item, e)}
                      title="Télécharger en qualité complète"
                    >
                      <FiDownload />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="media-gallery__thumbnail media-gallery__thumbnail--non-image">
                  <div className="media-gallery__icon">{getMediaIcon(item.type)}</div>
                  <button
                    className="media-gallery__download-btn"
                    onClick={(e) => handleDownload(item, e)}
                    title="Télécharger"
                  >
                    <FiDownload />
                  </button>
                </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Modal pour afficher l'image en grand - rendue via Portal pour échapper au contexte de stacking */}
      {selectedMedia && (selectedMedia.type === "image" || selectedMedia.type === "sticker") && 
        createPortal(
          <div className="media-gallery__modal" onClick={handleCloseModal}>
            <div className="media-gallery__modal-content" onClick={(e) => e.stopPropagation()}>
              <button className="media-gallery__modal-close" onClick={handleCloseModal}>
                <FiX />
              </button>
              <img
                src={selectedMedia.url}
                alt={selectedMedia.caption || "Image"}
                className="media-gallery__modal-image"
              />
              {selectedMedia.caption && (
                <div className="media-gallery__modal-caption">{selectedMedia.caption}</div>
              )}
              <button
                className="media-gallery__modal-download"
                onClick={(e) => handleDownload(selectedMedia, e)}
              >
                <FiDownload /> Télécharger en qualité complète
              </button>
            </div>
          </div>,
          document.body
        )
      }
    </>
  );
}

