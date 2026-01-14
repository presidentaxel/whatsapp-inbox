import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getConversations,
  markConversationRead,
  toggleConversationFavorite,
  toggleConversationBotMode,
  findOrCreateConversation,
} from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts } from "../api/contactsApi";
import ConversationList from "../components/conversations/ConversationList";
import ChatWindow from "../components/chat/ChatWindow";
import AccountSelector from "../components/accounts/AccountSelector";
import SidebarNav from "../components/layout/SidebarNav";
import ContactsPanel from "../components/contacts/ContactsPanel";
import AccountMediaGallery from "../components/gallery/AccountMediaGallery";
import { useAuth } from "../context/AuthContext";
import SettingsPanel from "../components/settings/SettingsPanel";
import GeminiPanel from "../components/bot/GeminiPanel";
import WhatsAppBusinessPanel from "../components/whatsapp/WhatsAppBusinessPanel";
import { useGlobalNotifications } from "../hooks/useGlobalNotifications";
import { saveActiveAccount, getActiveAccount } from "../utils/accountStorage";
import { clearConversationNotification } from "../registerSW";


export default function InboxPage() {
  const { signOut, profile, hasPermission, refreshProfile } = useAuth();
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
  const [conversationSearch, setConversationSearch] = useState("");
  const [showGallery, setShowGallery] = useState(false);
  const canViewContacts = hasPermission?.("contacts.view");
  
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
      setAccounts([]);
      setActiveAccount(null);
    }
  }, []);

  const refreshConversations = useCallback(
    async (accountId = activeAccount) => {
      if (!accountId) return;
      
      // Charger toutes les conversations avec pagination
      let allConversations = [];
      let hasMore = true;
      let cursor = null;
      const limit = 200; // Maximum autorisé par l'API
      
      while (hasMore) {
        try {
          const res = await getConversations(accountId, { limit, cursor });
          const conversations = res.data || [];
          
          if (conversations.length === 0) {
            hasMore = false;
            break;
          }
          
          allConversations = [...allConversations, ...conversations];
          
          // Si on a moins de messages que la limite, on a tout chargé
          if (conversations.length < limit) {
            hasMore = false;
          } else {
            // Utiliser le updated_at de la dernière conversation comme cursor
            const lastConversation = conversations[conversations.length - 1];
            cursor = lastConversation.updated_at;
          }
        } catch (error) {
          hasMore = false;
        }
      }
      
      setConversations(allConversations);
      setSelectedConversation((prev) =>
        prev ? allConversations.find((c) => c.id === prev.id) ?? null : null
      );
    },
    [activeAccount]
  );

  useEffect(() => {
    const handleVisibility = () => setIsWindowActive(!document.hidden);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  // Écouter les événements du Service Worker pour les notifications
  useEffect(() => {
    const handleMarkConversationRead = (event) => {
      const { conversationId } = event.detail;
      if (conversationId) {
        markConversationRead(conversationId).then(() => {
          refreshConversations();
          clearConversationNotification(conversationId);
        });
      }
    };

    const handleMarkAllRead = (event) => {
      const { conversationIds } = event.detail;
      if (conversationIds && conversationIds.length > 0) {
        Promise.all(conversationIds.map(id => markConversationRead(id)))
          .then(() => {
            refreshConversations();
            // Nettoyer toutes les conversations du stockage
            conversationIds.forEach(id => clearConversationNotification(id));
          });
      }
    };

    const handleOpenConversation = (event) => {
      const { conversationId } = event.detail;
      if (conversationId) {
        // Trouver la conversation et la sélectionner
        const conv = conversations.find(c => c.id === conversationId);
        if (conv) {
          setSelectedConversation(conv);
          if (conv?.unread_count) {
            markConversationRead(conv.id).then(() => {
              refreshConversations();
              clearConversationNotification(conv.id);
            });
          }
        }
      }
    };

    window.addEventListener('markConversationRead', handleMarkConversationRead);
    window.addEventListener('markAllConversationsRead', handleMarkAllRead);
    window.addEventListener('openConversation', handleOpenConversation);

    return () => {
      window.removeEventListener('markConversationRead', handleMarkConversationRead);
      window.removeEventListener('markAllConversationsRead', handleMarkAllRead);
      window.removeEventListener('openConversation', handleOpenConversation);
    };
  }, [conversations, refreshConversations]);

  // Écouter TOUS les nouveaux messages pour afficher des notifications
  // Fonctionne comme WhatsApp : notifications pour TOUS les messages entrants
  // Peu importe le compte, la plateforme, etc.
  useGlobalNotifications(selectedConversation?.id);

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
      markConversationRead(conv.id).then(() => {
        refreshConversations();
        // Nettoyer la notification pour cette conversation
        clearConversationNotification(conv.id);
      });
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
    // Si la galerie est affichée, ne pas filtrer les conversations
    if (showGallery) {
      return [];
    }
    
    switch (filter) {
      case "unread":
        return conversations.filter((c) => c.unread_count > 0);
      case "favorites":
        return conversations.filter((c) => c.is_favorite);
      case "gallery":
        return conversations; // Ne pas filtrer quand on affiche la galerie
      default:
        return conversations;
    }
  }, [conversations, filter, showGallery]);

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

  const canViewAccounts = hasPermission?.("accounts.view"); // Permet aux Managers de voir les comptes
  const canManageAccounts = hasPermission?.("accounts.manage"); // Seul Admin peut créer/supprimer
  const canManageRoles = hasPermission?.("roles.manage");
  const canManageUsers = hasPermission?.("users.manage");
  // Pour l'onglet Permissions : Admin a permissions.manage, DEV a permissions.view
  const canViewPermissions = hasPermission?.("permissions.view"); // DEV peut voir les permissions
  const canManagePermissions = hasPermission?.("permissions.manage"); // Admin peut gérer les permissions
  const canManageSettings = hasPermission?.("settings.manage");
  // Pour l'onglet Gemini : Admin, DEV et Manager peuvent y accéder
  // On vérifie si l'utilisateur a au moins un rôle parmi admin, dev, manager
  const canAccessGemini = canViewPermissions || canManagePermissions || canViewAccounts; // DEV, Admin, ou Manager


  const allowedNavItems = useMemo(() => {
    const items = ["chat"];
    if (canViewContacts) {
      items.push("contacts");
    }
    items.push("whatsapp"); // Nouveau: WhatsApp Business
    if (canAccessGemini) {
      items.push("assistant");
    }
    items.push("settings");
    return items;
  }, [canViewContacts, canAccessGemini]);

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
              canViewAccounts={canViewAccounts}
              canManageAccounts={canManageAccounts}
              canManageRoles={canManageRoles}
              canManageUsers={canManageUsers}
              canViewPermissions={canViewPermissions}
              canManagePermissions={canManagePermissions}
              onAccountsRefresh={loadAccounts}
              refreshProfile={refreshProfile}
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
                conversations={conversations}
              />

              <div className="conversation-filters">
                <button
                  className={filter === "all" ? "active" : ""}
                  onClick={() => {
                    setFilter("all");
                    setShowGallery(false);
                  }}
                >
                  Toutes
                </button>
                <button
                  className={filter === "unread" ? "active" : ""}
                  onClick={() => {
                    setFilter("unread");
                    setShowGallery(false);
                  }}
                >
                  Non lues
                </button>
                <button
                  className={filter === "favorites" ? "active" : ""}
                  onClick={() => {
                    setFilter("favorites");
                    setShowGallery(false);
                  }}
                >
                  Favoris
                </button>
                <button
                  className={filter === "gallery" ? "active" : ""}
                  onClick={() => {
                    setFilter("gallery");
                    setShowGallery(true);
                    setSelectedConversation(null); // Fermer la conversation si ouverte
                  }}
                >
                  Galerie
                </button>
              </div>
              {!showGallery && (
                <div className="conversation-search">
                  <input 
                    placeholder="Taper un numéro et appuyer sur Entrée (ex: +33612345678)" 
                    value={conversationSearch}
                    onChange={(e) => setConversationSearch(e.target.value)}
                    onKeyDown={async (e) => {
                      if (e.key === "Enter" && conversationSearch.trim() && activeAccount) {
                        const phoneNumber = conversationSearch.trim();
                        // Vérifier si c'est un numéro de téléphone (contient des chiffres)
                        if (/\d/.test(phoneNumber)) {
                          try {
                            const res = await findOrCreateConversation(activeAccount, phoneNumber);
                            if (res.data) {
                              setSelectedConversation(res.data);
                              setConversationSearch("");
                              refreshConversations(activeAccount);
                            }
                          } catch (error) {
                            const errorMsg = error.response?.data?.detail || error.message || "Erreur inconnue";
                            alert(`Impossible de créer la conversation: ${errorMsg}`);
                          }
                        }
                      }
                    }}
                  />
                </div>
              )}

              {showGallery ? (
                <AccountMediaGallery accountId={activeAccount} mediaType="all" />
              ) : (
                <>
                  <ConversationList
                    data={filteredConversations}
                    selectedId={selectedConversation?.id}
                    onSelect={handleSelectConversation}
                    onRefresh={() => refreshConversations(activeAccount)}
                  />
                </>
              )}
            </div>

            {!showGallery && (
              <ChatWindow
                conversation={selectedConversation}
                onFavoriteToggle={handleFavoriteToggle}
                onBotModeChange={handleBotModeChange}
                isWindowActive={isWindowActive && navMode === "chat"}
                canSend={canSendMessage}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}