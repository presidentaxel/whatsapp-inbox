import { useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { FiImage, FiVideo, FiFileText, FiDownload, FiX } from "react-icons/fi";
import { getAccountMediaGallery } from "../../api/messagesApi";
import { supabaseClient } from "../../api/supabaseClient";
import "./AccountMediaGallery.css";

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

  const handleImageClick = (item) => {
    setSelectedMedia(item);
  };

  const handleCloseModal = () => {
    setSelectedMedia(null);
  };

  const handleDownload = (item, event) => {
    event.stopPropagation();
    if (item.url) {
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
          Aucune {mediaType === "image" ? "image" : mediaType === "video" ? "vidéo" : "document"} dans ce compte
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="account-media-gallery">
        <div className="account-media-gallery__header">
          <h3>Galerie - {mediaItems.length} {mediaType === "image" ? "images" : mediaType === "video" ? "vidéos" : "documents"}</h3>
        </div>
        <div className="account-media-gallery__grid">
          {mediaItems.map((item) => (
            <div
              key={item.id}
              className="account-media-gallery__item"
              onClick={() => handleImageClick(item)}
            >
              {item.type === "image" || item.type === "sticker" ? (
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
              ) : (
                <div className="account-media-gallery__thumbnail account-media-gallery__thumbnail--non-image">
                  <div className="account-media-gallery__icon">{getMediaIcon(item.type)}</div>
                  <div className="account-media-gallery__download-btn">
                    <FiDownload />
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Modal pour afficher l'image en grand */}
      {selectedMedia && (selectedMedia.type === "image" || selectedMedia.type === "sticker") && 
        createPortal(
          <div className="account-media-gallery__modal" onClick={handleCloseModal}>
            <div className="account-media-gallery__modal-content" onClick={(e) => e.stopPropagation()}>
              <button className="account-media-gallery__modal-close" onClick={handleCloseModal}>
                <FiX />
              </button>
              <img
                src={selectedMedia.url}
                alt={selectedMedia.caption || "Image"}
                className="account-media-gallery__modal-image"
              />
              {selectedMedia.caption && (
                <div className="account-media-gallery__modal-caption">{selectedMedia.caption}</div>
              )}
              <button
                className="account-media-gallery__modal-download"
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

