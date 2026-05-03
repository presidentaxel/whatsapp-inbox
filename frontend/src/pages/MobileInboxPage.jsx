import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FiMessageSquare, FiUsers, FiTool, FiMessageCircle, FiSettings, FiUserCheck } from "react-icons/fi";
import { getConversations, markConversationRead } from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts, getMetaBlockedWaIdsBatch, metaBlockContact, metaUnblockContact } from "../api/contactsApi";
import { supabaseClient } from "../api/supabaseClient";
import { clearAuthSession } from "../utils/secureStorage";
import { saveActiveAccount, getActiveAccount } from "../utils/accountStorage";
import {
  excludePlaygroundSandboxConversations,
  isPlaygroundSandboxConversation,
} from "../utils/playgroundSandbox";
import MobileConversationsList from "../components/mobile/MobileConversationsList";
import MobileChatWindow from "../components/mobile/MobileChatWindow";
import MobileContactsPanel from "../components/mobile/MobileContactsPanel";
import MobileWhatsAppPanel from "../components/mobile/MobileWhatsAppPanel";
import MobileGeminiPanel from "../components/mobile/MobileGeminiPanel";
import MobileNotificationSettings from "../components/mobile/MobileNotificationSettings";
import MobileSettings from "../components/mobile/MobileSettings";
import MobileConnectedDevices from "../components/mobile/MobileConnectedDevices";
import MobileTeamPanel from "../components/mobile/MobileTeamPanel";
import MetaBlockAccountModal from "../components/contacts/MetaBlockAccountModal";
import { useAuth } from "../context/AuthContext";
import { useGlobalNotifications } from "../hooks/useGlobalNotifications";
import "../styles/mobile-inbox.css";

const SIDEBAR_CHAT_SYNC_DEBOUNCE_MS = 220;

