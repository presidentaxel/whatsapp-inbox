import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getConversations,
  markConversationRead,
  toggleConversationFavorite,
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
  const canViewContacts = hasPermission?.("contacts.view");

  const loadAccounts = useCallback(() => {
    getAccounts().then((res) => {
      setAccounts(res.data);
      setActiveAccount((prev) => {
        if (prev && res.data.some((acc) => acc.id === prev)) {
          return prev;
        }
        return res.data[0]?.id ?? null;
      });
    });
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
    if (!activeAccount || navMode !== "chat") {
      return;
    }
    const interval = setInterval(() => refreshConversations(activeAccount), 5000);
    return () => clearInterval(interval);
  }, [activeAccount, navMode, refreshConversations]);

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

  const allowedNavItems = useMemo(() => {
    const items = ["chat"];
    if (canViewContacts) {
      items.push("contacts");
    }
    items.push("settings");
    return items;
  }, [canViewContacts]);

  useEffect(() => {
    if (!allowedNavItems.includes(navMode)) {
      setNavMode("chat");
    }
  }, [allowedNavItems, navMode]);

  const canSendMessage =
    selectedConversation && selectedConversation.account_id
      ? hasPermission?.("messages.send", selectedConversation.account_id)
      : false;

  const canManageAccounts = hasPermission?.("accounts.manage");
  const canManageRoles = hasPermission?.("roles.manage");
  const canManageUsers = hasPermission?.("users.manage");

  return (
    <div className="app-shell">
      <div className="workspace">
        <SidebarNav active={navMode} onSelect={setNavMode} allowedItems={allowedNavItems} />

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
        ) : (
          <div className="workspace-main">
            <div className="sidebar">
              <AccountSelector
                accounts={accounts}
                value={activeAccount}
                onChange={setActiveAccount}
                label="Discussions"
              />
              <button className="logout-btn" onClick={signOut}>
                Déconnexion
              </button>

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
              canSend={canSendMessage}
            />
          </div>
        )}
      </div>
    </div>
  );
}