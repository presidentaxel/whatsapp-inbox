/**
 * Composant pour afficher l'indicateur "en train d'écrire"
 * Style WhatsApp avec trois points animés
 */
export default function TypingIndicator() {
  return (
    <div className="typing-indicator">
      <div className="typing-indicator__bubble">
        <div className="typing-indicator__dots">
          <span className="typing-indicator__dot"></span>
          <span className="typing-indicator__dot"></span>
          <span className="typing-indicator__dot"></span>
        </div>
      </div>
    </div>
  );
}

