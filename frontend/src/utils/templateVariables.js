/**
 * Utilitaires pour gérer les variables dans les templates WhatsApp
 */

/**
 * Extrait toutes les variables d'un template ({{1}}, {{2}}, etc.)
 * @param {string} text - Le texte du template
 * @returns {Array<number>} - Liste des numéros de variables trouvées, triés
 */
export function extractTemplateVariables(text) {
  if (!text) return [];
  
  // Regex pour trouver {{1}}, {{2}}, etc.
  const regex = /\{\{(\d+)\}\}/g;
  const matches = [];
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    const varNumber = parseInt(match[1], 10);
    if (!matches.includes(varNumber)) {
      matches.push(varNumber);
    }
  }
  
  // Trier par ordre numérique
  return matches.sort((a, b) => a - b);
}

/**
 * Extrait toutes les variables d'un template depuis ses composants
 * @param {Array} components - Les composants du template (HEADER, BODY, FOOTER, etc.)
 * @returns {Object} - Objet avec les variables par type de composant
 *   { header: [1, 2], body: [1, 2, 3], footer: [] }
 */
export function extractVariablesFromComponents(components) {
  const result = {
    header: [],
    body: [],
    footer: [],
    buttons: []
  };
  
  if (!components || !Array.isArray(components)) {
    return result;
  }
  
  components.forEach(component => {
    const type = component.type?.toLowerCase();
    const text = component.text || "";
    
    if (type === "header") {
      result.header = extractTemplateVariables(text);
    } else if (type === "body") {
      result.body = extractTemplateVariables(text);
    } else if (type === "footer") {
      result.footer = extractTemplateVariables(text);
    } else if (type === "buttons") {
      // Les boutons peuvent aussi avoir des variables dans leur texte
      if (component.buttons && Array.isArray(component.buttons)) {
        component.buttons.forEach(button => {
          if (button.text) {
            const buttonVars = extractTemplateVariables(button.text);
            result.buttons = [...result.buttons, ...buttonVars];
          }
        });
      }
    }
  });
  
  // Dédupliquer et trier
  Object.keys(result).forEach(key => {
    result[key] = [...new Set(result[key])].sort((a, b) => a - b);
  });
  
  return result;
}

/**
 * Vérifie si un template a des variables
 * @param {Object} template - L'objet template avec ses components
 * @returns {boolean} - True si le template a au moins une variable
 */
export function hasTemplateVariables(template) {
  if (!template || !template.components) return false;
  
  const variables = extractVariablesFromComponents(template.components);
  return variables.header.length > 0 || 
         variables.body.length > 0 || 
         variables.footer.length > 0 || 
         variables.buttons.length > 0;
}

/**
 * Construit les composants pour l'API Meta avec les paramètres remplis
 * @param {Object} template - L'objet template avec ses components
 * @param {Object} variableValues - Objet avec les valeurs des variables { 1: "valeur1", 2: "valeur2" }
 * @returns {Array} - Composants formatés pour l'API Meta
 * 
 * Note: Selon la documentation Meta, les paramètres doivent être dans l'ordre des numéros de variables
 * ({{1}}, {{2}}, {{3}}, etc.), même si une variable apparaît plusieurs fois dans le texte.
 */
export function buildTemplateComponents(template, variableValues) {
  if (!template || !template.components) return [];
  
  const components = [];
  
  template.components.forEach(component => {
    const type = component.type?.toUpperCase();
    const text = component.text || "";
    
    // Ignorer les HEADER avec format IMAGE/VIDEO/DOCUMENT (géré par le backend)
    if (type === "HEADER" && component.format && 
        ["IMAGE", "VIDEO", "DOCUMENT"].includes(component.format)) {
      return; // Ne pas ajouter de composant pour les headers média
    }
    
    // Extraire les variables de ce composant (dans l'ordre d'apparition)
    const variables = extractTemplateVariables(text);
    
    // Si ce composant a des variables, créer un composant avec paramètres
    if (variables.length > 0) {
      // Les paramètres doivent être dans l'ordre des numéros de variables
      // Meta remplace automatiquement toutes les occurrences de chaque variable
      const parameters = variables.map(varNum => {
        const value = variableValues[varNum] || "";
        return {
          type: "text",
          text: value
        };
      });
      
      components.push({
        type: type,
        parameters: parameters
      });
    }
  });
  
  return components;
}

