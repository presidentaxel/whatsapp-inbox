import { useState, useMemo } from "react";
import { 
  FiSearch, 
  FiMoreVertical, 
  FiSmartphone, 
  FiStar, 
  FiCheckCircle, 
  FiSettings,
  FiImage,
  FiVideo,
  FiHeadphones,
  FiFileText,
  FiMapPin,
  FiUser,
  FiZap
} from "react-icons/fi";
import { formatPhoneNumber } from "../../utils/formatPhone";
import { getConversationProfilePicture } from "../../utils/getProfilePicture";
import MobileAccountSelector from "./MobileAccountSelector";
import { useCurrentTime } from "../../hooks/useCurrentTime";

// Composant Avatar avec support des images
function ConversationAvatar({ conversation, displayName }) {
  const [imageError, setImageError] = useState(false);
  const profilePicture = getConversationProfilePicture(conversation);

  return (
    <div className="mobile-conv-item__avatar">
      {profilePicture && !imageError ? (
        <img 
          src={profilePicture} 
          alt={displayName}
          className="mobile-conv-item__avatar-img"
          onError={() => setImageError(true)}
          loading="lazy"
        />
      ) : null}
      <span className="mobile-conv-item__avatar-initial">
        {displayName.charAt(0).toUpperCase()}
      </span>
    </div>
  );
}

