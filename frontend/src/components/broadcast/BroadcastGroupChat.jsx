import { useState, useEffect } from "react";
import { FiSend, FiUsers, FiBarChart2 } from "react-icons/fi";
import { sendBroadcastCampaign, getBroadcastCampaigns } from "../../api/broadcastApi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { formatRelativeDateTime } from "../../utils/date";
import BroadcastCampaignStats from "./BroadcastCampaignStats";

export default function BroadcastGroupChat({
  group,
  accountId,
  onClose,
}) {
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [campaigns, setCampaigns] = useState([]);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [showStats, setShowStats] = useState(false);

  useEffect(() => {
    if (group) {
      loadCampaigns();
    }
  }, [group]);

  const loadCampaigns = async () => {
    if (!group) return;
    try {
      const res = await getBroadcastCampaigns({ groupId: group.id });
      setCampaigns(res.data || []);
    } catch (error) {
      console.error("Error loading campaigns:", error);
    }
  };

  const handleSend = async () => {
    if (!message.trim() || !group) return;

    setSending(true);
    try {
      const res = await sendBroadcastCampaign(group.id, {
        content_text: message,
        message_type: "text",
      });
      
      setMessage("");
      await loadCampaigns();
      // Afficher les stats de la nouvelle campagne
      if (res.data) {
        setSelectedCampaign(res.data);
        setShowStats(true);
      }
    } catch (error) {
      console.error("Error sending broadcast:", error);
      alert(error.response?.data?.detail || "Erreur lors de l'envoi");
    } finally {
      setSending(false);
    }
  };

  if (!group) {
    return (
      <div className="broadcast-group-chat empty">
        <p>Sélectionnez un groupe pour envoyer un message</p>
      </div>
    );
  }

  return (
    <div className="broadcast-group-chat">
      <div className="broadcast-group-chat__header">
        <div className="header-info">
          <h2>
            <FiUsers /> {group.name}
          </h2>
          {group.description && <p className="description">{group.description}</p>}
        </div>
        <button className="btn-icon" onClick={onClose}>
          ×
        </button>
      </div>

      <div className="broadcast-group-chat__content">
        {showStats && selectedCampaign ? (
          <div className="campaign-stats-view">
            <div className="stats-header">
              <button className="btn-secondary" onClick={() => setShowStats(false)}>
                ← Retour
              </button>
              <h3>Statistiques de la campagne</h3>
            </div>
            <BroadcastCampaignStats campaignId={selectedCampaign.id} />
          </div>
        ) : (
          <>
            <div className="campaigns-list">
              <div className="campaigns-header">
                <h3>Campagnes précédentes</h3>
                <button
                  className="btn-icon"
                  onClick={() => loadCampaigns()}
                  title="Actualiser"
                >
                  ↻
                </button>
              </div>
              {campaigns.length === 0 ? (
                <p className="empty">Aucune campagne envoyée</p>
              ) : (
                <div className="campaigns-items">
                  {campaigns.map((campaign) => (
                    <div
                      key={campaign.id}
                      className="campaign-item"
                      onClick={() => {
                        setSelectedCampaign(campaign);
                        setShowStats(true);
                      }}
                    >
                      <div className="campaign-content">
                        <p>{campaign.content_text}</p>
                        <div className="campaign-meta">
                          <span>{formatRelativeDateTime(campaign.sent_at)}</span>
                          <span className="stats-badge">
                            {campaign.read_count || 0} lus / {campaign.replied_count || 0} réponses
                          </span>
                        </div>
                      </div>
                      <button
                        className="btn-icon"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedCampaign(campaign);
                          setShowStats(true);
                        }}
                      >
                        <FiBarChart2 />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="message-input-area">
              <textarea
                className="message-input"
                placeholder="Tapez votre message à envoyer à tous les destinataires..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={4}
                disabled={sending}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    handleSend();
                  }
                }}
              />
              <div className="message-actions">
                <small>Ctrl+Entrée pour envoyer</small>
                <button
                  className="btn-primary"
                  onClick={handleSend}
                  disabled={!message.trim() || sending}
                >
                  <FiSend /> {sending ? "Envoi..." : "Envoyer à tous"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

