import { useState, useEffect } from "react";
import { FiX, FiSend } from "react-icons/fi";
import { extractVariablesFromComponents, buildTemplateComponents } from "../../utils/templateVariables";

export default function TemplateVariablesModal({ 
  template, 
  onClose, 
  onSend, 
  isOpen 
}) {
  const [variableValues, setVariableValues] = useState({});
  const [errors, setErrors] = useState({});
  
  // Extraire les variables du template
  const variables = extractVariablesFromComponents(template?.components || []);
  const allVariables = [
    ...variables.header.map(v => ({ num: v, type: "header", label: `Variable ${v} (En-tête)` })),
    ...variables.body.map(v => ({ num: v, type: "body", label: `Variable ${v} (Corps)` })),
    ...variables.footer.map(v => ({ num: v, type: "footer", label: `Variable ${v} (Pied de page)` })),
    ...variables.buttons.map(v => ({ num: v, type: "buttons", label: `Variable ${v} (Boutons)` }))
  ].sort((a, b) => a.num - b.num);
  
  // Réinitialiser les valeurs quand le template change
  useEffect(() => {
    if (template) {
      const initialValues = {};
      allVariables.forEach(v => {
        initialValues[v.num] = "";
      });
      setVariableValues(initialValues);
      setErrors({});
    }
  }, [template?.name]);
  
  if (!isOpen || !template) return null;
  
  const handleChange = (varNum, value) => {
    setVariableValues(prev => ({
      ...prev,
      [varNum]: value
    }));
    // Effacer l'erreur pour cette variable
    if (errors[varNum]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[varNum];
        return newErrors;
      });
    }
  };
  
  const validate = () => {
    const newErrors = {};
    allVariables.forEach(v => {
      if (!variableValues[v.num] || variableValues[v.num].trim() === "") {
        newErrors[v.num] = "Cette variable est requise";
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };
  
  const handleSubmit = () => {
    if (!validate()) {
      return;
    }
    
    // Construire les composants avec les paramètres
    const components = buildTemplateComponents(template, variableValues);
    
    // Appeler la fonction onSend avec les composants
    onSend(components);
    onClose();
  };
  
  // Obtenir le texte du template pour l'aperçu
  const getTemplatePreview = () => {
    let preview = "";
    const components = template.components || [];
    
    components.forEach(component => {
      if (component.type === "HEADER" && component.text) {
        preview += component.text + "\n\n";
      } else if (component.type === "BODY" && component.text) {
        preview += component.text;
      } else if (component.type === "FOOTER" && component.text) {
        preview += "\n\n" + component.text;
      }
    });
    
    // Remplacer les variables par leurs valeurs pour l'aperçu
    Object.keys(variableValues).forEach(varNum => {
      const value = variableValues[varNum] || `{{${varNum}}}`;
      preview = preview.replace(new RegExp(`\\{\\{${varNum}\\}\\}`, "g"), value);
    });
    
    return preview;
  };
  
  return (
    <div className="template-variables-modal-overlay" onClick={onClose}>
      <div className="template-variables-modal" onClick={(e) => e.stopPropagation()}>
        <div className="template-variables-modal__header">
          <h3 className="template-variables-modal__title">
            Remplir les variables du template
          </h3>
          <button 
            className="template-variables-modal__close"
            onClick={onClose}
            aria-label="Fermer"
          >
            <FiX />
          </button>
        </div>
        
        <div className="template-variables-modal__content">
          <div className="template-variables-modal__info">
            <strong>{template.name}</strong>
            <span className="template-variables-modal__category">
              {template.category}
            </span>
          </div>
          
          {allVariables.length === 0 ? (
            <div className="template-variables-modal__no-vars">
              Ce template n'a pas de variables à remplir.
            </div>
          ) : (
            <>
              <div className="template-variables-modal__form">
                {allVariables.map(v => (
                  <div key={v.num} className="template-variables-modal__field">
                    <label className="template-variables-modal__label">
                      {v.label}
                      <span className="template-variables-modal__required">*</span>
                    </label>
                    <input
                      type="text"
                      className={`template-variables-modal__input ${errors[v.num] ? "template-variables-modal__input--error" : ""}`}
                      value={variableValues[v.num] || ""}
                      onChange={(e) => handleChange(v.num, e.target.value)}
                      placeholder={`Valeur pour {{${v.num}}}`}
                      maxLength={32768} // Limite WhatsApp
                    />
                    {errors[v.num] && (
                      <span className="template-variables-modal__error">
                        {errors[v.num]}
                      </span>
                    )}
                  </div>
                ))}
              </div>
              
              <div className="template-variables-modal__preview">
                <div className="template-variables-modal__preview-title">
                  Aperçu du message
                </div>
                <div className="template-variables-modal__preview-content">
                  {getTemplatePreview() || "Aperçu non disponible"}
                </div>
              </div>
            </>
          )}
        </div>
        
        <div className="template-variables-modal__footer">
          <button
            className="template-variables-modal__cancel"
            onClick={onClose}
          >
            Annuler
          </button>
          <button
            className="template-variables-modal__send"
            onClick={handleSubmit}
            disabled={allVariables.length > 0 && Object.keys(errors).length > 0}
          >
            <FiSend style={{ marginRight: "8px" }} />
            Envoyer
          </button>
        </div>
      </div>
    </div>
  );
}

