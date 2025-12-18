import { useState } from "react";
import { IoCheckmark, IoCheckmarkDoneOutline } from "react-icons/io5";
import { FiRefreshCw, FiInfo } from "react-icons/fi";

/**
 * Composant pour afficher le statut d'un message (coches)
 * 
 * Pour les messages SORTANTS (qu'on envoie) : sent, delivered, read (masqué)
 * Pour les messages ENTRANTS (qu'on reçoit) : reçu, lu (si conversation marquée comme lue)
 */
export default function MessageStatus({ status, isOwnMessage, conversation, messageTimestamp, message, onResend }) {
  const [showErrorTooltip, setShowErrorTooltip] = useState(false);
  // Pour les messages sortants (qu'on envoie) : afficher les statuts WhatsApp
  if (isOwnMessage) {
    const normalizedStatus = (status || "sent").toLowerCase();

    // Les statuts WhatsApp possibles : pending, sent, delivered, read, failed
    // On masque "read" comme demandé par l'utilisateur
    switch (normalizedStatus) {
      case "pending":
        // Message en attente d'envoi (message optimiste)
        return (
          <span className="message-status message-status--sent" title="Envoi en cours...">
            <IoCheckmark />
          </span>
        );

      case "read":
        // Message lu - afficher en bleu
        return (
          <span className="message-status message-status--read" title="Lu">
            <IoCheckmarkDoneOutline />
          </span>
        );

      case "delivered":
        return (
          <span className="message-status message-status--delivered" title="Délivré">
            <IoCheckmarkDoneOutline />
          </span>
        );

      case "sent":
        return (
          <span className="message-status message-status--sent" title="Envoyé">
            <IoCheckmarkDoneOutline />
          </span>
        );

      case "failed":
      case "error":
        const errorMessage = message?.error_message;
        return (
          <div 
            className="message-status-container"
            onMouseEnter={() => errorMessage && setShowErrorTooltip(true)}
            onMouseLeave={() => setShowErrorTooltip(false)}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="message-status message-status--failed message-status--resend"
              title={errorMessage || "Message non envoyé - Cliquez pour renvoyer"}
              onClick={(e) => {
                e.stopPropagation();
                if (onResend && message) {
                  onResend(message);
                }
              }}
            >
              <span className="message-status__error-icon">⚠️</span>
              <span className="message-status__resend-text">Renvoyer</span>
              <FiRefreshCw className="message-status__resend-icon" />
            </button>
            {errorMessage && showErrorTooltip && (
              <div className="message-status__error-tooltip">
                <div className="message-status__error-tooltip-header">
                  <FiInfo />
                  <span>Détails de l'erreur</span>
                </div>
                <div className="message-status__error-tooltip-content">
                  {errorMessage}
                </div>
              </div>
            )}
          </div>
        );

      default:
        return (
          <span className="message-status message-status--sent" title="Envoyé">
            <IoCheckmarkDoneOutline />
          </span>
        );
    }
  }

  // Pour les messages entrants (qu'on reçoit) : ne rien afficher
  return null;
}

