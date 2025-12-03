import { useCallback, useEffect, useState } from "react";
import { FiMessageSquare, FiUsers, FiTool, FiMessageCircle, FiSettings, FiUserCheck } from "react-icons/fi";
import { getConversations, markConversationRead } from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts } from "../api/contactsApi";
import { clearAuthSession } from "../utils/secureStorage";
import { saveActiveAccount, getActiveAccount } from "../utils/accountStorage";
import MobileConversationsList from "../components/mobile/MobileConversationsList";
import MobileChatWindow from "../components/mobile/MobileChatWindow";
import MobileContactsPanel from "../components/mobile/MobileContactsPanel";
import MobileWhatsAppPanel from "../components/mobile/MobileWhatsAppPanel";
import MobileGeminiPanel from "../components/mobile/MobileGeminiPanel";
import MobileNotificationSettings from "../components/mobile/MobileNotificationSettings";
import MobileSettings from "../components/mobile/MobileSettings";
import MobileConnectedDevices from "../components/mobile/MobileConnectedDevices";
import MobileTeamPanel from "../components/mobile/MobileTeamPanel";
import { useGlobalNotifications } from "../hooks/useGlobalNotifications";
import "../styles/mobile-inbox.css";

export default function MobileInboxPage({ onLogout }) {
  const [activeTab, setActiveTab] = useState("conversations");
  const [accounts, setAccounts] = useState([]);
  const [activeAccount, setActiveAccount] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [selectedContactFromChat, setSelectedContactFromChat] = useState(null);

  // Charger les comptes
  const loadAccounts = useCallback(async () => {
    try {
      const res = await getAccounts();
      const payload = Array.isArray(res?.data) ? res.data : res?.data?.data || [];
      setAccounts(payload);
      
      // Essayer de restaurer le compte sauvegardé
      const savedAccountId = getActiveAccount();
      const savedAccountExists = savedAccountId && payload.some((acc) => acc.id === savedAccountId);
      
      if (payload.length > 0 && !activeAccount) {
        // Si un compte est sauvegardé et existe toujours, l'utiliser
        if (savedAccountExists) {
          setActiveAccount(savedAccountId);
        } else {
          // Sinon, prendre le premier compte disponible
          setActiveAccount(payload[0].id);
        }
      }
    } catch (error) {
      console.error("Erreur chargement comptes:", error);
    }
  }, [activeAccount]);

  // Charger les conversations
  const refreshConversations = useCallback(async (accountId) => {
    if (!accountId) return;
    try {
      const res = await getConversations(accountId);
      setConversations(res.data || []);
    } catch (error) {
      console.error("Erreur chargement conversations:", error);
    }
  }, []);

  // Charger les contacts
  const loadContacts = useCallback(async () => {
    try {
      const res = await getContacts();
      setContacts(res.data || []);
    } catch (error) {
      console.error("Erreur chargement contacts:", error);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
    loadContacts();
  }, [loadAccounts, loadContacts]);

  // Sauvegarder le compte actif quand il change
  useEffect(() => {
    if (activeAccount) {
      saveActiveAccount(activeAccount);
    }
  }, [activeAccount]);

  useEffect(() => {
    if (activeAccount) {
      refreshConversations(activeAccount);
      
      // Polling toutes les 5 secondes
      const interval = setInterval(() => {
        refreshConversations(activeAccount);
      }, 5000);
      
      return () => clearInterval(interval);
    }
  }, [activeAccount, refreshConversations]);

  // Écouter TOUS les nouveaux messages pour afficher des notifications
  // Fonctionne comme WhatsApp : notifications pour TOUS les messages entrants
  // Peu importe le compte, la plateforme, etc.
  useGlobalNotifications(selectedConversation?.id);

  const handleSelectConversation = async (conv) => {
    setSelectedConversation(conv);
    if (conv?.unread_count) {
      await markConversationRead(conv.id);
      refreshConversations(activeAccount);
    }
  };

  const handleBackToList = () => {
    setSelectedConversation(null);
  };

  const handleLogout = () => {
    clearAuthSession();
    onLogout();
  };

  const handleConnectedDevices = () => {
    // Afficher les informations du compte actif comme "appareils connectés"
    setActiveTab("connected-devices");
  };

  const handleImportant = () => {
    // Cette fonction peut être utilisée pour naviguer vers une vue "Important"
    // Pour l'instant, on peut juste afficher un message
    // Le filtre "favorites" est déjà géré dans MobileConversationsList
    // On pourrait aussi naviguer vers une vue dédiée aux favoris
  };

  const handleMarkAllRead = async () => {
    try {
      // Marquer toutes les conversations non lues comme lues pour le compte actif uniquement
      // Les conversations sont déjà filtrées par compte dans le backend, mais on double-vérifie
      const unreadConversations = conversations.filter(
        c => c.unread_count > 0 && (!c.account_id || c.account_id === activeAccount)
      );
      if (unreadConversations.length === 0) {
        return;
      }
      await Promise.all(
        unreadConversations.map(conv => markConversationRead(conv.id))
      );
      // Rafraîchir les conversations
      await refreshConversations(activeAccount);
    } catch (error) {
      console.error("Erreur lors du marquage de toutes les conversations comme lues:", error);
    }
  };

  const handleSettings = () => {
    setActiveTab("settings");
  };

  const handleShowContact = (contact) => {
    setSelectedContactFromChat(contact);
    setActiveTab("contacts");
  };

  const handleToggleBotMode = async (conversationId, enabled) => {
    // Mettre à jour la conversation dans la liste
    setConversations(prev => prev.map(conv => 
      conv.id === conversationId ? { ...conv, bot_enabled: enabled } : conv
    ));
  };

  // Si une conversation est sélectionnée, afficher le chat en plein écran
  if (selectedConversation) {
    return (
      <MobileChatWindow
        conversation={selectedConversation}
        onBack={handleBackToList}
        onRefresh={() => refreshConversations(activeAccount)}
        onShowContact={handleShowContact}
        onToggleBotMode={handleToggleBotMode}
      />
    );
  }

  // Rendu du contenu selon l'onglet actif
  const renderContent = () => {
    switch (activeTab) {
      case "conversations":
        return (
          <MobileConversationsList
            conversations={conversations}
            accounts={accounts}
            activeAccount={activeAccount}
            onSelectAccount={setActiveAccount}
            onSelectConversation={handleSelectConversation}
            onConnectedDevices={handleConnectedDevices}
            onImportant={handleImportant}
            onMarkAllRead={handleMarkAllRead}
            onSettings={handleSettings}
          />
        );
      
      case "contacts":
        return (
          <MobileContactsPanel
            contacts={contacts}
            activeAccount={activeAccount}
            onRefresh={loadContacts}
            initialContact={selectedContactFromChat}
          />
        );
      
      case "whatsapp":
        return (
          <MobileWhatsAppPanel
            accounts={accounts}
            activeAccount={activeAccount}
          />
        );
      
      case "gemini":
        return (
          <MobileGeminiPanel
            accounts={accounts}
            activeAccount={activeAccount}
          />
        );
      
      case "settings":
        return (
          <MobileSettings onBack={() => setActiveTab("conversations")} />
        );
      
      case "connected-devices":
        return (
          <MobileConnectedDevices
            accounts={accounts}
            activeAccount={activeAccount}
            onBack={() => setActiveTab("conversations")}
          />
        );
      
      case "team":
        return (
          <MobileTeamPanel
            onBack={() => setActiveTab("conversations")}
          />
        );
      
      default:
        return null;
    }
  };

  return (
    <div className="mobile-inbox">
      {/* Contenu principal */}
      <div className="mobile-inbox__content">
        {renderContent()}
      </div>

      {/* Navigation en bas (comme WhatsApp) */}
      <nav className="mobile-inbox__nav">
        <button
          className={`mobile-inbox__nav-btn ${activeTab === "conversations" ? "active" : ""}`}
          onClick={() => setActiveTab("conversations")}
        >
          <FiMessageSquare />
          <span>Discussions</span>
          {(() => {
            // Les conversations sont déjà filtrées par compte actif dans le backend
            const unreadCount = conversations.filter(c => c.unread_count > 0).length;
            return unreadCount > 0 ? (
              <span className="mobile-inbox__nav-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
            ) : null;
          })()}
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "contacts" ? "active" : ""}`}
          onClick={() => setActiveTab("contacts")}
        >
          <FiUsers />
          <span>Contacts</span>
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "gemini" ? "active" : ""}`}
          onClick={() => setActiveTab("gemini")}
        >
          <FiMessageCircle />
          <span>Assistant</span>
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "team" ? "active" : ""}`}
          onClick={() => setActiveTab("team")}
        >
          <FiUserCheck />
          <span>Équipe</span>
        </button>
      </nav>
    </div>
  );
}

