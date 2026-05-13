import { useState, useEffect, useMemo } from "react";
import { FiX, FiSend } from "react-icons/fi";
import { buildTemplateComponents, extractTemplateVariables, extractTemplateVariablesWithMapping } from "../../utils/templateVariables";

export default function TemplateVariablesModal({ 
  template, 
  onClose, 
  onSend, 
  isOpen 
}) {
  const [variableValues, setVariableValues] = useState({});
  const [errors, setErrors] = useState({});
  
  // Calculer les variables avec useMemo pour éviter les recalculs inutiles
  const allVariables = useMemo(() => {
    if (!template || !template.components || !Array.isArray(template.components)) {
      return [];
    }
    
    const variablesList = [];
    const seenVariables = new Set();
    
    console.log("📝 TemplateVariablesModal: Analyse des components", {
      templateName: template.name,
      componentsCount: template.components.length,
      components: template.components.map(c => ({ 
        type: c.type, 
        text: c.text?.substring(0, 100), // Limiter pour les logs
        hasText: !!c.text 
      }))
    });
    
    template.components.forEach((component, index) => {
      const type = (component.type || "").toUpperCase();
      const text = component.text || "";
      
      console.log(`📝 Component ${index}:`, {
        type,
        textLength: text.length,
        text: text.substring(0, 200),
        hasText: !!text
      });
      
      if (text) {
        const foundVars = extractTemplateVariables(text);
        console.log(`📝 Component ${index} (${type}): Variables trouvées:`, foundVars);
        
        // Utiliser extractTemplateVariablesWithMapping pour obtenir toutes les infos des variables
        const variableMapping = extractTemplateVariablesWithMapping(text);
        
        foundVars.forEach(varId => {
          // varId peut être un numéro ou un nom (string)
          // Trouver la variable correspondante dans le mapping
          const variableInfo = variableMapping.find(v => {
            if (typeof varId === 'string') {
              // Si varId est un string (nom), chercher par nom
              return v.name === varId;
            } else {
              // Si varId est un numéro, chercher par numéro
              return v.num === varId;
            }
          });
          
          if (!variableInfo) {
            console.warn(`⚠️ TemplateVariablesModal: Variable ${varId} non trouvée dans le mapping`);
            return;
          }
          
          // Utiliser le numéro assigné pour l'ordre et le stockage (même pour les variables nommées)
          const varNum = variableInfo.num;
          const key = `${type}-${varNum}`;
          
          if (!seenVariables.has(key)) {
            seenVariables.add(key);
            
            let label = variableInfo.isNamed && variableInfo.name 
              ? variableInfo.name 
              : `Variable ${varNum}`;
            
            if (type === "HEADER") label += " (En-tête)";
            else if (type === "BODY") label += " (Corps)";
            else if (type === "FOOTER") label += " (Pied de page)";
            else if (type === "BUTTONS") label += " (Boutons)";
            
            variablesList.push({
              num: varNum, // Toujours utiliser le numéro assigné pour le stockage dans variableValues
              name: variableInfo.name || null, // Nom original si variable nommée
              type: type.toLowerCase(),
              label: label,
              component: component,
              originalText: text
            });
            
            console.log(`📝 TemplateVariablesModal: Variable ajoutée - num: ${varNum}, name: ${variableInfo.name || 'null'}, isNamed: ${variableInfo.isNamed}, label: ${label}`);
          }
        });
      }
    });
    
    // Trier par numéro de variable
    variablesList.sort((a, b) => a.num - b.num);
    
    console.log("📝 TemplateVariablesModal: Variables finales détectées", {
      count: variablesList.length,
      variables: variablesList.map(v => ({ num: v.num, label: v.label }))
    });
    
    return variablesList;
  }, [template?.name, template?.components ? JSON.stringify(template.components) : null]);
  
  // Réinitialiser les valeurs quand les variables changent
  useEffect(() => {
    if (allVariables.length > 0) {
      console.log("📝 TemplateVariablesModal: Initialisation des valeurs pour", allVariables.length, "variables");
      const initialValues = {};
      allVariables.forEach(v => {
        initialValues[v.num] = "";
      });
      setVariableValues(initialValues);
      setErrors({});
    } else {
      setVariableValues({});
      setErrors({});
    }
  }, [allVariables]);
  
  // Obtenir le texte du template pour l'aperçu - utiliser useMemo pour se mettre à jour quand variableValues change
  // IMPORTANT: Ce hook doit être appelé AVANT le return conditionnel pour éviter l'erreur "Rendered more hooks"
  const templatePreview = useMemo(() => {
    if (!template || !template.components) return "";
    
    let previewParts = [];
    const components = template.components || [];
    
    // Construire le texte de base component par component pour préserver l'ordre
    components.forEach(component => {
      if (component.type === "HEADER" && component.text && component.format !== "IMAGE" && component.format !== "VIDEO" && component.format !== "DOCUMENT") {
        previewParts.push({
          text: component.text,
          type: "HEADER"
        });
        previewParts.push({ text: "\n\n", type: "SPACER" });
      } else if (component.type === "BODY" && component.text) {
        previewParts.push({
          text: component.text,
          type: "BODY"
        });
      } else if (component.type === "FOOTER" && component.text) {
        previewParts.push({ text: "\n\n", type: "SPACER" });
        previewParts.push({
          text: component.text,
          type: "FOOTER"
        });
      }
    });
    
    console.log("🔍 templatePreview (useMemo): Preview parts", previewParts);
    console.log("🔍 templatePreview (useMemo): Variables à remplacer", variableValues);
    console.log("🔍 templatePreview (useMemo): allVariables", allVariables);
    
    // Pour chaque part de texte, remplacer les variables dans l'ordre d'apparition
    const resultParts = previewParts.map(part => {
      if (part.type === "SPACER") {
        return part.text;
      }
      
      let resultText = part.text;
      
      // Utiliser extractTemplateVariablesWithMapping pour obtenir les variables dans l'ordre d'apparition
      const variableMapping = extractTemplateVariablesWithMapping(part.text);
      
      console.log(`🔍 templatePreview (useMemo): Component ${part.type} - Texte original:`, part.text);
      console.log(`🔍 templatePreview (useMemo): Component ${part.type} - Variables trouvées:`, variableMapping);
      console.log(`🔍 templatePreview (useMemo): Component ${part.type} - variableValues disponibles:`, variableValues);
      
      // Trier par position (ordre d'apparition) - dans l'ordre inverse pour éviter les problèmes d'index lors du remplacement
      const sortedMapping = [...variableMapping].sort((a, b) => b.position - a.position);
      
      // Remplacer dans l'ordre inverse pour préserver les positions
      sortedMapping.forEach(({ num, name, pattern, position, isNumbered: _isNumbered, isNamed }) => {
        // Pour les variables nommées, chercher par num (car elles sont stockées par num dans variableValues)
        // Pour les variables numérotées ou vides, chercher aussi par num
        const value = variableValues[num] || variableValues[String(num)] || "";
        const varDisplay = isNamed && name ? `${name} (${num})` : num;
        console.log(`🔍 templatePreview (useMemo): Variable ${varDisplay} (pattern: "${pattern}", position: ${position}, isNamed: ${isNamed}) -> valeur: "${value}"`);
        if (value) {
          const before = resultText.substring(0, position);
          const after = resultText.substring(position + pattern.length);
          resultText = before + value + after;
          console.log(`✅ templatePreview (useMemo): Remplacement de "${pattern}" par "${value}" effectué`);
        } else {
          console.warn(`⚠️ templatePreview (useMemo): Aucune valeur trouvée pour la variable ${varDisplay} (pattern: "${pattern}")`);
        }
      });
      
      return resultText;
    });
    
    const result = resultParts.join("");
    console.log("🔍 templatePreview (useMemo): Texte final après remplacement", result);
    
    return result;
  }, [template, variableValues, allVariables]);
  
  // Fonctions de gestion (doivent être définies après les hooks mais avant le return)
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
  
  // Retourner null APRÈS tous les hooks
  if (!isOpen || !template) return null;
  
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
              <p>Ce template n'a pas de variables à remplir.</p>
              {template?.components && template.components.length > 0 && (
                <details style={{ marginTop: '12px', fontSize: '12px', color: 'rgba(255, 255, 255, 0.6)' }}>
                  <summary style={{ cursor: 'pointer', marginBottom: '8px' }}>Détails du template (debug)</summary>
                  <pre style={{ 
                    background: 'rgba(0, 0, 0, 0.2)', 
                    padding: '8px', 
                    borderRadius: '4px',
                    overflow: 'auto',
                    fontSize: '11px',
                    maxHeight: '200px'
                  }}>
                    {JSON.stringify(template.components.map(c => ({ 
                      type: c.type, 
                      text: c.text,
                      format: c.format 
                    })), null, 2)}
                  </pre>
                </details>
              )}
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
                      placeholder={v.name ? `Valeur pour {{${v.name}}}` : `Valeur pour {{${v.num}}}`}
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
                  {templatePreview || "Aperçu non disponible"}
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

