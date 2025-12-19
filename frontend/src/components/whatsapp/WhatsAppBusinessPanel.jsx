import { useEffect, useState } from "react";
import { FiInfo, FiMessageSquare, FiFileText, FiImage, FiUser, FiExternalLink, FiPhone, FiCornerDownLeft } from "react-icons/fi";
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
import { supabaseClient } from "../../api/supabaseClient";

export default function WhatsAppBusinessPanel({ accountId, accounts }) {
  const [activeTab, setActiveTab] = useState("info");
  const [phoneDetails, setPhoneDetails] = useState(null);
  const [businessProfile, setBusinessProfile] = useState(null);
  const [wabaDetails, setWabaDetails] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [templateMedias, setTemplateMedias] = useState({}); // { templateName_language: { IMAGE: url, VIDEO: url, ... } }
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
      // OPTIMISATION : Charger toutes les données en parallèle avec Promise.allSettled
      // pour que les erreurs d'un appel ne bloquent pas les autres
      const [phoneResult, profileResult, wabaResult, templatesResult] = await Promise.allSettled([
        getPhoneDetails(accountId),
        getBusinessProfile(accountId),
        getWabaDetails(accountId),
        listTemplates(accountId),
      ]);

      // Traiter les résultats
      if (phoneResult.status === "fulfilled") {
        setPhoneDetails(phoneResult.value.data);
      } else {
        console.log("Phone details not available:", phoneResult.reason?.response?.data?.detail);
      }

      if (profileResult.status === "fulfilled" && profileResult.value.data?.data?.[0]) {
        const profileData = profileResult.value.data.data[0];
        setBusinessProfile(profileData);
        setProfileForm({
          about: profileData.about || "",
          description: profileData.description || "",
          email: profileData.email || "",
          address: profileData.address || "",
          websites: (profileData.websites || []).join(", "),
          vertical: profileData.vertical || ""
        });
      } else {
        console.log("Business profile not available:", profileResult.reason?.response?.data?.detail);
      }

      if (wabaResult.status === "fulfilled") {
        setWabaDetails(wabaResult.value.data);
      } else {
        console.log("WABA details not available:", wabaResult.reason?.response?.data?.detail);
      }

      if (templatesResult.status === "fulfilled") {
        const templatesData = templatesResult.value.data?.data || [];
        setTemplates(templatesData);
        // Charger les médias pour chaque template
        await loadTemplateMedias(templatesData);
      } else {
        console.log("Templates not available:", templatesResult.reason?.response?.data?.detail);
      }
    } catch (err) {
      setError("Erreur lors du chargement des données");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // OPTIMISATION : Fonction légère pour recharger uniquement le profil après mise à jour
  const reloadProfile = async () => {
    try {
      const profileRes = await getBusinessProfile(accountId);
      if (profileRes.data?.data?.[0]) {
        const profileData = profileRes.data.data[0];
        setBusinessProfile(profileData);
        setProfileForm({
          about: profileData.about || "",
          description: profileData.description || "",
          email: profileData.email || "",
          address: profileData.address || "",
          websites: (profileData.websites || []).join(", "),
          vertical: profileData.vertical || ""
        });
      }
    } catch (err) {
      console.log("Error reloading profile:", err);
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
      
      // OPTIMISATION : Ne recharger que le profil au lieu de tout recharger
      await reloadProfile();
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

  const loadTemplateMedias = async (templates) => {
    if (!accountId || !templates.length) return;

    try {
      // Récupérer tous les médias pour les templates de ce compte
      const { data, error } = await supabaseClient
        .from("template_media")
        .select("template_name, template_language, media_type, storage_url, storage_path")
        .eq("account_id", accountId);

      if (error) {
        console.error("Error loading template medias:", error);
        return;
      }

      // Organiser les médias par template_name + template_language + media_type
      const mediasMap = {};
      if (data) {
        data.forEach((media) => {
          const key = `${media.template_name}_${media.template_language}`;
          if (!mediasMap[key]) {
            mediasMap[key] = {};
          }
          
          // Construire l'URL publique
          let publicUrl = null;
          
          // Si storage_url est déjà une URL complète, l'utiliser directement
          if (media.storage_url && (media.storage_url.startsWith('http://') || media.storage_url.startsWith('https://'))) {
            publicUrl = media.storage_url;
          } else if (media.storage_path) {
            // Sinon, construire l'URL depuis storage_path
            const { data: urlData } = supabaseClient.storage
              .from("template-media")
              .getPublicUrl(media.storage_path);
            publicUrl = urlData?.publicUrl;
          } else if (media.storage_url) {
            // Si storage_url existe mais n'est pas une URL complète, essayer de construire l'URL
            const { data: urlData } = supabaseClient.storage
              .from("template-media")
              .getPublicUrl(media.storage_url);
            publicUrl = urlData?.publicUrl;
          }
          
          if (publicUrl) {
            mediasMap[key][media.media_type] = publicUrl;
          }
        });
      }

      setTemplateMedias(mediasMap);
    } catch (err) {
      console.error("Error loading template medias:", err);
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
                <p className="empty-message">Aucun template. Configurez waba_id pour voir vos templates ou créez-en un nouveau.</p>
              ) : (
                templates.map((tpl) => (
                  <div key={tpl.name} className="template-card">
                    <div className="template-card-header">
                      <div className="template-info">
                        <h4 className="template-name">{tpl.name}</h4>
                        <div className="template-badges">
                          <span className={`template-status-badge status-${(tpl.status || "").toLowerCase()}`}>
                            {tpl.status}
                          </span>
                          <span className="template-category-badge">{tpl.category}</span>
                          <span className="template-lang-badge">{tpl.language}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleDeleteTemplate(tpl.name)}
                        className="btn-delete-template"
                        disabled={loading}
                        title="Supprimer"
                      >
                        Supprimer
                      </button>
                    </div>
                    <div className="template-preview">
                      <div className="template-preview-bubble">
                        {tpl.components?.map((comp, idx) => {
                          if (comp.type === "HEADER") {
                            const mediaKey = `${tpl.name}_${tpl.language}`;
                            const mediaUrl = templateMedias[mediaKey]?.[comp.format];
                            
                            return (
                              <div key={idx} className="template-preview-header">
                                {comp.format === "IMAGE" ? (
                                  mediaUrl ? (
                                    <div className="template-preview-media-image-wrapper">
                                      <img 
                                        src={mediaUrl} 
                                        alt="Template header" 
                                        className="template-preview-media-image"
                                        onError={(e) => {
                                          e.target.parentElement.innerHTML = '<div class="template-preview-media">[Image non disponible]</div>';
                                        }}
                                      />
                                    </div>
                                  ) : (
                                    <div className="template-preview-media">[Image]</div>
                                  )
                                ) : comp.format === "VIDEO" ? (
                                  mediaUrl ? (
                                    <div className="template-preview-media-video-wrapper">
                                      <video 
                                        src={mediaUrl} 
                                        controls 
                                        className="template-preview-media-video"
                                        onError={(e) => {
                                          e.target.parentElement.innerHTML = '<div class="template-preview-media">[Vidéo non disponible]</div>';
                                        }}
                                      />
                                    </div>
                                  ) : (
                                    <div className="template-preview-media">[Vidéo]</div>
                                  )
                                ) : comp.format === "DOCUMENT" ? (
                                  mediaUrl ? (
                                    <a 
                                      href={mediaUrl} 
                                      target="_blank" 
                                      rel="noopener noreferrer"
                                      className="template-preview-media-document"
                                    >
                                      📄 Document
                                    </a>
                                  ) : (
                                    <div className="template-preview-media">[Document]</div>
                                  )
                                ) : (
                                  <strong>{comp.text}</strong>
                                )}
                              </div>
                            );
                          }
                          if (comp.type === "BODY") {
                            return (
                              <div key={idx} className="template-preview-body">
                                {comp.text}
                              </div>
                            );
                          }
                          if (comp.type === "FOOTER") {
                            return (
                              <div key={idx} className="template-preview-footer">
                                {comp.text}
                              </div>
                            );
                          }
                          if (comp.type === "BUTTONS") {
                            return (
                              <div key={idx} className="template-preview-buttons">
                                {comp.buttons?.map((btn, btnIdx) => (
                                  <div key={btnIdx} className="template-preview-button">
                                    {btn.type === "QUICK_REPLY" ? (
                                      <FiCornerDownLeft className="template-preview-button-icon" />
                                    ) : btn.type === "URL" ? (
                                      <FiExternalLink className="template-preview-button-icon" />
                                    ) : (
                                      <FiPhone className="template-preview-button-icon" />
                                    )}
                                    <span className="template-preview-button-text">{btn.text}</span>
                                  </div>
                                ))}
                              </div>
                            );
                          }
                          return null;
                        })}
                      </div>
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

            <div className="media-info">
              <h4>Comment utiliser ?</h4>
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