export default function MobileConversationsList({
  conversations,
  accounts,
  activeAccount,
  onSelectAccount,
  onSelectConversation,
  onConnectedDevices,
  onImportant,
  onMarkAllRead,
  onSettings
}) {
  const [showMenu, setShowMenu] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [filter, setFilter] = useState("all");
  
  // Gérer l'action "Important" en changeant le filtre
  const handleImportant = () => {
    if (onImportant) {
      onImportant();
    } else {
      // Fallback : changer le filtre vers "favorites"
      setFilter("favorites");
    }
  };
  
  // Utiliser le hook pour mettre à jour l'heure périodiquement
  // Mise à jour toutes les minutes pour les heures, et toutes les heures pour les dates
  const currentTime = useCurrentTime(60000); // 1 minute

  const currentAccount = accounts.find(a => a.id === activeAccount);

  // Filtrer par type de conversation
  const filteredByType = useMemo(() => {
    switch (filter) {
      case "unread":
        return conversations.filter((c) => c.unread_count > 0);
      case "favorites":
        return conversations.filter((c) => c.is_favorite);
      case "groups":
        return conversations.filter((c) => c.is_group);
      default:
        return conversations;
    }
  }, [conversations, filter]);

  // Filtrer par recherche
  const filteredConversations = filteredByType.filter(conv => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (conv.contacts?.display_name || conv.client_number || "").toLowerCase();
    return name.includes(term);
  });

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    // Interpréter comme UTC si pas de timezone explicite
    const dateStr = typeof timestamp === 'string' && !timestamp.match(/[Z+-]\d{2}:\d{2}$/) 
      ? timestamp + 'Z' 
      : timestamp;
    const date = new Date(dateStr);
    const now = currentTime; // Utiliser l'heure actuelle du hook
    
    // Calculer la différence en millisecondes
    const diff = now.getTime() - date.getTime();
    
    // Normaliser les dates pour comparer les jours (sans heures)
    const today = new Date(now);
    today.setHours(0, 0, 0, 0);
    const messageDate = new Date(date);
    messageDate.setHours(0, 0, 0, 0);
    
    const timeZone = 'Europe/Paris';
    
    // Aujourd'hui : afficher l'heure (comme WhatsApp)
    if (messageDate.getTime() === today.getTime()) {
      return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', timeZone });
    }
    
    // Hier : afficher "Hier"
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    if (messageDate.getTime() === yesterday.getTime()) {
      return "Hier";
    }
    
    // Cette semaine (7 derniers jours) : afficher le jour de la semaine
    const weekAgo = new Date(now);
    weekAgo.setDate(weekAgo.getDate() - 7);
    if (date > weekAgo) {
      const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
      return days[date.getDay()];
    }
    
    // Cette année : afficher le jour et le mois
    if (date.getFullYear() === now.getFullYear()) {
      return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', timeZone });
    }
    
    // Sinon : afficher la date complète
    return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit', timeZone });
  };

  return (
    <div className="mobile-conversations">
      {/* Header style WhatsApp */}
      <header className="mobile-conversations__header">
        <h1>WhatsApp</h1>
        <div className="mobile-conversations__actions">
          <button 
            className="icon-btn-round"
            onClick={() => setShowMenu(!showMenu)}
            title="Menu"
          >
            <FiMoreVertical />
          </button>
        </div>

        {showMenu && (
          <div className="mobile-conversations__menu">
            {onConnectedDevices && (
              <button onClick={() => { onConnectedDevices(); setShowMenu(false); }}>
                <FiSmartphone /> Appareils connectés
              </button>
            )}
            {onImportant && (
              <button onClick={() => { handleImportant(); setShowMenu(false); }}>
                <FiStar /> Important
              </button>
            )}
            {onMarkAllRead && (
              <button onClick={() => { onMarkAllRead(); setShowMenu(false); }}>
                <FiCheckCircle /> Tout lire
              </button>
            )}
            {onSettings && (
              <button onClick={() => { onSettings(); setShowMenu(false); }}>
                <FiSettings /> Paramètres
              </button>
            )}
          </div>
        )}
      </header>

      {/* Barre de recherche */}
      <div className="mobile-conversations__search">
        <div className="search-box">
          <FiSearch />
          <input
            type="text"
            placeholder="Rechercher..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Sélecteur de compte si plusieurs */}
      <div className="mobile-conversations__account-selector">
        <MobileAccountSelector
          accounts={accounts}
          value={activeAccount}
          onChange={onSelectAccount}
        />
      </div>

      {/* Filtres de types de conversations */}
      <div className="mobile-conversations__filters">
        <button
          className={`mobile-conversations__filter-btn ${filter === "all" ? "active" : ""}`}
          onClick={() => setFilter("all")}
        >
          Toutes
        </button>
        <button
          className={`mobile-conversations__filter-btn ${filter === "unread" ? "active" : ""}`}
          onClick={() => setFilter("unread")}
        >
          Non lues
        </button>
        <button
          className={`mobile-conversations__filter-btn ${filter === "favorites" ? "active" : ""}`}
          onClick={() => setFilter("favorites")}
        >
          Favoris
        </button>
        <button
          className={`mobile-conversations__filter-btn ${filter === "groups" ? "active" : ""}`}
          onClick={() => setFilter("groups")}
        >
          Groupes
        </button>
      </div>

      {/* Liste des conversations */}
      <div className="mobile-conversations__list">
        {filteredConversations.length === 0 ? (
          <div className="mobile-conversations__empty">
            <p>Aucune conversation</p>
          </div>
        ) : (
          filteredConversations.map((conv) => {
            const displayName = conv.contacts?.display_name || 
                               formatPhoneNumber(conv.client_number) ||
                               conv.client_number;
            const lastMessage = conv.last_message || "";
            const time = formatTime(conv.updated_at);
            const unread = conv.unread_count || 0;

            return (
              <div
                key={conv.id}
                className="mobile-conv-item"
                onClick={() => onSelectConversation(conv)}
              >
                <ConversationAvatar conversation={conv} displayName={displayName} />
                
                <div className="mobile-conv-item__content">
                  <div className="mobile-conv-item__header">
                    <div className="mobile-conv-item__header-left">
                      <span className="mobile-conv-item__name">
                        {displayName}
                      </span>
                      <span className={`mobile-conv-item__bot-indicator ${conv.bot_enabled ? 'bot' : 'human'}`}>
                        {conv.bot_enabled ? 'Bot' : 'Humain'}
                      </span>
                    </div>
                    <span className="mobile-conv-item__time">{time}</span>
                  </div>
                  
                  <div className="mobile-conv-item__footer">
                    <span className="mobile-conv-item__message">
                      {(() => {
                        // Remplacer les formats [type] par des icônes
                        if (lastMessage === "[image]") {
                          return <><FiImage /> Image</>;
                        } else if (lastMessage === "[video]") {
                          return <><FiVideo /> Vidéo</>;
                        } else if (lastMessage === "[audio]") {
                          return <><FiHeadphones /> Audio</>;
                        } else if (lastMessage === "[document]") {
                          return <><FiFileText /> Document</>;
                        } else if (lastMessage === "[location]") {
                          return <><FiMapPin /> Localisation</>;
                        } else if (lastMessage === "[contact]") {
                          return <><FiUser /> Contact</>;
                        } else if (lastMessage === "[interactive]") {
                          return <><FiZap /> Message interactif</>;
                        }
                        return lastMessage;
                      })()}
                    </span>
                    {unread > 0 && (
                      <span className="mobile-conv-item__badge">{unread}</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

