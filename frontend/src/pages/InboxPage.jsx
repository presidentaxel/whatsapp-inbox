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
import { 
  getBroadcastGroups, 
  createBroadcastGroup, 
  updateBroadcastGroup, 
  deleteBroadcastGroup,
  addRecipientToGroup
} from "../api/broadcastApi";
import BroadcastGroupsList from "../components/broadcast/BroadcastGroupsList";
import BroadcastGroupEditor from "../components/broadcast/BroadcastGroupEditor";
import BroadcastGroupChat from "../components/broadcast/BroadcastGroupChat";


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
  const [selectedContacts, setSelectedContacts] = useState(new Set());
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [isWindowActive, setIsWindowActive] = useState(true);
  const [conversationSearch, setConversationSearch] = useState("");
  const [showGallery, setShowGallery] = useState(false);
  const [broadcastGroups, setBroadcastGroups] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [showGroupEditor, setShowGroupEditor] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);
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

  // Update optimiste : mettre à jour unread_count localement sans refetch complet
  const optimisticallyMarkRead = useCallback((conversationIds) => {
    const ids = new Set(Array.isArray(conversationIds) ? conversationIds : [conversationIds]);
    setConversations((prev) =>
      prev.map((c) => (ids.has(c.id) && c.unread_count > 0 ? { ...c, unread_count: 0 } : c))
    );
  }, []);

  // Écouter les événements du Service Worker pour les notifications
  useEffect(() => {
    const handleMarkConversationRead = (event) => {
      const { conversationId } = event.detail;
      if (conversationId) {
        optimisticallyMarkRead(conversationId);
        clearConversationNotification(conversationId);
        markConversationRead(conversationId).catch(() => refreshConversations());
      }
    };

    const handleMarkAllRead = (event) => {
      const { conversationIds } = event.detail;
      if (conversationIds && conversationIds.length > 0) {
        optimisticallyMarkRead(conversationIds);
        conversationIds.forEach((id) => clearConversationNotification(id));
        Promise.all(conversationIds.map((id) => markConversationRead(id))).catch(() =>
          refreshConversations()
        );
      }
    };

    const handleOpenConversation = (event) => {
      const { conversationId } = event.detail;
      if (conversationId) {
        const conv = conversations.find((c) => c.id === conversationId);
        if (conv) {
          setSelectedConversation(conv);
          if (conv?.unread_count) {
            optimisticallyMarkRead(conv.id);
            clearConversationNotification(conv.id);
            markConversationRead(conv.id).catch(() => refreshConversations());
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
  }, [conversations, refreshConversations, optimisticallyMarkRead]);

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

  // Charger les groupes de diffusion
  const loadBroadcastGroups = useCallback(async () => {
    if (!activeAccount) {
      setBroadcastGroups([]);
      return;
    }
    try {
      const res = await getBroadcastGroups(activeAccount);
      setBroadcastGroups(res.data || []);
    } catch (error) {
      console.error("Error loading broadcast groups:", error);
      setBroadcastGroups([]);
    }
  }, [activeAccount]);

  useEffect(() => {
    if (filter === "groups") {
      loadBroadcastGroups();
    }
  }, [filter, activeAccount, loadBroadcastGroups]);

  const handleCreateGroup = () => {
    setEditingGroup(null);
    setShowGroupEditor(true);
  };

  const handleEditGroup = (group) => {
    setEditingGroup(group);
    setShowGroupEditor(true);
  };

  const handleDeleteGroup = async (groupId) => {
    try {
      await deleteBroadcastGroup(groupId);
      await loadBroadcastGroups();
      if (selectedGroup?.id === groupId) {
        setSelectedGroup(null);
      }
    } catch (error) {
      console.error("Error deleting group:", error);
      alert(error.response?.data?.detail || "Erreur lors de la suppression");
    }
  };

  const handleGroupSaved = async (newGroup) => {
    await loadBroadcastGroups();
    setShowGroupEditor(false);
    setEditingGroup(null);
    if (newGroup) {
      setSelectedGroup(newGroup);
    }
  };

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

  // Ne pas réinitialiser la sélection lors de la recherche si on est en mode multi-sélection
  useEffect(() => {
    if (multiSelectMode) return; // Ne pas réinitialiser en mode multi-sélection
    if (!filteredContacts.length) {
      setSelectedContact(null);
      return;
    }
    if (!selectedContact || !filteredContacts.some((c) => c.id === selectedContact.id)) {
      setSelectedContact(filteredContacts[0]);
    }
  }, [filteredContacts, selectedContact, multiSelectMode]);

  const handleToggleContactSelect = useCallback((contactId) => {
    setSelectedContacts((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(contactId)) {
        newSet.delete(contactId);
      } else {
        newSet.add(contactId);
      }
      return newSet;
    });
  }, []);

  const handleCreateCampaignFromContacts = useCallback(async () => {
    if (!activeAccount) {
      alert("Aucun compte WhatsApp actif. Veuillez sélectionner un compte.");
      return;
    }

    if (selectedContacts.size === 0) {
      alert("Veuillez sélectionner au moins un contact.");
      return;
    }

    try {
      // Créer un groupe de broadcast
      const groupName = `Campagne - ${new Date().toLocaleDateString('fr-FR')}`;
      const res = await createBroadcastGroup({
        account_id: activeAccount,
        name: groupName,
        description: `Campagne créée depuis ${selectedContacts.size} contact(s) sélectionné(s)`
      });

      const newGroup = res.data;

      // Ajouter tous les contacts sélectionnés au groupe
      const selectedContactsArray = Array.from(selectedContacts);
      const contactObjects = selectedContactsArray
        .map(id => contacts.find(c => c.id === id))
        .filter(Boolean);

      for (const contact of contactObjects) {
        try {
          await addRecipientToGroup(newGroup.id, {
            phone_number: contact.whatsapp_number,
            contact_id: contact.id,
            display_name: contact.display_name,
          });
        } catch (error) {
          console.error(`Error adding contact ${contact.id} to group:`, error);
        }
      }

      // Réinitialiser la sélection
      setSelectedContacts(new Set());
      setMultiSelectMode(false);

      // Afficher le groupe créé
      await loadBroadcastGroups();
      setSelectedGroup(newGroup);
      setFilter("groups");

      alert(`Campagne créée avec ${contactObjects.length} contact(s) !`);
    } catch (error) {
      console.error("Error creating campaign:", error);
      alert(error.response?.data?.detail || "Erreur lors de la création de la campagne");
    }
  }, [activeAccount, selectedContacts, contacts, loadBroadcastGroups]);

  const handleSelectConversation = (conv) => {
    setSelectedConversation(conv);
    if (conv?.unread_count) {
      optimisticallyMarkRead(conv.id);
      clearConversationNotification(conv.id);
      markConversationRead(conv.id).catch(() => refreshConversations());
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
        timeoutId = setTimeout(poll, 15000);
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
      case "groups":
        // Les groupes seront gérés séparément
        return [];
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
                <div className="contacts-header">
                  <h3 className="panel-title">Contacts</h3>
                  <div className="contacts-actions">
                    {!multiSelectMode ? (
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => setMultiSelectMode(true)}
                      >
                        Sélection multiple
                      </button>
                    ) : (
                      <>
                        <span className="selection-count">
                          {selectedContacts.size} sélectionné{selectedContacts.size > 1 ? 's' : ''}
                        </span>
                        {selectedContacts.size > 0 && activeAccount && (
                          <button
                            className="btn-primary btn-sm"
                            onClick={handleCreateCampaignFromContacts}
                          >
                            Créer une campagne
                          </button>
                        )}
                        <button
                          className="btn-secondary btn-sm"
                          onClick={() => {
                            setMultiSelectMode(false);
                            setSelectedContacts(new Set());
                          }}
                        >
                          Annuler
                        </button>
                      </>
                    )}
                  </div>
                </div>
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
                  selectedContacts={selectedContacts}
                  onToggleSelect={handleToggleContactSelect}
                  multiSelect={multiSelectMode}
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
                  className={filter === "groups" ? "active" : ""}
                  onClick={() => {
                    setFilter("groups");
                    setShowGallery(false);
                  }}
                >
                  Groupes
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
                    placeholder="Taper un numéro et appuyer sur Entrée..." 
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
              ) : filter === "groups" ? (
                <BroadcastGroupsList
                  groups={broadcastGroups}
                  selectedGroupId={selectedGroup?.id}
                  onSelectGroup={setSelectedGroup}
                  onCreateGroup={handleCreateGroup}
                  onEditGroup={handleEditGroup}
                  onDeleteGroup={handleDeleteGroup}
                />
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

            {!showGallery && filter !== "groups" && (
              <ChatWindow
                conversation={selectedConversation}
                onFavoriteToggle={handleFavoriteToggle}
                onBotModeChange={handleBotModeChange}
                onMarkRead={optimisticallyMarkRead}
                isWindowActive={isWindowActive && navMode === "chat"}
                canSend={canSendMessage}
              />
            )}
            {filter === "groups" && (
              <BroadcastGroupChat
                group={selectedGroup}
                accountId={activeAccount}
                onClose={() => setSelectedGroup(null)}
              />
            )}
          </div>
        )}
      </div>

      {/* Modal d'édition de groupe */}
      {showGroupEditor && (
        <div className="modal-overlay" onClick={() => setShowGroupEditor(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <BroadcastGroupEditor
              group={editingGroup}
              accountId={activeAccount}
              onClose={() => {
                setShowGroupEditor(false);
                setEditingGroup(null);
              }}
              onSave={handleGroupSaved}
            />
          </div>
        </div>
      )}
    </div>
  );
}