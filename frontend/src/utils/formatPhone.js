/**
 * Formate un numéro de téléphone au format international lisible
 * 
 * @param {string} phone - Le numéro brut (ex: "33628005265")
 * @returns {string} Le numéro formaté (ex: "(+33) 6 28 00 52 65")
 * 
 * @example
 * formatPhoneNumber("33628005265") // "(+33) 6 28 00 52 65"
 * formatPhoneNumber("33783614530") // "(+33) 7 83 61 45 30"
 * formatPhoneNumber("33123456789") // "(+33) 1 23 45 67 89"
 */
export function formatPhoneNumber(phone) {
  if (!phone) return "";
  
  // Nettoyer le numéro (retirer espaces, tirets, etc.)
  const cleaned = String(phone).replace(/\D/g, "");
  
  if (!cleaned) return phone;
  
  // Format français avec indicatif international 33
  if (cleaned.startsWith("33") && cleaned.length === 11) {
    const countryCode = "33";
    const nationalNumber = cleaned.substring(2); // 9 chiffres
    
    // Format français : X XX XX XX XX (premier chiffre seul, puis groupes de 2)
    const firstDigit = nationalNumber[0];
    const rest = nationalNumber.substring(1);
    const groups = rest.match(/.{1,2}/g) || [];
    const formatted = [firstDigit, ...groups].join(" ");
    
    return `(+${countryCode}) ${formatted}`;
  }
  
  // Format international générique (11+ chiffres)
  if (cleaned.length > 10) {
    // Essayer de détecter l'indicatif pays (2-3 chiffres au début)
    const possibleCountryCode = cleaned.substring(0, 2);
    const rest = cleaned.substring(2);
    
    // Premier chiffre seul, puis groupes de 2
    if (rest.length > 0) {
      const firstDigit = rest[0];
      const remaining = rest.substring(1);
      const groups = remaining.match(/.{1,2}/g) || [];
      const formatted = [firstDigit, ...groups].join(" ");
      return `(+${possibleCountryCode}) ${formatted}`;
    }
  }
  
  // Format national simple (grouper par 2)
  const groups = cleaned.match(/.{1,2}/g) || [];
  return groups.join(" ");
}

