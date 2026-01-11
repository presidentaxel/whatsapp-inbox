/**
 * Utilitaires pour gérer les variables dans les templates WhatsApp
 */

/**
 * Extrait toutes les variables d'un template ({{1}}, {{2}}, etc.)
 * @param {string} text - Le texte du template
 * @returns {Array<number>} - Liste des numéros de variables trouvées, triés
 */
/**
 * Extrait toutes les variables d'un template ({{1}}, {{2}}, {{}} (vide), {{sender_name}}, etc.)
 * @param {string} text - Le texte du template
 * @returns {Array<number|string>} - Liste des identifiants de variables trouvées
 * Note: Les {{}} vides sont automatiquement assignées à des numéros séquentiels (1, 2, 3...)
 * Les variables nommées ({{sender_name}}) gardent leur nom
 */
export function extractTemplateVariables(text) {
  if (!text || typeof text !== 'string') {
    console.log("🔍 extractTemplateVariables: texte vide ou non-string", { text, type: typeof text });
    return [];
  }
  
  console.log("🔍 extractTemplateVariables: Analyse du texte", {
    textLength: text.length,
    textPreview: text.substring(0, 500),
    containsDoubleBraces: text.includes('{{'),
    fullText: text
  });
  
  // Utiliser extractTemplateVariablesWithMapping pour obtenir toutes les variables avec leurs détails
  const allMatches = extractTemplateVariablesWithMapping(text);
  
  // Extraire les identifiants uniques (numéros ou noms) pour compatibilité
  const seenIds = new Set();
  const uniqueIds = [];
  
  allMatches.forEach(m => {
    // Pour les variables nommées, utiliser le nom comme ID
    // Pour les variables numérotées ou vides, utiliser le numéro
    const id = m.name || m.num;
    if (!seenIds.has(id)) {
      seenIds.add(id);
      uniqueIds.push(id);
    }
  });
  
  console.log("🔍 extractTemplateVariables: Résultat final", {
    variablesCount: uniqueIds.length,
    variables: uniqueIds,
    totalMatches: allMatches.length,
    hasEmptyVars: allMatches.some(m => m.pattern === '{{}}'),
    hasNamedVars: allMatches.some(m => m.isNamed),
    allMatches: allMatches.map(m => ({ id: m.name || m.num, num: m.num, name: m.name, pattern: m.pattern, pos: m.position }))
  });
  
  // Retourner les IDs pour compatibilité (mélange de numéros et noms)
  return uniqueIds;
}

/**
 * Vérifie si un texte contient des variables (même vides comme {{}})
 * @param {string} text - Le texte à vérifier
 * @returns {boolean} - True si le texte contient au moins une variable
 */
export function hasAnyVariablePattern(text) {
  if (!text || typeof text !== 'string') return false;
  // Détecte {{1}}, {{2}}, mais aussi {{}} (vide) et autres formats
  return /\{\{[\s\d]*\}\}/.test(text);
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
    // Pour le tri, gérer à la fois les numéros et les strings (noms de variables)
    result[key] = [...new Set(result[key])].sort((a, b) => {
      // Si les deux sont des numéros, trier numériquement
      if (typeof a === 'number' && typeof b === 'number') {
        return a - b;
      }
      // Si l'un est un string (nom), le mettre après les numéros
      if (typeof a === 'string' && typeof b === 'number') {
        return 1; // String après numéro
      }
      if (typeof a === 'number' && typeof b === 'string') {
        return -1; // Numéro avant string
      }
      // Si les deux sont des strings, trier alphabétiquement
      if (typeof a === 'string' && typeof b === 'string') {
        return a.localeCompare(b);
      }
      return 0;
    });
  });
  
  return result;
}

/**
 * Vérifie si un template a des variables
 * @param {Object} template - L'objet template avec ses components
 * @returns {boolean} - True si le template a au moins une variable
 */
