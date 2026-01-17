import { useState, useEffect } from "react";
import { FiX, FiPlus, FiTrash2, FiSearch } from "react-icons/fi";
import { getContacts } from "../../api/contactsApi";
import { 
  createBroadcastGroup, 
  updateBroadcastGroup, 
  getGroupRecipients, 
  addRecipientToGroup,
  removeRecipientFromGroup 
} from "../../api/broadcastApi";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function BroadcastGroupEditor({
  group = null,
  accountId,
  onClose,
  onSave,
}) {
  const [name, setName] = useState(group?.name || "");
  const [description, setDescription] = useState(group?.description || "");
  const [recipients, setRecipients] = useState([]);
  const [pendingRecipients, setPendingRecipients] = useState([]); // Pour les destinataires en attente lors de la création
  const [contacts, setContacts] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [phoneInput, setPhoneInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showAddRecipient, setShowAddRecipient] = useState(false);

  useEffect(() => {
    if (group) {
      loadRecipients();
    }
    loadContacts();
  }, [group]);

  const loadRecipients = async () => {
    if (!group) return;
    try {
      const res = await getGroupRecipients(group.id);
      setRecipients(res.data || []);
    } catch (error) {
      console.error("Error loading recipients:", error);
    }
  };

  const loadContacts = async () => {
    try {
      const res = await getContacts();
      setContacts(res.data || []);
    } catch (error) {
      console.error("Error loading contacts:", error);
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      alert("Le nom du groupe est requis");
      return;
    }

    setLoading(true);
    try {
      if (group) {
        // Mise à jour d'un groupe existant
        await updateBroadcastGroup(group.id, { name, description });
      } else {
        // Création d'un nouveau groupe
        const res = await createBroadcastGroup({ account_id: accountId, name, description });
        const newGroup = res.data;
        
        // Ajouter tous les destinataires en attente
        if (pendingRecipients.length > 0) {
          for (const recipient of pendingRecipients) {
            try {
              await addRecipientToGroup(newGroup.id, {
                phone_number: recipient.phone_number,
                contact_id: recipient.contact_id,
                display_name: recipient.display_name,
              });
            } catch (error) {
              console.error("Error adding recipient:", error);
              // Continuer même si un destinataire échoue
            }
          }
        }
        
        if (onSave) {
          onSave(newGroup);
        }
      }
      onClose();
    } catch (error) {
      console.error("Error saving group:", error);
      alert(error.response?.data?.detail || "Erreur lors de la sauvegarde");
    } finally {
      setLoading(false);
    }
  };

  const handleAddRecipient = async (contact = null, phoneNumber = null) => {
    const phone = phoneNumber || contact?.whatsapp_number;
    if (!phone) {
      alert("Numéro de téléphone requis");
      return;
    }

    // Vérifier si le destinataire n'est pas déjà ajouté
    const allRecipients = group ? recipients : pendingRecipients;
    if (allRecipients.some((r) => r.phone_number === phone)) {
      alert("Ce destinataire est déjà dans le groupe");
      return;
    }

    if (group) {
      // Groupe existant : ajouter directement en base
      setLoading(true);
      try {
        await addRecipientToGroup(group.id, {
          phone_number: phone,
          contact_id: contact?.id,
          display_name: contact?.display_name,
        });
        await loadRecipients();
        setPhoneInput("");
        setShowAddRecipient(false);
      } catch (error) {
        console.error("Error adding recipient:", error);
        alert(error.response?.data?.detail || "Erreur lors de l'ajout");
      } finally {
        setLoading(false);
      }
    } else {
      // Nouveau groupe : ajouter en mémoire
      setPendingRecipients([
        ...pendingRecipients,
        {
          phone_number: phone,
          contact_id: contact?.id,
          display_name: contact?.display_name,
          contacts: contact,
        },
      ]);
      setPhoneInput("");
      setShowAddRecipient(false);
    }
  };

  const handleRemoveRecipient = async (recipientId, phoneNumber = null) => {
    if (!confirm("Retirer ce destinataire du groupe ?")) return;

    if (group) {
      // Groupe existant : supprimer de la base
      setLoading(true);
      try {
        await removeRecipientFromGroup(group.id, recipientId);
        await loadRecipients();
      } catch (error) {
        console.error("Error removing recipient:", error);
        alert(error.response?.data?.detail || "Erreur lors de la suppression");
      } finally {
        setLoading(false);
      }
    } else {
      // Nouveau groupe : supprimer de la liste en mémoire
      setPendingRecipients(pendingRecipients.filter((r) => r.phone_number !== phoneNumber));
    }
  };

  const filteredContacts = contacts
    .filter((c) => {
      const term = searchTerm.toLowerCase();
      const name = (c.display_name || "").toLowerCase();
      const phone = (c.whatsapp_number || "").toLowerCase();
      return name.includes(term) || phone.includes(term);
    })
    .sort((a, b) => {
      const term = searchTerm.toLowerCase();
      const aName = (a.display_name || "").toLowerCase();
      const bName = (b.display_name || "").toLowerCase();
      const aPhone = (a.whatsapp_number || "").toLowerCase();
      const bPhone = (b.whatsapp_number || "").toLowerCase();
      
      // Prioriser les correspondances exactes
      const aNameExact = aName === term;
      const bNameExact = bName === term;
      const aPhoneExact = aPhone === term;
      const bPhoneExact = bPhone === term;
      
      // Correspondance exacte du nom en premier
      if (aNameExact && !bNameExact) return -1;
      if (!aNameExact && bNameExact) return 1;
      
      // Correspondance exacte du téléphone en deuxième
      if (aPhoneExact && !bPhoneExact) return -1;
      if (!aPhoneExact && bPhoneExact) return 1;
      
      // Prioriser les correspondances qui commencent par le terme
      const aNameStarts = aName.startsWith(term);
      const bNameStarts = bName.startsWith(term);
      const aPhoneStarts = aPhone.startsWith(term);
      const bPhoneStarts = bPhone.startsWith(term);
      
      if (aNameStarts && !bNameStarts && !bPhoneStarts) return -1;
      if (!aNameStarts && !aPhoneStarts && bNameStarts) return 1;
      if (aPhoneStarts && !bPhoneStarts && !bNameStarts) return -1;
      if (!aPhoneStarts && !aNameStarts && bPhoneStarts) return 1;
      
      // Sinon, ordre alphabétique
      return aName.localeCompare(bName);
    });

  const isRecipientAdded = (phoneNumber) => {
    const allRecipients = group ? recipients : pendingRecipients;
    return allRecipients.some((r) => r.phone_number === phoneNumber);
  };

  // Combiner les destinataires existants et en attente pour l'affichage
  const displayRecipients = group ? recipients : pendingRecipients;

  return (
    <div className="broadcast-group-editor">
      <div className="broadcast-group-editor__header">
        <h2>{group ? "Modifier le groupe" : "Nouveau groupe"}</h2>
        <button className="btn-icon" onClick={onClose}>
          <FiX />
        </button>
      </div>

      <div className="broadcast-group-editor__form">
        <div className="form-group">
          <label>Nom du groupe *</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ex: Clients VIP"
            disabled={loading}
          />
        </div>

        <div className="form-group">
          <label>Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description optionnelle du groupe"
            rows={3}
            disabled={loading}
          />
        </div>

        <div className="broadcast-group-editor__recipients">
          <div className="recipients-header">
            <h3>Destinataires ({displayRecipients.length})</h3>
            <button
              className="btn-primary btn-sm"
              onClick={() => setShowAddRecipient(!showAddRecipient)}
            >
              <FiPlus /> Ajouter
            </button>
          </div>

            {showAddRecipient && (
              <div className="add-recipient-panel">
                <div className="add-recipient-tabs">
                  <div className="tab-content">
                    <div className="form-group">
                      <label>Rechercher un contact</label>
                      <div className="search-input">
                        <FiSearch />
                        <input
                          type="text"
                          placeholder="Nom ou numéro..."
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)}
                        />
                      </div>
                    </div>

                    <div className="contacts-list-mini">
                      {filteredContacts
                        .filter((c) => !isRecipientAdded(c.whatsapp_number))
                        .map((contact) => (
                          <div
                            key={contact.id}
                            className="contact-item-mini"
                            onClick={() => handleAddRecipient(contact)}
                          >
                            <div className="avatar">
                              {(contact.display_name || contact.whatsapp_number || "?")[0]}
                            </div>
                            <div className="contact-info">
                              <strong>{contact.display_name || formatPhoneNumber(contact.whatsapp_number)}</strong>
                              <small>{formatPhoneNumber(contact.whatsapp_number)}</small>
                            </div>
                          </div>
                        ))}
                    </div>

                    <div className="form-group">
                      <label>Ou ajouter un numéro libre</label>
                      <div className="phone-input-group">
                        <input
                          type="text"
                          placeholder="+33612345678"
                          value={phoneInput}
                          onChange={(e) => setPhoneInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" && phoneInput.trim()) {
                              handleAddRecipient(null, phoneInput.trim());
                            }
                          }}
                        />
                        <button
                          className="btn-primary"
                          onClick={() => handleAddRecipient(null, phoneInput.trim())}
                          disabled={!phoneInput.trim() || loading}
                        >
                          Ajouter
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

          <div className="recipients-list">
            {displayRecipients.length === 0 ? (
              <p className="empty">Aucun destinataire. Ajoutez-en pour envoyer des messages groupés.</p>
            ) : (
              displayRecipients.map((recipient, index) => {
                const displayName = recipient.display_name || 
                  recipient.contacts?.display_name || 
                  formatPhoneNumber(recipient.phone_number);
                const recipientId = recipient.id || `pending-${index}`;
                const phoneNumber = recipient.phone_number;
                return (
                  <div key={recipientId} className="recipient-item">
                    <div className="recipient-info">
                      <div className="avatar">
                        {displayName[0]}
                      </div>
                      <div>
                        <strong>{displayName}</strong>
                        <small>{formatPhoneNumber(phoneNumber)}</small>
                      </div>
                    </div>
                    <button
                      className="btn-icon btn-danger"
                      onClick={() => handleRemoveRecipient(recipientId, phoneNumber)}
                      disabled={loading}
                    >
                      <FiTrash2 />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="broadcast-group-editor__actions">
          <button className="btn-secondary" onClick={onClose} disabled={loading}>
            Annuler
          </button>
          <button className="btn-primary" onClick={handleSave} disabled={loading || !name.trim()}>
            {loading ? "Enregistrement..." : group ? "Enregistrer" : "Créer le groupe"}
          </button>
        </div>
      </div>
    </div>
  );
}


