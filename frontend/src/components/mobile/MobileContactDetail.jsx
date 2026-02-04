import { useState, useEffect } from "react";
import { FiArrowLeft, FiTrash2, FiSave, FiX, FiEdit } from "react-icons/fi";
import { updateContact, deleteContact, getContactWhatsAppInfo } from "../../api/contactsApi";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function MobileContactDetail({ contact, activeAccount, onBack, onUpdate, onDelete }) {
  const [isEditing, setIsEditing] = useState(false);
  const [displayName, setDisplayName] = useState(contact?.display_name || "");
  const [whatsappNumber, setWhatsappNumber] = useState(contact?.whatsapp_number || "");
  const [loading, setLoading] = useState(false);
  const [whatsappInfo, setWhatsappInfo] = useState(null);
  const [loadingWhatsAppInfo, setLoadingWhatsAppInfo] = useState(false);

  // Mettre à jour les valeurs quand le contact change
  useEffect(() => {
    if (contact) {
      setDisplayName(contact.display_name || "");
      setWhatsappNumber(contact.whatsapp_number || "");
    }
  }, [contact]);

  // Récupérer les informations WhatsApp (uniquement si contact.id est défini)
  useEffect(() => {
    if (contact?.id && activeAccount && !isEditing) {
      setLoadingWhatsAppInfo(true);
      getContactWhatsAppInfo(contact.id, activeAccount)
        .then((res) => {
          if (res.data?.success && res.data?.data) {
            setWhatsappInfo(res.data.data);
          }
        })
        .catch((err) => {
          console.error("Erreur lors de la récupération des infos WhatsApp:", err);
        })
        .finally(() => {
          setLoadingWhatsAppInfo(false);
        });
    }
  }, [contact, activeAccount, isEditing]);

  const handleSave = async () => {
    if (!contact) return;
    
    setLoading(true);
    try {
      const updated = await updateContact(contact.id, {
        display_name: displayName || null,
        whatsapp_number: whatsappNumber
      });
      setIsEditing(false);
      if (onUpdate) {
        onUpdate(updated.data);
      }
    } catch (error) {
      console.error("Erreur lors de la mise à jour du contact:", error);
      alert("Erreur lors de la mise à jour du contact");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!contact) return;
    
    if (!confirm("Êtes-vous sûr de vouloir supprimer ce contact ?")) {
      return;
    }

    setLoading(true);
    try {
      await deleteContact(contact.id);
      if (onDelete) {
        onDelete(contact.id);
      }
      onBack();
    } catch (error) {
      console.error("Erreur lors de la suppression du contact:", error);
      alert("Erreur lors de la suppression du contact");
    } finally {
      setLoading(false);
    }
  };

  if (!contact) {
    return null;
  }

  return (
    <div className="mobile-contact-detail">
      <header className="mobile-panel-header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>{isEditing ? "Modifier le contact" : "Détails du contact"}</h1>
        {isEditing ? (
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <button 
              className="icon-btn" 
              onClick={() => { setIsEditing(false); setDisplayName(contact.display_name || ""); setWhatsappNumber(contact.whatsapp_number || ""); }}
              title="Annuler"
            >
              <FiX />
            </button>
            <button 
              className="icon-btn" 
              onClick={handleSave}
              disabled={loading}
              title="Enregistrer"
            >
              <FiSave />
            </button>
          </div>
        ) : (
          <button className="icon-btn" onClick={() => setIsEditing(true)} title="Modifier">
            <FiEdit />
          </button>
        )}
      </header>

      <div className="mobile-contact-detail__content">
        <div className="mobile-contact-detail__avatar">
          {(contact.profile_picture_url || whatsappInfo?.profile_picture_url) ? (
            <img 
              src={contact.profile_picture_url || whatsappInfo.profile_picture_url} 
              alt={contact.display_name || "Contact"}
              style={{ width: "100%", height: "100%", borderRadius: "50%", objectFit: "cover" }}
              onError={(e) => {
                e.target.style.display = 'none';
                e.target.nextSibling.style.display = 'flex';
              }}
            />
          ) : null}
          <div style={{ display: (contact.profile_picture_url || whatsappInfo?.profile_picture_url) ? 'none' : 'flex', width: "100%", height: "100%", alignItems: "center", justifyContent: "center" }}>
            {(contact.display_name || contact.whatsapp_name || "?").charAt(0).toUpperCase()}
          </div>
        </div>

        <div className="mobile-contact-detail__fields">
          <div className="mobile-contact-detail__field">
            <label>Nom</label>
            {isEditing ? (
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Nom du contact"
              />
            ) : (
              <div className="mobile-contact-detail__value">
                {whatsappInfo?.name || contact.display_name || "Sans nom"}
              </div>
            )}
          </div>

          <div className="mobile-contact-detail__field">
            <label>Numéro WhatsApp</label>
            {isEditing ? (
              <input
                type="text"
                value={whatsappNumber}
                onChange={(e) => setWhatsappNumber(e.target.value)}
                placeholder="Numéro de téléphone"
              />
            ) : (
              <div className="mobile-contact-detail__value">
                {formatPhoneNumber(contact.whatsapp_number)}
              </div>
            )}
          </div>

          {!isEditing && (
            <>
              {contact.whatsapp_name && contact.whatsapp_name !== contact.display_name && (
                <div className="mobile-contact-detail__field">
                  <label>Nom WhatsApp</label>
                  <div className="mobile-contact-detail__value">
                    {contact.whatsapp_name}
                  </div>
                </div>
              )}
              {loadingWhatsAppInfo && (
                <div className="mobile-contact-detail__field">
                  <div className="mobile-contact-detail__value" style={{ color: "#8696a0", fontStyle: "italic" }}>
                    Chargement des informations WhatsApp...
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {!isEditing && (
          <div className="mobile-contact-detail__actions">
            <button
              className="mobile-contact-detail__delete-btn"
              onClick={handleDelete}
              disabled={loading}
            >
              <FiTrash2 /> Supprimer le contact
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

