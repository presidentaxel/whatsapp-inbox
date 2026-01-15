import { useState, useEffect } from "react";
import { getCampaignStats, getCampaignHeatmap, getCampaignTimeline } from "../../api/broadcastApi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { formatRelativeDateTime } from "../../utils/date";
import { FiCheck, FiX, FiEye, FiMessageCircle, FiClock } from "react-icons/fi";

export default function BroadcastCampaignStats({ campaignId }) {
  const [stats, setStats] = useState(null);
  const [heatmap, setHeatmap] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // all, read, replied, failed

  useEffect(() => {
    loadStats();
    const interval = setInterval(loadStats, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [campaignId]);

  const loadStats = async () => {
    try {
      const [statsRes, heatmapRes, timelineRes] = await Promise.all([
        getCampaignStats(campaignId),
        getCampaignHeatmap(campaignId),
        getCampaignTimeline(campaignId),
      ]);
      setStats(statsRes.data);
      setHeatmap(heatmapRes.data);
      setTimeline(timelineRes.data);
    } catch (error) {
      console.error("Error loading stats:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="campaign-stats loading">Chargement des statistiques...</div>;
  }

  if (!stats) {
    return <div className="campaign-stats error">Erreur lors du chargement</div>;
  }

  const { campaign, overview, recipients } = stats;

  const filteredRecipients = recipients.filter((r) => {
    if (filter === "read") return r.read_at;
    if (filter === "replied") return r.replied_at;
    if (filter === "failed") return r.failed_at;
    return true;
  });

  // Calculer les métriques de temps moyen
  const readTimes = recipients
    .filter((r) => r.time_to_read)
    .map((r) => {
      const match = r.time_to_read.match(/(\d+):(\d+):(\d+)/);
      if (match) {
        return parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseInt(match[3]);
      }
      return 0;
    });

  const replyTimes = recipients
    .filter((r) => r.time_to_reply)
    .map((r) => {
      const match = r.time_to_reply.match(/(\d+):(\d+):(\d+)/);
      if (match) {
        return parseInt(match[1]) * 3600 + parseInt(match[2]) * 60 + parseInt(match[3]);
      }
      return 0;
    });

  const avgReadTime = readTimes.length > 0
    ? Math.round(readTimes.reduce((a, b) => a + b, 0) / readTimes.length / 60)
    : 0;

  const avgReplyTime = replyTimes.length > 0
    ? Math.round(replyTimes.reduce((a, b) => a + b, 0) / replyTimes.length / 60)
    : 0;

  return (
    <div className="campaign-stats">
      {/* Métriques principales */}
      <div className="stats-overview">
        <div className="stat-card">
          <div className="stat-value">{overview.total}</div>
          <div className="stat-label">Destinataires</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.delivered}</div>
          <div className="stat-label">Livrés</div>
          <div className="stat-rate">{overview.delivery_rate}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.read}</div>
          <div className="stat-label">Lus</div>
          <div className="stat-rate">{overview.read_rate}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{overview.replied}</div>
          <div className="stat-label">Répondu</div>
          <div className="stat-rate">{overview.reply_rate}%</div>
        </div>
        {overview.failed > 0 && (
          <div className="stat-card error">
            <div className="stat-value">{overview.failed}</div>
            <div className="stat-label">Échoués</div>
          </div>
        )}
      </div>

      {/* Métriques de temps */}
      {avgReadTime > 0 && (
        <div className="stats-timing">
          <div className="timing-item">
            <FiClock /> Temps moyen de lecture: <strong>{avgReadTime} min</strong>
          </div>
          {avgReplyTime > 0 && (
            <div className="timing-item">
              <FiClock /> Temps moyen de réponse: <strong>{avgReplyTime} min</strong>
            </div>
          )}
        </div>
      )}

      {/* Heat Map simple (heures) */}
      {heatmap && (
        <div className="stats-heatmap">
          <h4>Activité par heure</h4>
          <div className="heatmap-hours">
            {heatmap.read_by_hour.map((item, idx) => {
              const maxCount = Math.max(
                ...heatmap.read_by_hour.map((h) => h.count),
                ...heatmap.reply_by_hour.map((h) => h.count),
                1
              );
              const intensity = item.count / maxCount;
              return (
                <div key={idx} className="heatmap-hour">
                  <div
                    className="heatmap-bar"
                    style={{
                      height: `${intensity * 100}%`,
                      backgroundColor: `rgba(34, 197, 94, ${0.3 + intensity * 0.7})`,
                    }}
                    title={`${item.hour}h: ${item.count} lectures`}
                  />
                  <small>{item.hour}h</small>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Timeline simple */}
      {timeline && timeline.length > 0 && (
        <div className="stats-timeline">
          <h4>Évolution dans le temps</h4>
          <div className="timeline-chart">
            <div className="timeline-bars">
              {timeline.slice(-24).map((point, idx) => {
                const maxReads = Math.max(...timeline.map((t) => t.reads), 1);
                const maxReplies = Math.max(...timeline.map((t) => t.replies), 1);
                return (
                  <div key={idx} className="timeline-bar">
                    <div
                      className="bar-reads"
                      style={{ height: `${(point.reads / maxReads) * 100}%` }}
                      title={`${point.reads} lectures`}
                    />
                    <div
                      className="bar-replies"
                      style={{ height: `${(point.replies / maxReplies) * 100}%` }}
                      title={`${point.replies} réponses`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Liste des destinataires */}
      <div className="stats-recipients">
        <div className="recipients-header">
          <h4>Destinataires ({filteredRecipients.length})</h4>
          <div className="filter-buttons">
            <button
              className={filter === "all" ? "active" : ""}
              onClick={() => setFilter("all")}
            >
              Tous
            </button>
            <button
              className={filter === "read" ? "active" : ""}
              onClick={() => setFilter("read")}
            >
              Lus
            </button>
            <button
              className={filter === "replied" ? "active" : ""}
              onClick={() => setFilter("replied")}
            >
              Répondu
            </button>
            {overview.failed > 0 && (
              <button
                className={filter === "failed" ? "active" : ""}
                onClick={() => setFilter("failed")}
              >
                Échoués
              </button>
            )}
          </div>
        </div>

        <div className="recipients-table">
          <table>
            <thead>
              <tr>
                <th>Destinataire</th>
                <th>Statut</th>
                <th>Lu le</th>
                <th>Répondu le</th>
                <th>Délai</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecipients.map((recipient) => {
                const displayName =
                  recipient.broadcast_group_recipients?.display_name ||
                  recipient.broadcast_group_recipients?.contacts?.display_name ||
                  formatPhoneNumber(recipient.phone_number);

                const getStatusIcon = () => {
                  if (recipient.failed_at) return <FiX className="status-failed" />;
                  if (recipient.replied_at) return <FiMessageCircle className="status-replied" />;
                  if (recipient.read_at) return <FiEye className="status-read" />;
                  if (recipient.delivered_at) return <FiCheck className="status-delivered" />;
                  return <FiCheck className="status-sent" />;
                };

                return (
                  <tr key={recipient.id}>
                    <td>
                      <strong>{displayName}</strong>
                      <br />
                      <small>{formatPhoneNumber(recipient.phone_number)}</small>
                    </td>
                    <td>{getStatusIcon()}</td>
                    <td>
                      {recipient.read_at
                        ? formatRelativeDateTime(recipient.read_at)
                        : recipient.delivered_at
                        ? "Livré"
                        : "Envoyé"}
                    </td>
                    <td>
                      {recipient.replied_at
                        ? formatRelativeDateTime(recipient.replied_at)
                        : "—"}
                    </td>
                    <td>
                      {recipient.time_to_read && (
                        <span className="time-badge">
                          {(() => {
                            const match = recipient.time_to_read.match(/(\d+):(\d+):(\d+)/);
                            if (match) {
                              const hours = parseInt(match[1]);
                              const mins = parseInt(match[2]);
                              if (hours > 0) return `${hours}h ${mins}m`;
                              return `${mins}m`;
                            }
                            return recipient.time_to_read;
                          })()}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