export default function MobileInboxPage({ onLogout }) {
  const { hasPermission, profile } = useAuth();
  const [activeTab, setActiveTab] = useState("conversations");
  const [accounts, setAccounts] = useState([]);
  const [activeAccount, setActiveAccount] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [conversationCursor, setConversationCursor] = useState(null);
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [selectedContactFromChat, setSelectedContactFromChat] = useState(null);
  const [contactsListQ, setContactsListQ] = useState("");
  const [blockedByAccount, setBlockedByAccount] = useState({});
  const [metaBlockBusyId, setMetaBlockBusyId] = useState(null);
  const [metaBlockModal, setMetaBlockModal] = useState(null);

  const selectedConversationIdRef = useRef(null);
  const conversationRealtimeDebounceTimerRef = useRef(null);
  const inboundFullRefreshDebounceTimerRef = useRef(null);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversation?.id ?? null;
  }, [selectedConversation?.id]);

  useEffect(() => {
    return () => {
      if (inboundFullRefreshDebounceTimerRef.current) {
        clearTimeout(inboundFullRefreshDebounceTimerRef.current);
      }
    };
  }, []);

  const normalizeWaDigits = useCallback((phone) => String(phone || "").replace(/\D/g, ""), []);

  const loadAllBlockedWaForContacts = useCallback(async () => {
    if (!accounts.length) {
      setBlockedByAccount({});
      return;
    }
    const targets = accounts.filter((a) => hasPermission?.("messages.view", a.id));
    if (!targets.length) {
      setBlockedByAccount({});
      return;
    }
    try {
      const res = await getMetaBlockedWaIdsBatch(targets.map((a) => a.id));
      const byAccount = res.data?.by_account ?? {};
      setBlockedByAccount(
        Object.fromEntries(
          targets.map((a) => [
            a.id,
            (byAccount[a.id] ?? []).map((x) => normalizeWaDigits(x)),
          ])
        )
      );
    } catch (e) {
      console.error("meta block list:", e);
      setBlockedByAccount({});
    }
  }, [accounts, hasPermission, normalizeWaDigits]);

  const mergedBlockedWaIds = useMemo(() => {
    const s = new Set();
    Object.values(blockedByAccount).forEach((arr) => {
      (arr || []).forEach((id) => s.add(id));
    });
    return s;
  }, [blockedByAccount]);

  const suppressInboundForConversationRef = useRef(() => false);
  useEffect(() => {
    suppressInboundForConversationRef.current = (conversation) => {
      if (!conversation?.account_id) return false;
      const wa = normalizeWaDigits(
        conversation.contacts?.whatsapp_number ?? conversation.client_number ?? ""
      );
      if (!wa) return false;
      return (blockedByAccount[conversation.account_id] || []).includes(wa);
    };
  }, [blockedByAccount, normalizeWaDigits]);

  const blockedByAccountRef = useRef({});
  useEffect(() => {
    blockedByAccountRef.current = blockedByAccount;
  }, [blockedByAccount]);

  const conversationInternallyBlocked = useMemo(() => {
    const c = selectedConversation;
    if (!c?.account_id) return false;
    const wa = normalizeWaDigits(c.contacts?.whatsapp_number ?? c.client_number ?? "");
    if (!wa) return false;
    return (blockedByAccount[c.account_id] || []).includes(wa);
  }, [selectedConversation, blockedByAccount, normalizeWaDigits]);

  const accountWriteOk = useCallback(
    (accountId) => {
      if (!hasPermission?.("messages.send", accountId)) return false;
      const level = profile?.permissions?.account_access_levels?.[accountId];
      return level !== "aucun" && level !== "lecture";
    },
    [hasPermission, profile]
  );

  const canModerateWaAny = useMemo(
    () => accounts.some((a) => accountWriteOk(a.id)),
    [accounts, accountWriteOk]
  );

  const metaBlockModalAccounts = useMemo(() => {
    if (!metaBlockModal?.contact) return [];
    const w = normalizeWaDigits(metaBlockModal.contact.whatsapp_number);
    if (metaBlockModal.action === "block") {
      return accounts.filter((a) => accountWriteOk(a.id));
    }
    return accounts.filter(
      (a) => accountWriteOk(a.id) && (blockedByAccount[a.id] || []).includes(w)
    );
  }, [metaBlockModal, accounts, accountWriteOk, blockedByAccount, normalizeWaDigits]);

  const handleMetaBlockModalConfirm = useCallback(
    async (accountId) => {
      const contact = metaBlockModal?.contact;
      const action = metaBlockModal?.action;
      if (!contact?.id || !action) return;
      setMetaBlockBusyId(contact.id);
      try {
        if (action === "block") {
          await metaBlockContact(contact.id, accountId);
        } else {
          await metaUnblockContact(contact.id, accountId);
        }
        await loadAllBlockedWaForContacts();
        setMetaBlockModal(null);
      } catch (error) {
        const detail = error.response?.data?.detail;
        alert(
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => d.msg || d).join(", ")
              : "Erreur blocage WhatsApp"
        );
      } finally {
        setMetaBlockBusyId(null);
      }
    },
    [metaBlockModal, loadAllBlockedWaForContacts]
  );

  // Charger les comptes
  const loadAccounts = useCallback(async () => {
    try {
      const { data: { session }, error: sessionError } = await supabaseClient.auth.getSession();
      if (sessionError || !session?.access_token) return;

      const res = await getAccounts();
      const payload = Array.isArray(res?.data) ? res.data : res?.data?.data || [];
      setAccounts(payload);
      
      const savedAccountId = getActiveAccount();
      const savedAccountExists = savedAccountId && payload.some((acc) => acc.id === savedAccountId);
      
      if (payload.length > 0 && !activeAccount) {
        setActiveAccount(savedAccountExists ? savedAccountId : payload[0].id);
      }
    } catch {
      // Silent fallback
    }
  }, [activeAccount]);

  useEffect(() => {
    setSelectedConversation((prev) =>
      prev && isPlaygroundSandboxConversation(prev) ? null : prev
    );
  }, [activeAccount]);

  const CONVERSATIONS_PAGE_SIZE = 50;

  const refreshConversations = useCallback(async (accountId) => {
    if (!accountId) return;
    try {
      const res = await getConversations(accountId, { limit: CONVERSATIONS_PAGE_SIZE });
      const batch = excludePlaygroundSandboxConversations(res.data || []);
      setConversations(batch);
      if (batch.length >= CONVERSATIONS_PAGE_SIZE) {
        setConversationCursor(batch[batch.length - 1].updated_at);
        setHasMoreConversations(true);
      } else {
        setConversationCursor(null);
        setHasMoreConversations(false);
      }
    } catch {
      setConversations([]);
      setHasMoreConversations(false);
    }
  }, []);

  const loadMoreConversations = useCallback(async () => {
    if (!activeAccount || !hasMoreConversations || loadingMoreConversations || !conversationCursor) return;
    setLoadingMoreConversations(true);
    try {
      const res = await getConversations(activeAccount, {
        limit: CONVERSATIONS_PAGE_SIZE,
        cursor: conversationCursor,
      });
      const batch = excludePlaygroundSandboxConversations(res.data || []);
      if (batch.length === 0) {
        setHasMoreConversations(false);
      } else {
        setConversations((prev) => [...prev, ...batch]);
        if (batch.length >= CONVERSATIONS_PAGE_SIZE) {
          setConversationCursor(batch[batch.length - 1].updated_at);
        } else {
          setHasMoreConversations(false);
          setConversationCursor(null);
        }
      }
    } catch {
      // Silent
    } finally {
      setLoadingMoreConversations(false);
    }
  }, [activeAccount, hasMoreConversations, loadingMoreConversations, conversationCursor]);

  // Charger les contacts (liste alignée avec la recherche serveur)
  const loadContacts = useCallback(async () => {
    try {
      const trimmed = contactsListQ.trim();
      const params = trimmed ? { q: trimmed, limit: 8000 } : { limit: 15000 };
      const res = await getContacts(params);
      setContacts(res.data?.items || res.data || []);
    } catch (error) {
      console.error("Erreur chargement contacts:", error);
    }
  }, [contactsListQ]);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    if (activeTab === "contacts") {
      loadContacts();
    }
  }, [activeTab, contactsListQ, loadContacts]);

  // Sauvegarder le compte actif quand il change
  useEffect(() => {
    if (activeAccount) {
      saveActiveAccount(activeAccount);
    }
  }, [activeAccount]);

  // Chargé au démarrage avec les comptes : le chat a besoin de l’état bloqué sans passer par l’onglet contacts.
  useEffect(() => {
    loadAllBlockedWaForContacts();
  }, [loadAllBlockedWaForContacts]);

  useEffect(() => {
    if (activeAccount) {
      refreshConversations(activeAccount);
      const interval = setInterval(() => {
        refreshConversations(activeAccount);
      }, 45000);
      return () => clearInterval(interval);
    }
  }, [activeAccount, refreshConversations]);

  const onInboundMessage = useCallback(
    (newMessage) => {
      if (!activeAccount) return;
      const convId = newMessage?.conversation_id;
      const isOpenChat = convId && convId === selectedConversationIdRef.current;
      const run = () => refreshConversations(activeAccount);
      if (!isOpenChat) {
        run();
        return;
      }
      if (inboundFullRefreshDebounceTimerRef.current) {
        clearTimeout(inboundFullRefreshDebounceTimerRef.current);
      }
      inboundFullRefreshDebounceTimerRef.current = setTimeout(() => {
        inboundFullRefreshDebounceTimerRef.current = null;
        run();
      }, SIDEBAR_CHAT_SYNC_DEBOUNCE_MS);
    },
    [activeAccount, refreshConversations]
  );

  useGlobalNotifications(selectedConversation?.id, onInboundMessage, suppressInboundForConversationRef);

  // Realtime: refresh conversation list instantly when any conversation changes
  useEffect(() => {
    if (!activeAccount) return;
    const channel = supabaseClient
      .channel(`conversations:${activeAccount}`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "conversations",
          filter: `account_id=eq.${activeAccount}`,
        },
        (payload) => {
          const updated = payload.new;
          if (isPlaygroundSandboxConversation(updated)) {
            setConversations((prev) => prev.filter((c) => c.id !== updated.id));
            setSelectedConversation((prev) =>
              prev?.id === updated.id ? null : prev
            );
            return;
          }
          const waUpd = normalizeWaDigits(updated.client_number ?? "");
          if (
            updated.account_id &&
            waUpd &&
            (blockedByAccountRef.current[updated.account_id] || []).includes(waUpd)
          ) {
            return;
          }
          const applyConversationUpdate = () => {
            setConversations((prev) => {
              const idx = prev.findIndex((c) => c.id === updated.id);
              if (idx === -1) return prev;
              const next = [...prev];
              next[idx] = { ...next[idx], ...updated };
              return next.sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1));
            });
            setSelectedConversation((prev) =>
              prev?.id === updated.id ? { ...prev, ...updated } : prev
            );
          };
          const isOpenChat = selectedConversationIdRef.current === updated.id;
          if (!isOpenChat) {
            applyConversationUpdate();
            return;
          }
          if (conversationRealtimeDebounceTimerRef.current) {
            clearTimeout(conversationRealtimeDebounceTimerRef.current);
          }
          conversationRealtimeDebounceTimerRef.current = setTimeout(() => {
            conversationRealtimeDebounceTimerRef.current = null;
            applyConversationUpdate();
          }, SIDEBAR_CHAT_SYNC_DEBOUNCE_MS);
        }
      )
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "conversations",
          filter: `account_id=eq.${activeAccount}`,
        },
        (payload) => {
          const newConv = payload.new;
          if (isPlaygroundSandboxConversation(newConv)) return;
          setConversations((prev) => {
            if (prev.some((c) => c.id === newConv.id)) return prev;
            return [newConv, ...prev].sort(
              (a, b) => (b.updated_at > a.updated_at ? 1 : -1)
            );
          });
        }
      )
      .subscribe();
    return () => {
      if (conversationRealtimeDebounceTimerRef.current) {
        clearTimeout(conversationRealtimeDebounceTimerRef.current);
        conversationRealtimeDebounceTimerRef.current = null;
      }
      supabaseClient.removeChannel(channel);
    };
  }, [activeAccount, normalizeWaDigits]);

  const optimisticallyMarkRead = useCallback((conversationIds) => {
    const ids = new Set(Array.isArray(conversationIds) ? conversationIds : [conversationIds]);
    setConversations((prev) =>
      prev.map((c) => (ids.has(c.id) && c.unread_count > 0 ? { ...c, unread_count: 0 } : c))
    );
  }, []);

  const handleSelectConversation = async (conv) => {
    setSelectedConversation(conv);
    if (conv?.unread_count) {
      optimisticallyMarkRead(conv.id);
      markConversationRead(conv.id).catch(() => refreshConversations(activeAccount));
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
      const unreadConversations = conversations.filter(
        (c) => c.unread_count > 0 && (!c.account_id || c.account_id === activeAccount)
      );
      if (unreadConversations.length === 0) return;
      const ids = unreadConversations.map((c) => c.id);
      optimisticallyMarkRead(ids);
      Promise.all(ids.map((id) => markConversationRead(id))).catch(() =>
        refreshConversations(activeAccount)
      );
    } catch (error) {
      console.error("Erreur lors du marquage de toutes les conversations comme lues:", error);
      refreshConversations(activeAccount);
    }
  };

  const handleSettings = () => {
    setActiveTab("settings");
  };

  const handleShowContact = (contact) => {
    setSelectedContactFromChat(contact);
    setActiveTab("contacts");
  };

  const handleBotSettingsUpdated = (updated) => {
    if (!updated?.id) return;
    setConversations((prev) =>
      prev.map((c) => (c.id === updated.id ? { ...c, ...updated } : c))
    );
    setSelectedConversation((prev) =>
      prev?.id === updated.id ? { ...prev, ...updated } : prev
    );
  };

  // Si une conversation est sélectionnée, afficher le chat en plein écran
  if (selectedConversation) {
    return (
      <MobileChatWindow
        conversation={selectedConversation}
        onBack={handleBackToList}
        onRefresh={() => refreshConversations(activeAccount)}
        onShowContact={handleShowContact}
        onBotSettingsUpdated={handleBotSettingsUpdated}
        conversationInternallyBlocked={conversationInternallyBlocked}
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
            hasMore={hasMoreConversations}
            loadingMore={loadingMoreConversations}
            onLoadMore={loadMoreConversations}
          />
        );
      
      case "contacts":
        return (
          <>
            <MobileContactsPanel
              contacts={contacts}
              activeAccount={activeAccount}
              onRefresh={loadContacts}
              initialContact={selectedContactFromChat}
              metaBlockedNormalizedIds={mergedBlockedWaIds}
              canModerateWaAny={canModerateWaAny}
              metaBlockBusyId={metaBlockBusyId}
              onMetaBlockOpen={(contact, action) => setMetaBlockModal({ contact, action })}
              onContactsSearchQuery={setContactsListQ}
            />
            <MetaBlockAccountModal
              open={Boolean(metaBlockModal)}
              onClose={() => !metaBlockBusyId && setMetaBlockModal(null)}
              action={metaBlockModal?.action}
              accounts={metaBlockModalAccounts}
              busy={Boolean(metaBlockBusyId && metaBlockModal?.contact?.id === metaBlockBusyId)}
              onConfirm={handleMetaBlockModalConfirm}
            />
          </>
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

