import { useState } from "react";
import { FiArrowLeft, FiSave, FiX } from "react-icons/fi";
import { createContact } from "../../api/contactsApi";

export default function MobileContactForm({ onBack, onCreated }) {
  const [displayName, setDisplayName] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!whatsappNumber.trim()) {
      alert("Le numéro WhatsApp est requis");
      return;
    }

    setLoading(true);
    try {
      const result = await createContact({
        whatsapp_number: whatsappNumber,
        display_name: displayName || null
      });
      if (onCreated) {
        onCreated(result.data);
      }
      onBack();
    } catch (error) {
      console.error("Erreur lors de la création du contact:", error);
      const message = error.response?.data?.detail || "Erreur lors de la création du contact";
      alert(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mobile-contact-form">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Nouveau contact</h1>
      </header>

      <div className="mobile-contact-form__content">
        <form onSubmit={handleSubmit}>
          <div className="mobile-contact-form__field">
            <label>Nom</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Nom du contact (optionnel)"
            />
          </div>

          <div className="mobile-contact-form__field">
            <label>Numéro WhatsApp *</label>
            <input
              type="text"
              value={whatsappNumber}
              onChange={(e) => setWhatsappNumber(e.target.value)}
              placeholder="+33 6 12 34 56 78"
              required
            />
          </div>

          <div className="mobile-contact-form__actions">
            <button
              type="button"
              className="mobile-contact-form__cancel-btn"
              onClick={onBack}
              disabled={loading}
            >
              <FiX /> Annuler
            </button>
            <button
              type="submit"
              className="mobile-contact-form__save-btn"
              disabled={loading || !whatsappNumber.trim()}
            >
              <FiSave /> {loading ? "Création..." : "Créer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

