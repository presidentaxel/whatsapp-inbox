import { useState, useEffect, useRef } from "react";
import { FiX, FiPlus, FiTrash2, FiSearch, FiUpload } from "react-icons/fi";
import { getContacts } from "../../api/contactsApi";
import {
  createBroadcastGroup,
  updateBroadcastGroup,
  getGroupRecipients,
  addRecipientToGroup,
  removeRecipientFromGroup,
  importBroadcastRecipients,
  importBroadcastRecipientsCsv,
} from "../../api/broadcastApi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { contactMatchesSearch, foldString } from "../../utils/contactSearch";

function normalizePhoneDigits(raw) {
  let d = String(raw || "").replace(/\D/g, "");
  if (d.startsWith("0") && d.length === 10) d = "33" + d.slice(1);
  return d.length >= 8 ? d : null;
}

function parseBulkRecipientLines(text) {
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const sep = line.includes(";") ? ";" : line.includes(",") ? "," : null;
      let phone;
      let name = "";
      if (sep) {
        const parts = line.split(sep).map((s) => s.trim());
        phone = parts[0];
        name = parts.slice(1).join(" ").trim();
      } else {
        const tab = line.split(/\t/);
        if (tab.length >= 2) {
          phone = tab[0].trim();
          name = tab.slice(1).join(" ").trim();
        } else {
          phone = line;
        }
      }
      const normalized = normalizePhoneDigits(phone);
      return { phone, name, normalized };
    })
    .filter((r) => r.normalized);
}

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
  const [importBusy, setImportBusy] = useState(false);
  const [bulkPaste, setBulkPaste] = useState("");
  const [importFeedback, setImportFeedback] = useState(null);
  const [showAddRecipient, setShowAddRecipient] = useState(false);
  const csvInputRef = useRef(null);

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
      const res = await getContacts({ limit: 15000 });
      setContacts(res.data?.items || res.data || []);
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

        if (pendingRecipients.length > 0) {
          try {
            await importBroadcastRecipients(newGroup.id, {
              rows: pendingRecipients.map((r) => ({
                phone: r.phone_number,
                name: r.display_name || "",
              })),
              create_conversations: true,
            });
          } catch (error) {
            console.error("Error importing pending recipients:", error);
            alert(error.response?.data?.detail || "Groupe créé mais import des destinataires partiellement échoué.");
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

  const handleCsvFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !group) return;
    setImportFeedback(null);
    setImportBusy(true);
    try {
      const res = await importBroadcastRecipientsCsv(group.id, file, true);
      const d = res.data || {};
      const nErr = Array.isArray(d.errors) ? d.errors.length : 0;
      setImportFeedback({
        ok: true,
        text: `${d.imported ?? 0} ligne(s) importée(s). ${nErr ? `${nErr} erreur(s).` : ""}`,
      });
      await loadRecipients();
    } catch (err) {
      console.error(err);
      setImportFeedback({
        ok: false,
        text: err.response?.data?.detail || err.message || "Import CSV échoué",
      });
    } finally {
      setImportBusy(false);
    }
  };

  const handleBulkPasteApply = async () => {
    const parsed = parseBulkRecipientLines(bulkPaste);
    if (!parsed.length) {
      setImportFeedback({ ok: false, text: "Aucun numéro valide dans le texte." });
      return;
    }
    setImportFeedback(null);
    if (group) {
      setImportBusy(true);
      try {
        const rows = parsed.map(({ phone, name }) => ({
          phone,
          name: name || undefined,
        }));
        const res = await importBroadcastRecipients(group.id, {
          rows,
          create_conversations: true,
        });
        const d = res.data || {};
        const nErr = Array.isArray(d.errors) ? d.errors.length : 0;
        setImportFeedback({
          ok: true,
          text: `${d.imported ?? 0} importée(s). ${nErr ? `${nErr} erreur(s).` : ""}`,
        });
        setBulkPaste("");
        await loadRecipients();
      } catch (err) {
        console.error(err);
        setImportFeedback({
          ok: false,
          text: err.response?.data?.detail || err.message || "Import échoué",
        });
      } finally {
        setImportBusy(false);
      }
      return;
    }
    setPendingRecipients((prev) => {
      const map = new Map(prev.map((r) => [r.phone_number, r]));
      for (const r of parsed) {
        if (!map.has(r.normalized)) {
          map.set(r.normalized, {
            phone_number: r.normalized,
            display_name: r.name || null,
            contact_id: null,
            contacts: null,
          });
        }
      }
      return [...map.values()];
    });
    setBulkPaste("");
    setImportFeedback({
      ok: true,
      text: `${parsed.length} ligne(s) ajoutées au brouillon (création des fiches à l’enregistrement du groupe).`,
    });
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
    .filter((c) => contactMatchesSearch(c, searchTerm))
    .sort((a, b) => {
      const termRaw = searchTerm.trim();
      if (!termRaw) {
        return foldString(a.display_name || "").localeCompare(foldString(b.display_name || ""));
      }
      const term = foldString(termRaw);
      const termDigits = termRaw.replace(/\D/g, "");
      const aName = foldString(a.display_name || "");
      const bName = foldString(b.display_name || "");
      const aD = (a.whatsapp_number || "").replace(/\D/g, "");
      const bD = (b.whatsapp_number || "").replace(/\D/g, "");

      const aNameExact = aName === term;
      const bNameExact = bName === term;
      const aPhoneExact = termDigits.length >= 2 && aD === termDigits;
      const bPhoneExact = termDigits.length >= 2 && bD === termDigits;

      if (aNameExact && !bNameExact) return -1;
      if (!aNameExact && bNameExact) return 1;

      if (aPhoneExact && !bPhoneExact) return -1;
      if (!aPhoneExact && bPhoneExact) return 1;

      const aNameStarts = aName.startsWith(term);
      const bNameStarts = bName.startsWith(term);
      const aPhoneStarts = termDigits.length >= 1 && aD.startsWith(termDigits);
      const bPhoneStarts = termDigits.length >= 1 && bD.startsWith(termDigits);

      if (aNameStarts && !bNameStarts && !bPhoneStarts) return -1;
      if (!aNameStarts && !aPhoneStarts && bNameStarts) return 1;
      if (aPhoneStarts && !bPhoneStarts && !bNameStarts) return -1;
      if (!aPhoneStarts && !aNameStarts && bPhoneStarts) return 1;

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

        <div className="form-group broadcast-group-editor__import">
          <label>Importer des contacts / prospects</label>
          <p className="broadcast-group-editor__import-hint">
            Fichier CSV avec colonnes reconnues : téléphone, mobile, nom, prénom, etc. Séparateur{" "}
            <code>,</code> ou <code>;</code>. Ou colle une ligne par numéro :{" "}
            <code>+33601020304, Jean Dupont</code>
          </p>
          <p className="broadcast-group-editor__import-hint">
            Les numéros sont normalisés (ex. 06… → 33…). Une fiche contact et une conversation sont créées sur ce
            compte WhatsApp pour chaque ligne, puis le contact est ajouté au groupe. Tu peux ensuite lancer une campagne
            depuis l’onglet du groupe.
          </p>
          <input
            ref={csvInputRef}
            type="file"
            accept=".csv,text/csv,text/plain"
            style={{ display: "none" }}
            onChange={handleCsvFile}
          />
          <div className="broadcast-group-editor__import-actions">
            <button
              type="button"
              className="btn-secondary btn-sm"
              disabled={!group || loading || importBusy}
              onClick={() => csvInputRef.current?.click()}
            >
              <FiUpload aria-hidden /> CSV
            </button>
            {!group ? (
              <span className="muted broadcast-group-editor__import-note">
                Enregistre le groupe une première fois pour activer l’import fichier.
              </span>
            ) : null}
          </div>
          <textarea
            className="broadcast-group-editor__bulk-text"
            rows={4}
            placeholder={"+33601020304, Jean Dupont\n0755123456;Marie"}
            value={bulkPaste}
            onChange={(e) => setBulkPaste(e.target.value)}
            disabled={loading || importBusy}
          />
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => void handleBulkPasteApply()}
            disabled={loading || importBusy || !bulkPaste.trim()}
          >
            Importer depuis le texte
          </button>
          {importFeedback ? (
            <p className={importFeedback.ok ? "import-feedback ok" : "import-feedback err"} role="status">
              {importFeedback.text}
            </p>
          ) : null}
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
                          placeholder="Nom, prénom, numéro…"
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