export function hasTemplateVariables(template) {
  if (!template) {
    console.log("🔍 hasTemplateVariables: template est null/undefined");
    return false;
  }
  
  console.log("🔍 hasTemplateVariables: vérification du template", {
    name: template.name,
    hasComponents: !!template.components,
    componentsCount: template.components?.length || 0
  });
  
  // Vérifier d'abord dans les components
  if (template.components && Array.isArray(template.components)) {
    console.log("🔍 hasTemplateVariables: vérification des components", template.components);
    const variables = extractVariablesFromComponents(template.components);
    console.log("🔍 hasTemplateVariables: variables trouvées dans components", variables);
    
    if (variables.header.length > 0 || 
        variables.body.length > 0 || 
        variables.footer.length > 0 || 
        variables.buttons.length > 0) {
      console.log("✅ hasTemplateVariables: Variables détectées dans les components");
      return true;
    }
  }
  
  // Vérifier aussi dans le texte brut du template si disponible
  if (template.text || template.body) {
    const text = template.text || template.body;
    console.log("🔍 hasTemplateVariables: vérification du texte brut", text);
    const textVariables = extractTemplateVariables(text);
    console.log("🔍 hasTemplateVariables: variables trouvées dans le texte", textVariables);
    if (textVariables.length > 0) {
      console.log("✅ hasTemplateVariables: Variables détectées dans le texte brut");
      return true;
    }
  }
  
  // Vérifier dans le nom du template aussi (parfois les variables sont là)
  if (template.name) {
    const nameVariables = extractTemplateVariables(template.name);
    if (nameVariables.length > 0) {
      console.log("✅ hasTemplateVariables: Variables détectées dans le nom");
      return true;
    }
  }
  
  // Vérifier aussi s'il y a des patterns {{}} vides (extractTemplateVariables devrait déjà les détecter maintenant)
  // Mais on fait une vérification supplémentaire au cas où
  const allTexts = [
    ...(template.components || []).map(c => c.text || ""),
    template.text || "",
    template.body || "",
    template.name || ""
  ].filter(t => t && typeof t === 'string');
  
  for (const text of allTexts) {
    // extractTemplateVariables devrait maintenant détecter les {{}} vides automatiquement
    const vars = extractTemplateVariables(text);
    if (vars.length > 0) {
      console.log("✅ hasTemplateVariables: Variables détectées dans le texte (incluant {{}} vides):", vars);
      return true;
    }
    
    // Vérification de secours pour les {{}} vides et variables nommées
    if (/\{\{\s*\}\}/.test(text)) {
      console.warn("⚠️ hasTemplateVariables: Variables vides {{}} détectées (vérification de secours) - format non standard Meta");
      return true;
    }
    // Vérifier aussi les variables nommées ({{sender_name}}, etc.)
    if (/\{\{\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\}\}/.test(text)) {
      console.log("✅ hasTemplateVariables: Variables nommées détectées (vérification de secours)");
      return true;
    }
  }
  
  console.log("❌ hasTemplateVariables: Aucune variable détectée");
  return false;
}

/**
 * Extrait toutes les variables d'un template et retourne un mapping position -> numéro
 * @param {string} text - Le texte du template
 * @returns {Array<{num: number, pattern: string, position: number, isNumbered: boolean}>} - Liste des variables avec leur pattern original et position
 */
