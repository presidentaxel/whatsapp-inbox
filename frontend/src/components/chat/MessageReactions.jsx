import { useState, useEffect, useRef } from "react";
import { addReaction, removeReaction } from "../../api/messagesApi";

const COMMON_EMOJIS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

export default function MessageReactions({ message, conversation, onReactionChange, isHovered = false }) {
  const [showPicker, setShowPicker] = useState(false);
  const pickerRef = useRef(null);
  const reactions = message.reactions || [];

  // Grouper les réactions par emoji
  const reactionsByEmoji = {};
  reactions.forEach((reaction) => {
    if (!reactionsByEmoji[reaction.emoji]) {
      reactionsByEmoji[reaction.emoji] = [];
    }
    reactionsByEmoji[reaction.emoji].push(reaction);
  });

  // Utiliser le numéro de l'account depuis la conversation
  // Note: On ne peut pas facilement identifier "notre" réaction sans connaître notre numéro
  // Pour l'instant, on permet à tous d'ajouter/supprimer des réactions
  const handleReactionClick = async (emoji) => {
    // Vérifier si une réaction avec cet emoji existe déjà
    // (on ne vérifie pas le from_number car on ne le connaît pas côté frontend)
    const existingReaction = reactions.find((r) => r.emoji === emoji);

    try {
      if (existingReaction) {
        // Supprimer la réaction (ou la remplacer)
        await removeReaction({
          message_id: message.id,
          emoji: emoji,
        });
      } else {
        // Ajouter la réaction
        await addReaction({
          message_id: message.id,
          emoji: emoji,
        });
      }
      setShowPicker(false);
      onReactionChange?.();
    } catch (error) {
      console.error("Error managing reaction:", error);
    }
  };

  // Fermer le picker si on clique en dehors
  useEffect(() => {
    function handleClickOutside(event) {
      if (pickerRef.current && !pickerRef.current.contains(event.target)) {
        setShowPicker(false);
      }
    }
    if (showPicker) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showPicker]);

  const hasReactions = Object.keys(reactionsByEmoji).length > 0;

  return (
    <div className="message-reactions">
      {/* Afficher les réactions existantes (toujours visibles) */}
      {hasReactions && (
        <div className="message-reactions__list">
          {Object.entries(reactionsByEmoji).map(([emoji, reactionList]) => {
            return (
              <button
                key={emoji}
                className="message-reaction"
                onClick={() => handleReactionClick(emoji)}
                title={`${reactionList.length} réaction${reactionList.length > 1 ? "s" : ""}`}
              >
                <span className="message-reaction__emoji">{emoji}</span>
                {reactionList.length > 1 && (
                  <span className="message-reaction__count">{reactionList.length}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
      {/* Menu de réactions qui apparaît au survol */}
      <div 
        className={`message-reactions__picker-container ${isHovered ? "visible" : ""}`}
        ref={pickerRef}
      >
        <button
          className="message-reactions__add-btn"
          onClick={() => setShowPicker(!showPicker)}
          onMouseEnter={() => setShowPicker(true)}
          title="Ajouter une réaction"
        >
          <span className="message-reactions__add-icon">😊</span>
        </button>
        {showPicker && (
          <div className="message-reactions__picker">
            {COMMON_EMOJIS.map((emoji) => {
              const isActive = reactions.some((r) => r.emoji === emoji);
              return (
                <button
                  key={emoji}
                  className={`message-reactions__picker-item ${isActive ? "active" : ""}`}
                  onClick={() => handleReactionClick(emoji)}
                  onMouseEnter={() => {}}
                >
                  {emoji}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

