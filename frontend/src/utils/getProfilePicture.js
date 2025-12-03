/**
 * Construit l'URL de l'image de profil d'un contact WhatsApp
 * @param {string} phoneNumber - Numéro WhatsApp du contact
 * @param {string} accountId - ID du compte WhatsApp
 * @returns {string|null} URL de l'image de profil ou null
 */
export function getProfilePictureUrl(phoneNumber, accountId) {
  if (!phoneNumber || !accountId) return null;
  
  // Pour l'instant, on utilise une URL générique via l'API backend
  // TODO: Implémenter l'endpoint backend pour récupérer les images de profil WhatsApp
  // L'API WhatsApp permet de récupérer les images via GET /{PHONE_NUMBER_ID}/contacts/{phone_number}
  return null;
}

/**
 * Récupère l'URL de l'image de profil depuis les données de conversation
 * @param {Object} conversation - Objet conversation
 * @returns {string|null} URL de l'image de profil ou null
 */
export function getConversationProfilePicture(conversation) {
  // Vérifier si l'image est déjà dans les données
  if (conversation?.contacts?.profile_picture_url) {
    return conversation.contacts.profile_picture_url;
  }
  
  if (conversation?.profile_picture_url) {
    return conversation.profile_picture_url;
  }
  
  // Si pas d'image disponible, retourner null pour utiliser l'initiale
  return null;
}