export function extractTemplateVariablesWithMapping(text) {
  if (!text || typeof text !== 'string') return [];
  
  const allMatches = [];
  const positions = new Set(); // Pour éviter les doublons de position
  let autoVarNumber = 1; // Pour assigner des numéros aux variables sans numéro
  
  // 1. D'abord, trouver toutes les variables numérotées ({{1}}, {{2}}, etc.)
  const numberedRegex = /\{\{\s*(\d+)\s*\}\}/g;
  let match;
  
  while ((match = numberedRegex.exec(text)) !== null) {
    const varNumber = parseInt(match[1], 10);
    if (!positions.has(match.index)) {
      positions.add(match.index);
      allMatches.push({
        num: varNumber,
        name: null,
        pattern: match[0],
        position: match.index,
        isNumbered: true,
        isNamed: false
      });
      // Mettre à jour autoVarNumber si nécessaire
      if (varNumber >= autoVarNumber) {
        autoVarNumber = varNumber + 1;
      }
      console.log(`✅ extractTemplateVariablesWithMapping: Variable {{${varNumber}}} trouvée à la position ${match.index}`);
    }
  }
  
  // 2. Ensuite, trouver les variables nommées ({{sender_name}}, {{company_name}}, etc.)
  // Format: {{nom_variable}} où nom_variable commence par une lettre ou underscore, suivi de lettres/chiffres/underscores
  const namedRegex = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;
  namedRegex.lastIndex = 0; // Reset
  
  while ((match = namedRegex.exec(text)) !== null) {
    const varName = match[1];
    if (!positions.has(match.index)) {
      positions.add(match.index);
      const assignedNum = autoVarNumber++;
      allMatches.push({
        num: assignedNum, // Numéro pour l'ordre dans l'interface et l'API
        name: varName, // Nom original pour le remplacement dans l'aperçu
        pattern: match[0],
        position: match.index,
        isNumbered: false,
        isNamed: true
      });
      console.log(`✅ extractTemplateVariablesWithMapping: Variable nommée {{${varName}}} trouvée à la position ${match.index}, assignée au numéro ${assignedNum} pour l'ordre`);
    }
  }
  
  // 3. Enfin, trouver les {{}} vides et leur assigner des numéros séquentiels
  const emptyRegex = /\{\{\s*\}\}/g;
  let emptyMatch;
  emptyRegex.lastIndex = 0; // Reset
  
  while ((emptyMatch = emptyRegex.exec(text)) !== null) {
    if (!positions.has(emptyMatch.index)) {
      positions.add(emptyMatch.index);
      const assignedNum = autoVarNumber++;
      allMatches.push({
        num: assignedNum,
        name: null,
        pattern: '{{}}',
        position: emptyMatch.index,
        isNumbered: false,
        isNamed: false
      });
      console.log(`✅ extractTemplateVariablesWithMapping: Variable vide {{}} assignée au numéro ${assignedNum} à la position ${emptyMatch.index}`);
    }
  }
  
  // Trier par position (ordre d'apparition dans le texte)
  allMatches.sort((a, b) => a.position - b.position);
  
  console.log("🔍 extractTemplateVariablesWithMapping: Résultat", {
    totalMatches: allMatches.length,
    hasNamedVars: allMatches.some(m => m.isNamed),
    hasEmptyVars: allMatches.some(m => m.pattern === '{{}}'),
    matches: allMatches.map(m => ({ num: m.num, name: m.name, pattern: m.pattern, pos: m.position }))
  });
  
  return allMatches;
}

/**
 * Construit les composants pour l'API Meta avec les paramètres remplis
 * @param {Object} template - L'objet template avec ses components
 * @param {Object} variableValues - Objet avec les valeurs des variables { 1: "valeur1", 2: "valeur2" }
 * @returns {Array} - Composants formatés pour l'API Meta
 * 
 * Note: Selon la documentation Meta, les paramètres doivent être dans l'ordre des numéros de variables
 * ({{1}}, {{2}}, {{3}}, etc.), même si une variable apparaît plusieurs fois dans le texte.
 * Les {{}} vides sont automatiquement converties en {{1}}, {{2}}, etc. dans l'ordre d'apparition.
 */
