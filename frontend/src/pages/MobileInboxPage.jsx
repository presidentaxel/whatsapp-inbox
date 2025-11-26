import { useCallback, useEffect, useState } from "react";
import { FiMessageSquare, FiUsers, FiTool, FiMessageCircle } from "react-icons/fi";
import { getConversations, markConversationRead } from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts } from "../api/contactsApi";
import { clearAuthSession } from "../utils/secureStorage";
import MobileConversationsList from "../components/mobile/MobileConversationsList";
import MobileChatWindow from "../components/mobile/MobileChatWindow";
import MobileContactsPanel from "../components/mobile/MobileContactsPanel";
import MobileWhatsAppPanel from "../components/mobile/MobileWhatsAppPanel";
import MobileGeminiPanel from "../components/mobile/MobileGeminiPanel";
import "../styles/mobile-inbox.css";

export default function MobileInboxPage({ onLogout }) {
  const [activeTab, setActiveTab] = useState("conversations");
  const [accounts, setAccounts] = useState([]);
  const [activeAccount, setActiveAccount] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [contacts, setContacts] = useState([]);

  // Charger les comptes
  const loadAccounts = useCallback(async () => {
    try {
      const res = await getAccounts();
      const payload = Array.isArray(res?.data) ? res.data : res?.data?.data || [];
      setAccounts(payload);
      if (payload.length > 0 && !activeAccount) {
        setActiveAccount(payload[0].id);
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

  // Si une conversation est sélectionnée, afficher le chat en plein écran
  if (selectedConversation) {
    return (
      <MobileChatWindow
        conversation={selectedConversation}
        onBack={handleBackToList}
        onRefresh={() => refreshConversations(activeAccount)}
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
            onLogout={handleLogout}
          />
        );
      
      case "contacts":
        return (
          <MobileContactsPanel
            contacts={contacts}
            onRefresh={loadContacts}
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
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "contacts" ? "active" : ""}`}
          onClick={() => setActiveTab("contacts")}
        >
          <FiUsers />
          <span>Contacts</span>
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "whatsapp" ? "active" : ""}`}
          onClick={() => setActiveTab("whatsapp")}
        >
          <FiTool />
          <span>WhatsApp</span>
        </button>

        <button
          className={`mobile-inbox__nav-btn ${activeTab === "gemini" ? "active" : ""}`}
          onClick={() => setActiveTab("gemini")}
        >
          <FiMessageCircle />
          <span>Assistant</span>
        </button>
      </nav>
    </div>
  );
}

