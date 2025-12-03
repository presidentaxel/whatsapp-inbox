import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getConversations,
  markConversationRead,
  toggleConversationFavorite,
  toggleConversationBotMode,
} from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts } from "../api/contactsApi";
import ConversationList from "../components/conversations/ConversationList";
import ChatWindow from "../components/chat/ChatWindow";
import AccountSelector from "../components/accounts/AccountSelector";
import SidebarNav from "../components/layout/SidebarNav";
import ContactsPanel from "../components/contacts/ContactsPanel";
import { useAuth } from "../context/AuthContext";
import SettingsPanel from "../components/settings/SettingsPanel";
import GeminiPanel from "../components/bot/GeminiPanel";
import WhatsAppBusinessPanel from "../components/whatsapp/WhatsAppBusinessPanel";
import { useGlobalNotifications } from "../hooks/useGlobalNotifications";
import { saveActiveAccount, getActiveAccount } from "../utils/accountStorage";


export default function InboxPage() {
  const { signOut, profile, hasPermission } = useAuth();
  const [accounts, setAccounts] = useState([]);
  const [activeAccount, setActiveAccount] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [navMode, setNavMode] = useState("chat");
  const [filter, setFilter] = useState("all");
  const [contacts, setContacts] = useState([]);
  const [contactSearch, setContactSearch] = useState("");
  const [selectedContact, setSelectedContact] = useState(null);
  const [isWindowActive, setIsWindowActive] = useState(true);
  const canViewContacts = hasPermission?.("contacts.view");
  
  useEffect(() => {
    const handleVisibility = () => setIsWindowActive(!document.hidden);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  // Écouter TOUS les nouveaux messages pour afficher des notifications
  // Fonctionne comme WhatsApp : notifications pour TOUS les messages entrants
  // Peu importe le compte, la plateforme, etc.
  useGlobalNotifications(selectedConversation?.id);


  const loadAccounts = useCallback(async () => {
    try {
      const res = await getAccounts();
      const payload = Array.isArray(res?.data)
        ? res.data
        : Array.isArray(res?.data?.data)
          ? res.data.data
          : [];

      setAccounts(payload);
      
      // Essayer de restaurer le compte sauvegardé
      const savedAccountId = getActiveAccount();
      const savedAccountExists = savedAccountId && payload.some((acc) => acc.id === savedAccountId);
      
      setActiveAccount((prev) => {
        // Si un compte est sauvegardé et existe toujours, l'utiliser
        if (savedAccountExists) {
          return savedAccountId;
        }
        // Sinon, garder le compte actuel s'il existe toujours
        if (prev && payload.some((acc) => acc.id === prev)) {
          return prev;
        }
        // Sinon, prendre le premier compte disponible
        return payload[0]?.id ?? null;
      });
    } catch (error) {
      console.error("Failed to load accounts", error);
      setAccounts([]);
      setActiveAccount(null);
    }
  }, []);

  const refreshConversations = useCallback(
    (accountId = activeAccount) => {
      if (!accountId) return;
      getConversations(accountId).then((res) => {
        setConversations(res.data);
        setSelectedConversation((prev) =>
          prev ? res.data.find((c) => c.id === prev.id) ?? null : null
        );
      });
    },
    [activeAccount]
  );

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  // Sauvegarder le compte actif quand il change
  useEffect(() => {
    if (activeAccount) {
      saveActiveAccount(activeAccount);
    }
  }, [activeAccount]);

  useEffect(() => {
    if (!activeAccount) {
      setConversations([]);
      setSelectedConversation(null);
      return;
    }
    refreshConversations(activeAccount);
  }, [activeAccount, refreshConversations]);

  useEffect(() => {
    if (navMode === "contacts" && canViewContacts) {
      getContacts().then((res) => {
        setContacts(res.data);
        setSelectedContact((prev) => prev ?? res.data[0] ?? null);
      });
    } else if (navMode === "contacts" && !canViewContacts) {
      setContacts([]);
      setSelectedContact(null);
    }
  }, [navMode, canViewContacts]);

  const filteredContacts = useMemo(() => {
    if (!contactSearch.trim()) return contacts;
    const term = contactSearch.toLowerCase();
    return contacts.filter((contact) => {
      const name =
        contact.display_name?.toLowerCase() || contact.whatsapp_number?.toLowerCase();
      return name?.includes(term);
    });
  }, [contacts, contactSearch]);

  useEffect(() => {
    if (!filteredContacts.length) {
      setSelectedContact(null);
      return;
    }
    if (!selectedContact || !filteredContacts.some((c) => c.id === selectedContact.id)) {
      setSelectedContact(filteredContacts[0]);
    }
  }, [filteredContacts, selectedContact]);

  const handleSelectConversation = (conv) => {
    setSelectedConversation(conv);
    if (conv?.unread_count) {
      markConversationRead(conv.id).then(() => refreshConversations());
    }
  };

  useEffect(() => {
    if (!activeAccount || navMode !== "chat" || !isWindowActive) {
      return;
    }
    let cancelled = false;
    let timeoutId;
    const poll = async () => {
      await refreshConversations(activeAccount);
      if (!cancelled) {
        timeoutId = setTimeout(poll, 7000);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [activeAccount, navMode, isWindowActive, refreshConversations]);

  const filteredConversations = useMemo(() => {
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

  const handleFavoriteToggle = async (conversation, nextState) => {
    await toggleConversationFavorite(conversation.id, nextState);
    refreshConversations();
  };

  const handleBotModeChange = async (conversation, enabled) => {
    if (!conversation) return;
    const res = await toggleConversationBotMode(conversation.id, enabled);
    const updated = res.data?.conversation ?? { ...conversation, bot_enabled: enabled };
    setConversations((prev) =>
      prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
    );
    setSelectedConversation((prev) =>
      prev && prev.id === updated.id ? { ...prev, ...updated } : prev
    );
  };

  const canManageAccounts = hasPermission?.("accounts.manage");
  const canManageRoles = hasPermission?.("roles.manage");
  const canManageUsers = hasPermission?.("users.manage");
  const canManageSettings = hasPermission?.("settings.manage");

  const allowedNavItems = useMemo(() => {
    const items = ["chat"];
    if (canViewContacts) {
      items.push("contacts");
    }
    items.push("whatsapp"); // Nouveau: WhatsApp Business
    if (canManageSettings) {
      items.push("assistant");
    }
    items.push("settings");
    return items;
  }, [canViewContacts, canManageSettings]);

  useEffect(() => {
    if (!allowedNavItems.includes(navMode)) {
      setNavMode("chat");
    }
  }, [allowedNavItems, navMode]);

  const canSendMessage =
    selectedConversation && selectedConversation.account_id
      ? hasPermission?.("messages.send", selectedConversation.account_id)
      : false;

  return (
    <div className="app-shell">
      <div className="workspace">
        <SidebarNav active={navMode} onSelect={setNavMode} allowedItems={allowedNavItems} onSignOut={signOut} />

        {navMode === "contacts" ? (
          canViewContacts ? (
            <div className="workspace-main contacts-mode">
              <div className="contacts-pane">
                <h3 className="panel-title">Contacts</h3>
                <div className="conversation-search">
                  <input
                    placeholder="Trouver un contact"
                    value={contactSearch}
                    onChange={(e) => setContactSearch(e.target.value)}
                  />
                </div>
                <ContactsPanel
                  contacts={filteredContacts}
                  selected={selectedContact}
                  onSelect={setSelectedContact}
                />
              </div>
            </div>
          ) : (
            <div className="workspace-main contacts-mode">
              <div className="contacts-pane">
                <h3 className="panel-title">Contacts</h3>
                <p>Vous n'avez pas la permission d'afficher les contacts.</p>
              </div>
            </div>
          )
        ) : navMode === "settings" ? (
          <div className="workspace-main settings-mode">
            <SettingsPanel
              accounts={accounts}
              onSignOut={signOut}
              currentUser={profile}
              canManageAccounts={canManageAccounts}
              canManageRoles={canManageRoles}
              canManageUsers={canManageUsers}
              onAccountsRefresh={loadAccounts}
            />
          </div>
        ) : navMode === "whatsapp" ? (
          <div className="workspace-main settings-mode">
            <WhatsAppBusinessPanel
              accountId={activeAccount}
              accounts={accounts}
            />
          </div>
        ) : navMode === "assistant" ? (
          <div className="workspace-main settings-mode">
            <GeminiPanel
              accountId={activeAccount}
              accounts={accounts}
              onAccountChange={setActiveAccount}
            />
          </div>
        ) : (
          <div className="workspace-main">
            <div className="sidebar">
              <AccountSelector
                accounts={accounts}
                value={activeAccount}
                onChange={setActiveAccount}
                label="Discussions"
              />

              <div className="conversation-filters">
                <button
                  className={filter === "all" ? "active" : ""}
                  onClick={() => setFilter("all")}
                >
                  Toutes
                </button>
                <button
                  className={filter === "unread" ? "active" : ""}
                  onClick={() => setFilter("unread")}
                >
                  Non lues
                </button>
                <button
                  className={filter === "favorites" ? "active" : ""}
                  onClick={() => setFilter("favorites")}
                >
                  Favoris
                </button>
                <button
                  className={filter === "groups" ? "active" : ""}
                  onClick={() => setFilter("groups")}
                >
                  Groupes
                </button>
              </div>
              <div className="conversation-search">
                <input placeholder="Rechercher ou démarrer une discussion" />
              </div>

              <ConversationList
                data={filteredConversations}
                selectedId={selectedConversation?.id}
                onSelect={handleSelectConversation}
              />
            </div>

            <ChatWindow
              conversation={selectedConversation}
              onFavoriteToggle={handleFavoriteToggle}
              onBotModeChange={handleBotModeChange}
              isWindowActive={isWindowActive && navMode === "chat"}
              canSend={canSendMessage}
            />
          </div>
        )}
      </div>
    </div>
  );
}