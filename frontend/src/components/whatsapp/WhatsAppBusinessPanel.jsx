import { useEffect, useState } from "react";
import { FiInfo, FiMessageSquare, FiFileText, FiImage, FiUser } from "react-icons/fi";
import {
  getPhoneDetails,
  getBusinessProfile,
  updateBusinessProfile,
  listTemplates,
  createTemplate,
  deleteTemplate,
  uploadMedia,
  getWabaDetails
} from "../../api/whatsappApi";

export default function WhatsAppBusinessPanel({ accountId, accounts }) {
  const [activeTab, setActiveTab] = useState("info");
  const [phoneDetails, setPhoneDetails] = useState(null);
  const [businessProfile, setBusinessProfile] = useState(null);
  const [wabaDetails, setWabaDetails] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // États pour le profil
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({
    about: "",
    description: "",
    email: "",
    address: "",
    websites: "",
    vertical: ""
  });

  // États pour les templates
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [templateForm, setTemplateForm] = useState({
    name: "",
    category: "UTILITY",
    language: "fr",
    body: ""
  });

  // États pour les médias
  const [uploadedMedias, setUploadedMedias] = useState([]);
  const [uploadingMedia, setUploadingMedia] = useState(false);

  const currentAccount = accounts.find(a => a.id === accountId);
  const accountName = currentAccount?.name || "Compte";

  useEffect(() => {
    if (!accountId) return;
    loadData();
  }, [accountId]);

  const loadData = async () => {
    if (!accountId) return;
    
    setLoading(true);
    setError(null);

    try {
      // Charger les infos du numéro
      try {
        const phoneRes = await getPhoneDetails(accountId);
        setPhoneDetails(phoneRes.data);
      } catch (err) {
        console.log("Phone details not available:", err.response?.data?.detail);
      }

      // Charger le profil business
      try {
        const profileRes = await getBusinessProfile(accountId);
        if (profileRes.data?.data?.[0]) {
          setBusinessProfile(profileRes.data.data[0]);
          setProfileForm({
            about: profileRes.data.data[0].about || "",
            description: profileRes.data.data[0].description || "",
            email: profileRes.data.data[0].email || "",
            address: profileRes.data.data[0].address || "",
            websites: (profileRes.data.data[0].websites || []).join(", "),
            vertical: profileRes.data.data[0].vertical || ""
          });
        }
      } catch (err) {
        console.log("Business profile not available:", err.response?.data?.detail);
      }

      // Charger les détails WABA
      try {
        const wabaRes = await getWabaDetails(accountId);
        setWabaDetails(wabaRes.data);
      } catch (err) {
        console.log("WABA details not available:", err.response?.data?.detail);
      }

      // Charger les templates
      try {
        const templatesRes = await listTemplates(accountId);
        setTemplates(templatesRes.data?.data || []);
      } catch (err) {
        console.log("Templates not available:", err.response?.data?.detail);
      }
    } catch (err) {
      setError("Erreur lors du chargement des données");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleProfileUpdate = async () => {
    if (!accountId) return;
    
    setLoading(true);
    try {
      const data = {
        about: profileForm.about || undefined,
        description: profileForm.description || undefined,
        email: profileForm.email || undefined,
        address: profileForm.address || undefined,
        websites: profileForm.websites ? profileForm.websites.split(",").map(w => w.trim()).filter(Boolean) : undefined,
        vertical: profileForm.vertical || undefined
      };

      await updateBusinessProfile(accountId, data);
      alert("Profil mis à jour avec succès !");
      setEditingProfile(false);
      loadData();
    } catch (err) {
      alert("Erreur lors de la mise à jour du profil");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTemplate = async () => {
    if (!accountId || !templateForm.name || !templateForm.body) {
      alert("Veuillez remplir tous les champs obligatoires");
      return;
    }

    setLoading(true);
    try {
      await createTemplate(accountId, {
        name: templateForm.name.toLowerCase().replace(/[^a-z0-9_-]/g, "_"),
        category: templateForm.category,
        language: templateForm.language,
        components: [
          {
            type: "BODY",
            text: templateForm.body
          }
        ]
      });

      alert("Template créé et soumis à Meta pour validation !");
      setCreatingTemplate(false);
      setTemplateForm({ name: "", category: "UTILITY", language: "fr", body: "" });
      loadData();
    } catch (err) {
      alert(`Erreur: ${err.response?.data?.detail || "Erreur inconnue"}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTemplate = async (name) => {
    if (!confirm(`Supprimer le template "${name}" ?`)) return;

    setLoading(true);
    try {
      await deleteTemplate(accountId, { name });
      alert("Template supprimé !");
      loadData();
    } catch (err) {
      alert("Erreur lors de la suppression");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleMediaUpload = async (file) => {
    if (!accountId) return;

    setUploadingMedia(true);
    try {
      const result = await uploadMedia(accountId, file);
      const mediaId = result.data?.id;
      
      if (mediaId) {
        setUploadedMedias([...uploadedMedias, { id: mediaId, name: file.name, type: file.type }]);
        alert(`Fichier uploadé ! Media ID: ${mediaId}`);
      }
    } catch (err) {
      alert("Erreur lors de l'upload");
      console.error(err);
    } finally {
      setUploadingMedia(false);
    }
  };

  if (!accountId) {
    return (
      <div className="whatsapp-business-panel">
        <div className="panel-empty">
          <p>Sélectionnez un compte WhatsApp Business</p>
        </div>
      </div>
    );
  }

  return (
    <div className="whatsapp-business-panel">
      <div className="panel-header">
        <h2>WhatsApp Business - {accountName}</h2>
        <p className="panel-subtitle">Gestion complète de votre compte WhatsApp</p>
      </div>

      <div className="panel-tabs">
        <button
          className={activeTab === "info" ? "active" : ""}
          onClick={() => setActiveTab("info")}
        >
          <FiInfo /> Informations
        </button>
        <button
          className={activeTab === "profile" ? "active" : ""}
          onClick={() => setActiveTab("profile")}
        >
          <FiUser /> Profil Business
        </button>
        <button
          className={activeTab === "templates" ? "active" : ""}
          onClick={() => setActiveTab("templates")}
        >
          <FiMessageSquare /> Templates
        </button>
        <button
          className={activeTab === "media" ? "active" : ""}
          onClick={() => setActiveTab("media")}
        >
          <FiImage /> Médias
        </button>
      </div>

      {error && <div className="panel-error">{error}</div>}
      {loading && <div className="panel-loading">Chargement...</div>}

      <div className="panel-content">
        {activeTab === "info" && (
          <div className="info-section">
            <h3>Informations du Numéro</h3>
            {phoneDetails ? (
              <div className="info-grid">
                <div className="info-item">
                  <label>Numéro affiché</label>
                  <div>{phoneDetails.display_phone_number || "Non disponible"}</div>
                </div>
                <div className="info-item">
                  <label>Nom vérifié</label>
                  <div>{phoneDetails.verified_name || "Non disponible"}</div>
                </div>
                <div className="info-item">
                  <label>Qualité</label>
                  <div className={`quality-badge ${(phoneDetails.quality_rating || "").toLowerCase()}`}>
                    {phoneDetails.quality_rating || "UNKNOWN"}
                  </div>
                </div>
                <div className="info-item">
                  <label>Statut vérification</label>
                  <div>{phoneDetails.code_verification_status || "Non disponible"}</div>
                </div>
              </div>
            ) : (
              <p>Informations non disponibles (configurez waba_id dans la base de données)</p>
            )}

            <h3 style={{ marginTop: "2rem" }}>Détails WABA</h3>
            {wabaDetails ? (
              <div className="info-grid">
                <div className="info-item">
                  <label>WABA ID</label>
                  <div className="mono">{wabaDetails.id}</div>
                </div>
                <div className="info-item">
                  <label>Nom</label>
                  <div>{wabaDetails.name || "Non disponible"}</div>
                </div>
                <div className="info-item">
                  <label>Fuseau horaire</label>
                  <div>{wabaDetails.timezone_id || "Non disponible"}</div>
                </div>
                <div className="info-item">
                  <label>Statut</label>
                  <div className={`status-badge ${(wabaDetails.account_review_status || "").toLowerCase()}`}>
                    {wabaDetails.account_review_status || "UNKNOWN"}
                  </div>
                </div>
              </div>
            ) : (
              <p>Détails WABA non disponibles (configurez waba_id dans la base de données)</p>
            )}
          </div>
        )}

        {activeTab === "profile" && (
          <div className="profile-section">
            <div className="section-header">
              <h3>Profil Business WhatsApp</h3>
              {!editingProfile && (
                <button onClick={() => setEditingProfile(true)} className="btn-primary">
                  Modifier
                </button>
              )}
            </div>

            {editingProfile ? (
              <div className="profile-form">
                <div className="form-group">
                  <label>À propos (max 139 car.)</label>
                  <input
                    type="text"
                    value={profileForm.about}
                    onChange={(e) => setProfileForm({ ...profileForm, about: e.target.value.slice(0, 139) })}
                    maxLength={139}
                    placeholder="Description courte de votre entreprise"
                  />
                  <small>{profileForm.about.length}/139 caractères</small>
                </div>

                <div className="form-group">
                  <label>Description (max 512 car.)</label>
                  <textarea
                    value={profileForm.description}
                    onChange={(e) => setProfileForm({ ...profileForm, description: e.target.value.slice(0, 512) })}
                    maxLength={512}
                    placeholder="Description complète"
                    rows={4}
                  />
                  <small>{profileForm.description.length}/512 caractères</small>
                </div>

                <div className="form-group">
                  <label>Email</label>
                  <input
                    type="email"
                    value={profileForm.email}
                    onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                    placeholder="contact@entreprise.com"
                  />
                </div>

                <div className="form-group">
                  <label>Adresse</label>
                  <input
                    type="text"
                    value={profileForm.address}
                    onChange={(e) => setProfileForm({ ...profileForm, address: e.target.value })}
                    placeholder="123 Rue de la Paix, Paris"
                  />
                </div>

                <div className="form-group">
                  <label>Sites web (séparés par des virgules)</label>
                  <input
                    type="text"
                    value={profileForm.websites}
                    onChange={(e) => setProfileForm({ ...profileForm, websites: e.target.value })}
                    placeholder="https://site1.com, https://site2.com"
                  />
                </div>

                <div className="form-group">
                  <label>Secteur d'activité</label>
                  <select
                    value={profileForm.vertical}
                    onChange={(e) => setProfileForm({ ...profileForm, vertical: e.target.value })}
                  >
                    <option value="">Sélectionner...</option>
                    <option value="AUTOMOTIVE">Automobile</option>
                    <option value="BEAUTY">Beauté</option>
                    <option value="APPAREL">Mode</option>
                    <option value="EDU">Éducation</option>
                    <option value="ENTERTAINMENT">Divertissement</option>
                    <option value="FINANCE">Finance</option>
                    <option value="GROCERY">Épicerie</option>
                    <option value="HEALTH">Santé</option>
                    <option value="HOTEL">Hôtellerie</option>
                    <option value="NONPROFIT">Association</option>
                    <option value="RETAIL">Commerce</option>
                    <option value="RESTAURANT">Restaurant</option>
                    <option value="TRAVEL">Voyage</option>
                    <option value="OTHER">Autre</option>
                  </select>
                </div>

                <div className="form-actions">
                  <button onClick={handleProfileUpdate} className="btn-primary" disabled={loading}>
                    {loading ? "Enregistrement..." : "Enregistrer"}
                  </button>
                  <button onClick={() => setEditingProfile(false)} className="btn-secondary">
                    Annuler
                  </button>
                </div>
              </div>
            ) : (
              <div className="profile-view">
                {businessProfile ? (
                  <div className="info-grid">
                    <div className="info-item">
                      <label>À propos</label>
                      <div>{businessProfile.about || "Non renseigné"}</div>
                    </div>
                    <div className="info-item">
                      <label>Description</label>
                      <div>{businessProfile.description || "Non renseigné"}</div>
                    </div>
                    <div className="info-item">
                      <label>Email</label>
                      <div>{businessProfile.email || "Non renseigné"}</div>
                    </div>
                    <div className="info-item">
                      <label>Adresse</label>
                      <div>{businessProfile.address || "Non renseigné"}</div>
                    </div>
                    <div className="info-item">
                      <label>Sites web</label>
                      <div>{(businessProfile.websites || []).join(", ") || "Non renseigné"}</div>
                    </div>
                    <div className="info-item">
                      <label>Secteur</label>
                      <div>{businessProfile.vertical || "Non renseigné"}</div>
                    </div>
                  </div>
                ) : (
                  <p>Profil non disponible</p>
                )}
              </div>
            )}
          </div>
        )}

        {activeTab === "templates" && (
          <div className="templates-section">
            <div className="section-header">
              <h3>Templates de Messages</h3>
              {!creatingTemplate && (
                <button onClick={() => setCreatingTemplate(true)} className="btn-primary">
                  + Nouveau Template
                </button>
              )}
            </div>

            {creatingTemplate && (
              <div className="template-form card">
                <h4>Créer un Template</h4>
                <div className="form-group">
                  <label>Nom du template (sans espaces, minuscules)</label>
                  <input
                    type="text"
                    value={templateForm.name}
                    onChange={(e) => setTemplateForm({ ...templateForm, name: e.target.value })}
                    placeholder="confirmation_commande"
                  />
                </div>

                <div className="form-group">
                  <label>Catégorie</label>
                  <select
                    value={templateForm.category}
                    onChange={(e) => setTemplateForm({ ...templateForm, category: e.target.value })}
                  >
                    <option value="UTILITY">UTILITY - Notifications transactionnelles</option>
                    <option value="MARKETING">MARKETING - Messages promotionnels</option>
                    <option value="AUTHENTICATION">AUTHENTICATION - Codes de vérification</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Langue</label>
                  <select
                    value={templateForm.language}
                    onChange={(e) => setTemplateForm({ ...templateForm, language: e.target.value })}
                  >
                    <option value="fr">Français</option>
                    <option value="en">Anglais</option>
                    <option value="es">Espagnol</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Corps du message (utilisez {"{{1}}"}, {"{{2}}"} pour les variables)</label>
                  <textarea
                    value={templateForm.body}
                    onChange={(e) => setTemplateForm({ ...templateForm, body: e.target.value })}
                    placeholder="Bonjour {{1}}, votre commande {{2}} a été confirmée !"
                    rows={4}
                  />
                </div>

                <div className="form-actions">
                  <button onClick={handleCreateTemplate} className="btn-primary" disabled={loading}>
                    {loading ? "Création..." : "Créer et Soumettre à Meta"}
                  </button>
                  <button onClick={() => setCreatingTemplate(false)} className="btn-secondary">
                    Annuler
                  </button>
                </div>
                <small style={{ color: "#666", display: "block", marginTop: "1rem" }}>
                  ⚠️ Le template sera soumis à Meta pour validation. Cela peut prendre quelques heures.
                </small>
              </div>
            )}

            <div className="templates-list">
              {templates.length === 0 ? (
                <p>Aucun template. Configurez waba_id pour voir vos templates ou créez-en un nouveau.</p>
              ) : (
                templates.map((tpl) => (
                  <div key={tpl.name} className="template-card card">
                    <div className="template-header">
                      <div>
                        <h4>{tpl.name}</h4>
                        <span className={`badge ${(tpl.status || "").toLowerCase()}`}>
                          {tpl.status}
                        </span>
                        <span className="badge">{tpl.category}</span>
                        <span className="badge">{tpl.language}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteTemplate(tpl.name)}
                        className="btn-danger-small"
                        disabled={loading}
                      >
                        Supprimer
                      </button>
                    </div>
                    <div className="template-body">
                      {tpl.components?.map((comp, idx) => (
                        <div key={idx}>
                          <strong>{comp.type}:</strong> {comp.text || JSON.stringify(comp)}
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === "media" && (
          <div className="media-section">
            <h3>Upload de Médias</h3>
            <p>Uploadez des fichiers pour obtenir leur Media ID et les utiliser dans vos messages.</p>

            <div className="media-upload-zone">
              <input
                type="file"
                onChange={(e) => e.target.files[0] && handleMediaUpload(e.target.files[0])}
                disabled={uploadingMedia}
                accept="image/*,audio/*,video/*,.pdf,.doc,.docx"
                id="media-upload"
              />
              <label htmlFor="media-upload" className={uploadingMedia ? "uploading" : ""}>
                {uploadingMedia ? "Upload en cours..." : "Cliquez pour sélectionner un fichier"}
              </label>
            </div>

            {uploadedMedias.length > 0 && (
              <div className="uploaded-medias">
                <h4>Médias uploadés</h4>
                {uploadedMedias.map((media, idx) => (
                  <div key={idx} className="media-item card">
                    <div>
                      <strong>{media.name}</strong>
                      <br />
                      <small>Type: {media.type}</small>
                    </div>
                    <code className="media-id">{media.id}</code>
                  </div>
                ))}
              </div>
            )}

            <div className="media-info" style={{ marginTop: "2rem", padding: "1rem", background: "#f5f5f5", borderRadius: "8px" }}>
              <h4>💡 Comment utiliser ?</h4>
              <ol>
                <li>Uploadez votre fichier ci-dessus</li>
                <li>Copiez le Media ID affiché</li>
                <li>Utilisez-le dans un message interactif avec l'option "Média"</li>
                <li>Les médias sont conservés 30 jours sur les serveurs Meta</li>
              </ol>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

