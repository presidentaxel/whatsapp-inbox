import { useState } from "react";
import { FiSend } from "react-icons/fi";

export default function MessageInput({ onSend, disabled = false }) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (disabled || !text.trim()) return;
    onSend(text);
    setText("");
  };

  return (
    <div className={`input-area ${disabled ? "disabled" : ""}`}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Écrire un message..."
        onKeyDown={(e) => e.key === "Enter" && handleSend()}
        disabled={disabled}
      />
      <button onClick={handleSend} disabled={disabled} aria-label="Envoyer">
        <FiSend />
      </button>
    </div>
  );
}