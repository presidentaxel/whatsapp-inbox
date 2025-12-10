import { FiCheck, FiCheckCircle } from "react-icons/fi";

/**
 * Composant pour afficher le statut d'un message (coches)
 * 
 * Pour les messages SORTANTS (qu'on envoie) : sent, delivered, read (masqué)
 * Pour les messages ENTRANTS (qu'on reçoit) : reçu, lu (si conversation marquée comme lue)
 */
export default function MessageStatus({ status, isOwnMessage, conversation, messageTimestamp }) {
  // Pour les messages sortants (qu'on envoie) : afficher les statuts WhatsApp
  if (isOwnMessage) {
    const normalizedStatus = (status || "sent").toLowerCase();

    // Les statuts WhatsApp possibles : sent, delivered, read, failed
    // On masque "read" comme demandé par l'utilisateur
    switch (normalizedStatus) {
      case "read":
        // On masque "read" : on affiche "delivered" à la place
        return (
          <span className="message-status message-status--delivered" title="Délivré">
            <FiCheckCircle />
            <FiCheckCircle />
          </span>
        );

      case "delivered":
        return (
          <span className="message-status message-status--delivered" title="Délivré">
            <FiCheckCircle />
            <FiCheckCircle />
          </span>
        );

      case "sent":
        return (
          <span className="message-status message-status--sent" title="Envoyé">
            <FiCheck />
          </span>
        );

      case "failed":
      case "error":
        return (
          <span className="message-status message-status--failed" title="Échec">
            ⚠️
          </span>
        );

      default:
        return (
          <span className="message-status message-status--sent" title="Envoyé">
            <FiCheck />
          </span>
        );
    }
  }

  // Pour les messages entrants (qu'on reçoit) : afficher "Reçu" et "Lu"
  const normalizedStatus = (status || "received").toLowerCase();
  
  // Vérifier si la conversation a été marquée comme lue
  const isConversationRead = conversation?.unread_count === 0;
  const messageTime = messageTimestamp ? new Date(messageTimestamp).getTime() : 0;
  const now = Date.now();
  const isMessageOld = messageTime > 0 && (now - messageTime) > 5000; // Message reçu il y a plus de 5 secondes
  
  // Si la conversation est marquée comme lue ET le message a été reçu il y a un moment, afficher "Lu"
  if (isConversationRead && isMessageOld && normalizedStatus === "received") {
    return (
      <span className="message-status message-status--read" title="Lu">
        <FiCheckCircle />
        <FiCheckCircle />
      </span>
    );
  }
  
  // Sinon, afficher "Reçu"
  if (normalizedStatus === "received") {
    return (
      <span className="message-status message-status--delivered" title="Reçu">
        <FiCheckCircle />
      </span>
    );
  }

  return null;
}

