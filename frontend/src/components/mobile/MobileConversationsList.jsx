import { useState } from "react";
import { FiSearch, FiMoreVertical, FiLogOut } from "react-icons/fi";
import { formatPhoneNumber } from "../../utils/formatPhone";

export default function MobileConversationsList({
  conversations,
  accounts,
  activeAccount,
  onSelectAccount,
  onSelectConversation,
  onLogout
}) {
  const [showMenu, setShowMenu] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const currentAccount = accounts.find(a => a.id === activeAccount);

  const filteredConversations = conversations.filter(conv => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (conv.contacts?.display_name || conv.client_number || "").toLowerCase();
    return name.includes(term);
  });

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    // Moins de 24h : afficher l'heure
    if (diff < 24 * 60 * 60 * 1000) {
      return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    }
    
    // Cette semaine : afficher le jour
    if (diff < 7 * 24 * 60 * 60 * 1000) {
      return date.toLocaleDateString('fr-FR', { weekday: 'short' });
    }
    
    // Sinon : afficher la date
    return date.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' });
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
            <button onClick={onLogout}>
              <FiLogOut /> Déconnexion
            </button>
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
      {accounts.length > 1 && (
        <div className="mobile-conversations__account-selector">
          <select
            value={activeAccount}
            onChange={(e) => onSelectAccount(e.target.value)}
          >
            {accounts.map(acc => (
              <option key={acc.id} value={acc.id}>
                {acc.name}
              </option>
            ))}
          </select>
        </div>
      )}

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
                <div className="mobile-conv-item__avatar">
                  {displayName.charAt(0).toUpperCase()}
                </div>
                
                <div className="mobile-conv-item__content">
                  <div className="mobile-conv-item__header">
                    <span className="mobile-conv-item__name">
                      {displayName}
                    </span>
                    <span className="mobile-conv-item__time">{time}</span>
                  </div>
                  
                  <div className="mobile-conv-item__footer">
                    <span className="mobile-conv-item__message">
                      {lastMessage}
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

