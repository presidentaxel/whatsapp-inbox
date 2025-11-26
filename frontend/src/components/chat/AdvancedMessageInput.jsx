import { useState, useRef, useEffect } from "react";
import { FiSend, FiPaperclip, FiGrid, FiList, FiX, FiHelpCircle, FiSmile, FiImage, FiVideo, FiFileText, FiMic } from "react-icons/fi";
import { uploadMedia } from "../../api/whatsappApi";
import { sendMediaMessage, sendInteractiveMessage } from "../../api/messagesApi";
import EmojiPicker from "emoji-picker-react";

export default function AdvancedMessageInput({ conversation, onSend, disabled = false }) {
  const [text, setText] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [mode, setMode] = useState("text"); // text, media, buttons, list
  const [uploading, setUploading] = useState(false);
  
  const menuRef = useRef(null);
  const emojiRef = useRef(null);
  const fileInputRef = useRef(null);
  
  // States pour boutons interactifs
  const [buttons, setButtons] = useState([{ id: "", title: "" }]);
  const [headerText, setHeaderText] = useState("");
  const [footerText, setFooterText] = useState("");
  
  // States pour listes
  const [listSections, setListSections] = useState([
    { title: "", rows: [{ id: "", title: "", description: "" }] }
  ]);
  const [buttonText, setButtonText] = useState("Voir les options");

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

  const handleSend = () => {
    if (disabled || !text.trim()) return;
    onSend(text);
    setText("");
    setShowAdvanced(false);
    setMode("text");
  };

  const handleMediaSend = async (file) => {
    if (!conversation?.id || !conversation?.account_id) return;
    
    setUploading(true);
    setShowMenu(false);
    try {
      // Upload le fichier
      const uploadResult = await uploadMedia(conversation.account_id, file);
      const mediaId = uploadResult.data?.id;
      
      if (!mediaId) {
        alert("Erreur lors de l'upload du fichier");
        return;
      }

      // Détermine le type de média
      let mediaType = "document";
      if (file.type.startsWith("image/")) mediaType = "image";
      else if (file.type.startsWith("audio/")) mediaType = "audio";
      else if (file.type.startsWith("video/")) mediaType = "video";

      // Envoie le message via notre API backend qui gère le stockage
      await sendMediaMessage({
        conversation_id: conversation.id,
        media_type: mediaType,
        media_id: mediaId,
        caption: text || undefined
      });

      setText("");
      setShowAdvanced(false);
      setMode("text");
      onSend?.(""); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi média:", error);
      alert("Erreur lors de l'envoi du fichier");
    } finally {
      setUploading(false);
    }
  };

  const handleEmojiClick = (emojiData) => {
    setText(text + emojiData.emoji);
    setShowEmojiPicker(false);
  };

  const openMediaPicker = () => {
    setShowMenu(false);
    fileInputRef.current?.click();
  };

  const openMode = (newMode) => {
    setMode(newMode);
    setShowMenu(false);
    setShowAdvanced(true);
  };

  const handleButtonsSend = async () => {
    if (!conversation?.id || !text.trim()) return;
    
    const validButtons = buttons.filter(b => b.id && b.title).slice(0, 3);
    if (validButtons.length === 0) {
      alert("Ajoutez au moins un bouton");
      return;
    }

    try {
      await sendInteractiveMessage({
        conversation_id: conversation.id,
        interactive_type: "button",
        body_text: text,
        buttons: validButtons,
        header_text: headerText || undefined,
        footer_text: footerText || undefined
      });

      // Reset
      setText("");
      setButtons([{ id: "", title: "" }]);
      setHeaderText("");
      setFooterText("");
      setShowAdvanced(false);
      setMode("text");
      onSend?.(""); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi boutons:", error);
      alert("Erreur lors de l'envoi");
    }
  };

  const handleListSend = async () => {
    if (!conversation?.id || !text.trim()) return;
    
    const validSections = listSections
      .map(section => ({
        title: section.title,
        rows: section.rows.filter(r => r.id && r.title)
      }))
      .filter(s => s.rows.length > 0);
    
    if (validSections.length === 0) {
      alert("Ajoutez au moins une section avec des lignes");
      return;
    }

    try {
      await sendInteractiveMessage({
        conversation_id: conversation.id,
        interactive_type: "list",
        body_text: text,
        button_text: buttonText,
        sections: validSections,
        header_text: headerText || undefined,
        footer_text: footerText || undefined
      });

      // Reset
      setText("");
      setListSections([{ title: "", rows: [{ id: "", title: "", description: "" }] }]);
      setHeaderText("");
      setFooterText("");
      setButtonText("Voir les options");
      setShowAdvanced(false);
      setMode("text");
      onSend?.(""); // Trigger refresh
    } catch (error) {
      console.error("Erreur envoi liste:", error);
      alert("Erreur lors de l'envoi");
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
              {mode === "buttons" ? "Message avec boutons" : mode === "list" ? "Message avec liste" : "Options"}
            </h3>
            <button 
              className="advanced-close"
              onClick={() => setShowAdvanced(false)}
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
          </div>
        </div>
      )}

      <div className="input-area">
        {/* Boutons à gauche */}
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
                <input
                  ref={fileInputRef}
                  type="file"
                  style={{ display: "none" }}
                  onChange={(e) => e.target.files[0] && handleMediaSend(e.target.files[0])}
                  accept="image/*,audio/*,video/*,.pdf,.doc,.docx"
                />
                <button className="menu-item" onClick={openMediaPicker}>
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
                <button className="menu-item" onClick={() => openMode("list")}>
                  <div className="menu-icon menu-icon--list">
                    <FiList />
                  </div>
                  <span>Liste interactive</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Champ de saisie */}
        <div className="input-wrapper">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Écrire un message..."
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            disabled={disabled}
          />
        </div>
        
        {/* Bouton d'envoi */}
        <button
          className="btn-send-whatsapp"
          onClick={() => {
            if (mode === "buttons") handleButtonsSend();
            else if (mode === "list") handleListSend();
            else handleSend();
          }}
          disabled={disabled || !text.trim() || uploading}
          aria-label="Envoyer"
        >
          <FiSend />
        </button>
      </div>
    </div>
  );
}