export function buildTemplateComponents(template, variableValues) {
  if (!template || !template.components) return [];
  
  console.log("🔧 buildTemplateComponents: Construction des components", {
    templateName: template.name,
    variableValues
  });
  
  const components = [];
  
  template.components.forEach((component, index) => {
    const type = component.type?.toUpperCase();
    const text = component.text || "";
    
    // Ignorer les HEADER avec format IMAGE/VIDEO/DOCUMENT (géré par le backend)
    if (type === "HEADER" && component.format && 
        ["IMAGE", "VIDEO", "DOCUMENT"].includes(component.format)) {
      console.log(`⏭️ buildTemplateComponents: Component ${index} (${type}) ignoré (média)`);
      return; // Ne pas ajouter de composant pour les headers média
    }
    
    // Extraire les variables avec leur mapping (incluant les {{}} vides)
    const variableMapping = extractTemplateVariablesWithMapping(text);
    
    console.log(`🔍 buildTemplateComponents: Component ${index} (${type})`, {
      text: text.substring(0, 200),
      variableMapping,
      hasVariables: variableMapping.length > 0
    });
    
    // Si ce composant a des variables, créer un composant avec paramètres
    if (variableMapping.length > 0) {
      // IMPORTANT: Pour Meta API, les paramètres doivent être dans l'ordre d'apparition dans le template
      // Meta attend que les paramètres soient dans l'ordre séquentiel basé sur l'ordre d'apparition (position)
      // Selon la documentation Meta: "Parameters are provided in sequential order starting from {{1}}"
      // Les paramètres doivent correspondre à l'ordre d'apparition des variables dans le template original
      const seenNums = new Set(); // Pour éviter les doublons si une variable apparaît plusieurs fois
      const parameters = [];
      const paramMap = new Map(); // Pour mapper num -> paramètre (pour éviter les doublons)
      
      // Trier les variables par position (ordre d'apparition dans le texte)
      // C'est l'ordre dans lequel Meta attend les paramètres
      const sortedByPosition = [...variableMapping].sort((a, b) => a.position - b.position);
      
      console.log(`🔍 buildTemplateComponents: Variables triées par position pour ${type}:`, sortedByPosition.map(v => ({
        num: v.num,
        name: v.name,
        position: v.position,
        pattern: v.pattern
      })));
      
      sortedByPosition.forEach(({ num, name, pattern, position, isNumbered, isNamed }) => {
        // Éviter les doublons si une variable apparaît plusieurs fois
        // Meta attend un seul paramètre par variable unique, même si elle apparaît plusieurs fois
        if (!seenNums.has(num)) {
          seenNums.add(num);
          const value = variableValues[num] || variableValues[String(num)] || "";
          const varDisplay = isNamed && name ? `${name} (${num})` : num;
          
          // Stocker le paramètre dans la map avec le numéro comme clé
          // L'ordre dans l'array parameters sera basé sur l'ordre d'apparition (position)
          if (!paramMap.has(num)) {
            // Ne pas ajouter de paramètre vide (Meta peut rejeter)
            if (value && value.trim() !== "") {
              paramMap.set(num, {
                type: "text",
                text: value.trim()
              });
              console.log(`📝 buildTemplateComponents: Paramètre ajouté pour variable ${varDisplay} (pattern: "${pattern}", position: ${position}, isNamed: ${isNamed}): "${value.trim()}"`);
            } else {
              console.warn(`⚠️ buildTemplateComponents: Variable ${varDisplay} a une valeur vide, paramètre non ajouté`);
            }
          }
        }
      });
      
      // Maintenant, créer les parameters dans l'ordre séquentiel des numéros (1, 2, 3...)
      // mais seulement pour les variables qui ont des valeurs
      const sortedNums = Array.from(paramMap.keys()).sort((a, b) => a - b);
      sortedNums.forEach(num => {
        const param = paramMap.get(num);
        if (param) {
          parameters.push(param);
        }
      });
      
      // IMPORTANT: Meta exige que si un component a des variables dans le template,
      // on envoie TOUJOURS un composant avec des paramètres, même si certains sont vides
      // Mais Meta peut aussi rejeter les paramètres vides, donc on envoie seulement ceux qui ont des valeurs
      if (parameters.length > 0) {
        components.push({
          type: type,
          parameters: parameters
        });
        console.log(`✅ buildTemplateComponents: Component ${type} ajouté avec ${parameters.length} paramètres`);
        console.log(`📋 buildTemplateComponents: Paramètres dans l'ordre (séquentiel 1, 2, 3...):`, parameters.map((p, idx) => ({
          index: idx + 1,
          type: p.type,
          text: p.text?.substring(0, 50) + (p.text?.length > 50 ? '...' : ''),
          textLength: p.text?.length || 0
        })));
      } else {
        // Si aucune variable n'a de valeur, Meta pourrait quand même attendre un component vide
        // Mais généralement Meta rejette ça, donc on ne l'ajoute pas
        console.warn(`⚠️ buildTemplateComponents: Aucun paramètre valide pour le component ${type} (${variableMapping.length} variables détectées mais aucune valeur remplie), component non ajouté`);
        console.warn(`⚠️ buildTemplateComponents: Variables détectées:`, variableMapping.map(v => ({
          num: v.num,
          name: v.name,
          pattern: v.pattern,
          valueInVariableValues: variableValues[v.num] || variableValues[String(v.num)] || "VIDE"
        })));
      }
    }
  });
  
  console.log("🔧 buildTemplateComponents: Résultat final", {
    componentsCount: components.length,
    components: components
  });
  
  return components;
}

