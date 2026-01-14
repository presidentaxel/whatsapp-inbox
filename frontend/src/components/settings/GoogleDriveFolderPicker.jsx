import { useState, useEffect } from "react";
import { FiFolder, FiChevronLeft, FiX, FiCheck } from "react-icons/fi";
import { listGoogleDriveFolders } from "../../api/accountsApi";

export default function GoogleDriveFolderPicker({ 
  accountId, 
  currentFolderId = "root",
  onSelect,
  onClose 
}) {
  const [folders, setFolders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [navigationStack, setNavigationStack] = useState([{ id: "root", name: "Racine du Drive" }]);
  const [selectedFolderId, setSelectedFolderId] = useState(currentFolderId);

  const currentParent = navigationStack[navigationStack.length - 1];

  useEffect(() => {
    loadFolders(currentParent.id);
  }, [currentParent.id]);

  const loadFolders = async (parentId = "root") => {
    setLoading(true);
    setError(null);
    try {
      const response = await listGoogleDriveFolders(accountId, parentId);
      setFolders(response.data?.folders || []);
    } catch (err) {
      console.error("Error loading folders:", err);
      setError("Erreur lors du chargement des dossiers");
    } finally {
      setLoading(false);
    }
  };

  const handleFolderClick = (folder) => {
    if (folder.id === "root") {
      // Sélectionner la racine
      setSelectedFolderId("root");
    } else {
      // Entrer dans le dossier
      setNavigationStack((prev) => [...prev, folder]);
      setSelectedFolderId(folder.id);
    }
  };

  const handleBack = () => {
    if (navigationStack.length > 1) {
      setNavigationStack((prev) => prev.slice(0, -1));
      const previousFolder = navigationStack[navigationStack.length - 2];
      setSelectedFolderId(previousFolder.id);
    }
  };

  const handleSelect = () => {
    if (onSelect) {
      onSelect(selectedFolderId === "root" ? "" : selectedFolderId);
    }
    if (onClose) {
      onClose();
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content google-drive-picker" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Sélectionner un dossier Google Drive</h3>
          <button className="modal-close" onClick={onClose} type="button">
            <FiX />
          </button>
        </div>

        <div className="google-drive-picker__navigation">
          <div className="google-drive-picker__breadcrumb">
            {navigationStack.map((folder, index) => (
              <span key={folder.id} className="breadcrumb-item">
                {index > 0 && <span className="breadcrumb-separator">/</span>}
                <span className={index === navigationStack.length - 1 ? "breadcrumb-current" : ""}>
                  {folder.name}
                </span>
              </span>
            ))}
          </div>
          {navigationStack.length > 1 && (
            <button 
              className="google-drive-picker__back-btn" 
              onClick={handleBack}
              type="button"
            >
              <FiChevronLeft /> Retour
            </button>
          )}
        </div>

        <div className="google-drive-picker__content">
          {loading ? (
            <div className="google-drive-picker__loading">Chargement...</div>
          ) : error ? (
            <div className="google-drive-picker__error">{error}</div>
          ) : folders.length === 0 ? (
            <div className="google-drive-picker__empty">
              Aucun dossier dans ce répertoire
            </div>
          ) : (
            <div className="google-drive-picker__folders">
              {folders.map((folder) => (
                <div
                  key={folder.id}
                  className={`google-drive-picker__folder-item ${
                    selectedFolderId === folder.id ? "selected" : ""
                  }`}
                  onClick={() => handleFolderClick(folder)}
                >
                  <FiFolder className="folder-icon" />
                  <span className="folder-name">{folder.name}</span>
                  {selectedFolderId === folder.id && (
                    <FiCheck className="folder-check" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <div className="google-drive-picker__selected">
            {selectedFolderId === "root" || selectedFolderId === "" ? (
              <span>Racine du Drive sélectionnée</span>
            ) : (
              <span>
                Dossier sélectionné: <strong>{currentParent.name}</strong>
              </span>
            )}
          </div>
          <div className="modal-footer__actions">
            <button className="btn-secondary" onClick={onClose} type="button">
              Annuler
            </button>
            <button className="btn-primary" onClick={handleSelect} type="button">
              <FiCheck /> Sélectionner
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

