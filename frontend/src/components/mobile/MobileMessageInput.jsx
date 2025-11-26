import { useState, useRef } from "react";
import { FiSend, FiSmile, FiPlus, FiImage, FiFileText } from "react-icons/fi";
import EmojiPicker from "emoji-picker-react";
import { uploadMedia } from "../../api/whatsappApi";
import { sendMediaMessage } from "../../api/messagesApi";

export default function MobileMessageInput({ conversationId, accountId, onSend, onMediaSent, disabled }) {
  const [text, setText] = useState("");
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [uploading, setUploading] = useState(false);
  const textareaRef = useRef(null);

  // Auto-resize du textarea
  const handleTextChange = (e) => {
    setText(e.target.value);
    
    // Ajuster la hauteur automatiquement
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  };

  const handleSendClick = () => {
    if (!text.trim() || disabled) return;
    
    const messageText = text.trim();
    
    // Vider l'input immédiatement pour UX réactive
    setText("");
    
    // Reset la hauteur du textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    
    // Déléguer l'envoi au parent (pour l'UI optimiste)
    onSend?.(messageText);
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendClick();
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
        
        // Message optimiste pour le média
        const tempMediaMessage = {
          id: `temp-media-${Date.now()}`,
          conversation_id: conversationId,
          direction: "outbound",
          content_text: text.trim() || `[${mediaType}]`,
          message_type: mediaType,
          status: "pending",
          timestamp: new Date().toISOString(),
          // Stocker l'URL locale temporaire
          _localPreview: fileUrl,
        };
        
        console.log("🎨 Affichage aperçu optimiste");
        
        // TODO: Ajouter le message optimiste à l'UI
        // (nécessite de passer une fonction depuis le parent)
        
        // Envoyer le message média
        await sendMediaMessage({
          conversation_id: conversationId,
          media_id: mediaId,
          media_type: mediaType,
          caption: text.trim() || undefined
        });
        
        console.log("✅ Message média envoyé");
        
        // Nettoyer l'URL locale
        URL.revokeObjectURL(fileUrl);
        
        setText("");
        onMediaSent?.();
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

      {/* Input bar */}
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
          onKeyPress={handleKeyPress}
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
    </div>
  );
}

