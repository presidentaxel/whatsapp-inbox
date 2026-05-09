import {
  lazy,
  Suspense,
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { FiSearch } from "react-icons/fi";
import { useNavigate, useLocation } from "react-router-dom";
import { INBOX_PATH_BY_MODE, inboxPathToMode } from "../routes/inboxRoutes";
import {
  getConversations,
  markConversationRead,
  toggleConversationFavorite,
  toggleConversationBotMode,
  setConversationPlaygroundFlow,
  findOrCreateConversation,
} from "../api/conversationsApi";
import { getAccounts } from "../api/accountsApi";
import { getContacts, getMetaBlockedWaIdsBatch, metaBlockContact, metaUnblockContact } from "../api/contactsApi";
import ConversationList from "../components/conversations/ConversationList";
import ChatWindow from "../components/chat/ChatWindow";
import AccountSelector from "../components/accounts/AccountSelector";
import MetaBlockAccountModal from "../components/contacts/MetaBlockAccountModal";
import SidebarNav from "../components/layout/SidebarNav";
import { useAuth } from "../context/AuthContext";
import { useGlobalNotifications } from "../hooks/useGlobalNotifications";
import { saveActiveAccount, getActiveAccount } from "../utils/accountStorage";
import { clearConversationNotification } from "../registerSW";
import { platformAlert } from "../platform/platformDialogs";
import { supabaseClient } from "../api/supabaseClient";
import { filterContactsBySearch } from "../utils/contactSearch";
import {
  excludePlaygroundSandboxConversations,
  isPlaygroundSandboxConversation,
} from "../utils/playgroundSandbox";
import {
  getBroadcastGroups,
  createBroadcastGroup,
  deleteBroadcastGroup,
  addRecipientToGroup,
} from "../api/broadcastApi";

/** Délai avant de rafraîchir la ligne de conversation dans la sidebar quand ce chat est ouvert (sync avec le fil realtime des messages). */
const SIDEBAR_CHAT_SYNC_DEBOUNCE_MS = 220;

const inboundPreviewFromMessage = (msg) => {
  const explicit = (msg?.content_text || "").trim();
  if (explicit) return explicit;
  const t = (msg?.message_type || "").toLowerCase();
  if (t === "image") return "Photo";
  if (t === "video") return "Video";
  if (t === "audio") return "Audio";
  if (t === "document") return "Document";
  if (t === "sticker") return "Sticker";
  if (t === "location") return "Localisation";
  if (t === "contacts") return "Contact";
  if (t === "reaction") return "Reaction";
  return "Nouveau message";
};

// Lazy-loaded heavy panels (code-split to reduce initial bundle)
const ContactsPanel = lazy(() => import("../components/contacts/ContactsPanel"));
const AccountMediaGallery = lazy(() => import("../components/gallery/AccountMediaGallery"));
const SettingsPanel = lazy(() => import("../components/settings/SettingsPanel"));
const AssistantPanel = lazy(() => import("../components/assistant/AssistantPanel"));
const WhatsAppBusinessPanel = lazy(() => import("../components/whatsapp/WhatsAppBusinessPanel"));
const AxeliaChat = lazy(() => import("../components/axelia/AxeliaChat"));
const AgentStudioPage = lazy(() => import("../components/agentStudio/AgentStudioPage"));
const BroadcastGroupsList = lazy(() => import("../components/broadcast/BroadcastGroupsList"));
const BroadcastGroupEditor = lazy(() => import("../components/broadcast/BroadcastGroupEditor"));
const BroadcastGroupChat = lazy(() => import("../components/broadcast/BroadcastGroupChat"));


export default function InboxPage() {
  const { signOut, profile, hasPermission, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [accounts, setAccounts] = useState([]);
  const [activeAccount, setActiveAccount] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [hasMoreConversations, setHasMoreConversations] = useState(false);
  const [conversationCursor, setConversationCursor] = useState(null);
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(null);

  const navMode = useMemo(() => {
    const mode = inboxPathToMode(location.pathname);
    return mode ?? "chat";
  }, [location.pathname]);

  const handleNavSelect = useCallback(
    (id) => {
      const path = INBOX_PATH_BY_MODE[id];
      if (path) navigate(path);
    },
    [navigate]
  );
  const [filter, setFilter] = useState("all");
  const [contacts, setContacts] = useState([]);
  const [contactSearch, setContactSearch] = useState("");
  const [debouncedContactSearch, setDebouncedContactSearch] = useState("");
  const [selectedContact, setSelectedContact] = useState(null);
  const [selectedContacts, setSelectedContacts] = useState(new Set());
  const [multiSelectMode, setMultiSelectMode] = useState(false);
  const [isWindowActive, setIsWindowActive] = useState(true);
  const [blockedByAccount, setBlockedByAccount] = useState({});
  const [metaBlockBusyId, setMetaBlockBusyId] = useState(null);
  const [metaBlockModal, setMetaBlockModal] = useState(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [showGallery, setShowGallery] = useState(false);
  const [broadcastGroups, setBroadcastGroups] = useState([]);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [showGroupEditor, setShowGroupEditor] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);
  const canViewContacts = hasPermission?.("contacts.view");

  const normalizeWaDigits = useCallback((phone) => String(phone || "").replace(/\D/g, ""), []);

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
    } catch (error) {
      console.error("meta block list:", error);
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
        await platformAlert(
          typeof detail === "string"
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => d.msg || d).join(", ")
              : "Erreur lors du blocage / déblocage WhatsApp"
        );
      } finally {
        setMetaBlockBusyId(null);
      }
    },
    [metaBlockModal, loadAllBlockedWaForContacts]
  );

  const selectedConversationIdRef = useRef(null);
  const conversationRealtimeDebounceTimerRef = useRef(null);
  const inboundDeltaDebounceTimerRef = useRef(null);

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversation?.id ?? null;
  }, [selectedConversation?.id]);

  useEffect(() => {
    return () => {
      if (inboundDeltaDebounceTimerRef.current) {
        clearTimeout(inboundDeltaDebounceTimerRef.current);
      }
    };
  }, []);
  
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

  const CONVERSATIONS_PAGE_SIZE = 50;

  // Ref so delta refresh can read conversations without being in the dep array
  const conversationsForDeltaRef = useRef(conversations);
  conversationsForDeltaRef.current = conversations;

  const refreshConversations = useCallback(
    async (accountId = activeAccount, { delta = false } = {}) => {
      if (!accountId) return;

      if (delta) {
        const currentConversations = conversationsForDeltaRef.current;
        const newest = currentConversations.length > 0
          ? currentConversations.reduce((max, c) => (c.updated_at > max ? c.updated_at : max), currentConversations[0].updated_at)
          : null;

        if (newest) {
          try {
            const res = await getConversations(accountId, { limit: 200, updated_since: newest });
            const updated = excludePlaygroundSandboxConversations(res.data || []);
            if (updated.length > 0) {
              startTransition(() => {
                setConversations((prev) => {
                  const map = new Map(
                    excludePlaygroundSandboxConversations(prev).map((c) => [c.id, c]),
                  );
                  updated.forEach((c) => map.set(c.id, c));
                  return Array.from(map.values()).sort((a, b) =>
                    b.updated_at > a.updated_at ? 1 : -1,
                  );
                });
                setSelectedConversation((prev) => {
                  if (!prev) return null;
                  if (isPlaygroundSandboxConversation(prev)) return null;
                  return updated.find((c) => c.id === prev.id) ?? prev;
                });
              });
            }
          } catch {
            // Fallback silencieux
          }
          return;
        }
      }
      
      try {
        const res = await getConversations(accountId, { limit: CONVERSATIONS_PAGE_SIZE });
        const batch = excludePlaygroundSandboxConversations(res.data || []);
        setConversations(batch);
        if (batch.length >= CONVERSATIONS_PAGE_SIZE) {
          const last = batch[batch.length - 1];
          setConversationCursor(last.updated_at);
          setHasMoreConversations(true);
        } else {
          setConversationCursor(null);
          setHasMoreConversations(false);
        }
        // Garder la sélection si la conv n’est pas dans les N premiers résultats
        // (ex. find-or-create sur un numéro peu récent → sinon le chat se ferme au refresh).
        setSelectedConversation((prev) => {
          if (!prev) return null;
          if (isPlaygroundSandboxConversation(prev)) return null;
          const found = batch.find((c) => c.id === prev.id);
          return found ?? prev;
        });
      } catch {
        setConversations([]);
        setHasMoreConversations(false);
        setConversationCursor(null);
      }
    },
    [activeAccount]
  );

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

  // Use a ref so the SW event handlers always see the latest conversations
  // without causing effect re-runs on every conversation list change.
  const conversationsRef = useRef(conversations);
  conversationsRef.current = conversations;

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
        const conv = conversationsRef.current.find((c) => c.id === conversationId);
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
  }, [refreshConversations, optimisticallyMarkRead]);

  const onInboundMessage = useCallback(
    (newMessage, conversationFromEvent) => {
      if (!activeAccount) return;
      const convId = newMessage?.conversation_id;
      const isOpenChat = convId && convId === selectedConversationIdRef.current;
      const preview = inboundPreviewFromMessage(newMessage);
      const nextUpdatedAt =
        newMessage?.timestamp ||
        newMessage?.created_at ||
        conversationFromEvent?.updated_at ||
        new Date().toISOString();

      // Aligner "conversation-meta" sur le meme flux que le badge vert:
      // on injecte tout de suite l'aperçu message + tri.
      if (convId) {
        setConversations((prev) => {
          const idx = prev.findIndex((c) => c.id === convId);
          if (idx === -1) return prev;
          const next = [...prev];
          const current = next[idx];
          const shouldBumpUnread = !isOpenChat && (newMessage?.direction === "inbound" || !newMessage?.from_me);
          const unread = Number(current.unread_count || 0);
          next[idx] = {
            ...current,
            last_message: preview,
            updated_at: nextUpdatedAt,
            unread_count: shouldBumpUnread ? unread + 1 : unread,
          };
          return next.sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1));
        });
      }

      const run = () => refreshConversations(activeAccount, { delta: true });
      if (!isOpenChat) {
        run();
        return;
      }
      if (inboundDeltaDebounceTimerRef.current) {
        clearTimeout(inboundDeltaDebounceTimerRef.current);
      }
      inboundDeltaDebounceTimerRef.current = setTimeout(() => {
        inboundDeltaDebounceTimerRef.current = null;
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
    setSelectedConversation((prev) =>
      prev && isPlaygroundSandboxConversation(prev) ? null : prev
    );
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
      await platformAlert(error.response?.data?.detail || "Erreur lors de la suppression");
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

  // Liste des WA bloqués (app) : nécessaire pour le chat (bandeau, suppression realtime) - pas seulement sur l’onglet contacts.
  useEffect(() => {
    loadAllBlockedWaForContacts();
  }, [loadAllBlockedWaForContacts]);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedContactSearch(contactSearch), 320);
    return () => window.clearTimeout(t);
  }, [contactSearch]);

  useEffect(() => {
    if (navMode === "contacts" && canViewContacts) {
      const trimmed = debouncedContactSearch.trim();
      const params = trimmed ? { q: trimmed, limit: 8000 } : { limit: 15000 };
      getContacts(params)
        .then((res) => {
          const items = res.data?.items || res.data || [];
          setContacts(items);
          setSelectedContact((prev) => {
            if (prev && items.some((c) => c.id === prev.id)) return prev;
            return items[0] ?? null;
          });
        })
        .catch(() => setContacts([]));
    } else if (navMode === "contacts" && !canViewContacts) {
      setContacts([]);
      setSelectedContact(null);
    }
  }, [navMode, canViewContacts, debouncedContactSearch]);

  const filteredContacts = useMemo(
    () => filterContactsBySearch(contacts, contactSearch),
    [contacts, contactSearch]
  );

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
      await platformAlert("Aucun compte WhatsApp actif. Veuillez sélectionner un compte.");
      return;
    }

    if (selectedContacts.size === 0) {
      await platformAlert("Veuillez sélectionner au moins un contact.");
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

      await platformAlert(`Campagne créée avec ${contactObjects.length} contact(s) !`);
    } catch (error) {
      console.error("Error creating campaign:", error);
      await platformAlert(error.response?.data?.detail || "Erreur lors de la création de la campagne");
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
    const scheduleNext = () => {
      if (cancelled) return;
      timeoutId = window.setTimeout(run, 45000);
    };
    const run = () => {
      void refreshConversations(activeAccount, { delta: true }).finally(() => {
        scheduleNext();
      });
    };
    timeoutId = window.setTimeout(run, 45000);
    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [activeAccount, navMode, isWindowActive, refreshConversations]);

  const filteredConversations = useMemo(() => {
    // Si la galerie est affichée, ne pas filtrer les conversations
    if (showGallery) {
      return [];
    }

    const list = excludePlaygroundSandboxConversations(conversations);

    switch (filter) {
      case "unread":
        return list.filter((c) => c.unread_count > 0);
      case "groups":
        // Les groupes seront gérés séparément
        return [];
      case "favorites":
        return list.filter((c) => c.is_favorite);
      case "gallery":
        return list;
      default:
        return list;
    }
  }, [conversations, filter, showGallery]);

  const handleFavoriteToggle = async (conversation, nextState) => {
    await toggleConversationFavorite(conversation.id, nextState);
    refreshConversations();
  };

  const handleBotModeChange = async (conversation, { enabled, reply_mode } = {}) => {
    if (!conversation) return;
    const payload = { enabled };
    if (reply_mode != null) payload.reply_mode = reply_mode;
    const res = await toggleConversationBotMode(conversation.id, payload);
    const updated =
      res.data?.conversation ??
      {
        ...conversation,
        bot_enabled: enabled,
        bot_reply_mode:
          reply_mode ?? conversation.bot_reply_mode ?? "gemini",
      };
    setConversations((prev) =>
      prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
    );
    setSelectedConversation((prev) =>
      prev && prev.id === updated.id ? { ...prev, ...updated } : prev
    );
  };

  const handlePlaygroundFlowChange = async (conversation, playgroundFlowId) => {
    if (!conversation?.id) return;
    const res = await setConversationPlaygroundFlow(
      conversation.id,
      playgroundFlowId
    );
    const updated =
      res.data?.conversation ?? {
        ...conversation,
        playground_flow_id: playgroundFlowId,
      };
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
  const canAccessAxelia = hasPermission?.("axelia.access");
  const canAccessPlayground = hasPermission?.("playground.access");
  const canAccessAgentStudio = hasPermission?.("agent_studio.access");

  const allowedNavItems = useMemo(() => {
    const items = ["chat"];
    if (canViewContacts) {
      items.push("contacts");
    }
    if (canAccessAxelia) {
      items.push("axelia");
    }
    if (canAccessAgentStudio) {
      items.push("agentStudio");
    }
    if (canAccessPlayground) {
      items.push("assistant");
    }
    items.push("whatsapp");
    items.push("settings");
    return items;
  }, [canViewContacts, canAccessPlayground, canAccessAxelia, canAccessAgentStudio]);

  useEffect(() => {
    const modeFromUrl = inboxPathToMode(location.pathname);
    if (modeFromUrl === null) {
      navigate(INBOX_PATH_BY_MODE.chat, { replace: true });
    }
  }, [location.pathname, navigate]);

  useEffect(() => {
    if (!allowedNavItems.includes(navMode)) {
      navigate(INBOX_PATH_BY_MODE.chat, { replace: true });
    }
  }, [allowedNavItems, navMode, navigate]);

  const canSendMessage =
    selectedConversation && selectedConversation.account_id
      ? hasPermission?.("messages.send", selectedConversation.account_id)
      : false;

  const lazyFallback = <div style={{ padding: 24 }}>Chargement...</div>;

  return (
    <div className="app-shell">
      <div className="workspace">
        <SidebarNav active={navMode} onSelect={handleNavSelect} allowedItems={allowedNavItems} onSignOut={signOut} />
        <Suspense fallback={lazyFallback}>

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
                          {selectedContacts.size} sélectionné{selectedContacts.size > 1 ? "s" : ""}
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
                <div className="contacts-search">
                  <div className="contacts-search__inner">
                    <span className="contacts-search__icon" aria-hidden>
                      <FiSearch size={18} />
                    </span>
                    <input
                      type="search"
                      className="contacts-search__input"
                      placeholder="Nom, prénom, numéro…"
                      value={contactSearch}
                      onChange={(e) => setContactSearch(e.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                </div>
                <ContactsPanel
                  contacts={filteredContacts}
                  selected={selectedContact}
                  onSelect={setSelectedContact}
                  selectedContacts={selectedContacts}
                  onToggleSelect={handleToggleContactSelect}
                  multiSelect={multiSelectMode}
                  canModerateWaAny={canModerateWaAny}
                  metaBlockedNormalizedIds={mergedBlockedWaIds}
                  metaBlockBusyId={metaBlockBusyId}
                  onMetaBlockOpen={(contact, action) => setMetaBlockModal({ contact, action })}
                />
                <MetaBlockAccountModal
                  open={Boolean(metaBlockModal)}
                  onClose={() => !metaBlockBusyId && setMetaBlockModal(null)}
                  action={metaBlockModal?.action}
                  accounts={metaBlockModalAccounts}
                  busy={Boolean(metaBlockBusyId && metaBlockModal?.contact?.id === metaBlockBusyId)}
                  onConfirm={handleMetaBlockModalConfirm}
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
        ) : navMode === "axelia" ? (
          canAccessAxelia ? (
            <div className="workspace-main settings-mode">
              <AxeliaChat
                accounts={accounts}
                initialAccountId={activeAccount}
                profile={profile}
                hasPermission={hasPermission}
              />
            </div>
          ) : (
            <div className="workspace-main settings-mode">
              <p className="panel-title">Axelia</p>
              <p>Vous n&apos;avez pas accès à Axelia.</p>
            </div>
          )
        ) : navMode === "agentStudio" ? (
          canAccessAgentStudio ? (
            <div className="workspace-main settings-mode">
              <AgentStudioPage
                accountId={activeAccount}
                accounts={accounts}
                onAccountChange={setActiveAccount}
                disabled={!canAccessAgentStudio}
              />
            </div>
          ) : (
            <div className="workspace-main settings-mode">
              <p className="panel-title">Agent Studio</p>
              <p>Vous n&apos;avez pas accès à Agent Studio.</p>
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
            <AssistantPanel
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
                            await platformAlert(`Impossible de créer la conversation: ${errorMsg}`);
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
                    hasMore={hasMoreConversations}
                    loadingMore={loadingMoreConversations}
                    onLoadMore={loadMoreConversations}
                  />
                </>
              )}
            </div>

            {!showGallery && filter !== "groups" && (
              <ChatWindow
                conversation={selectedConversation}
                onFavoriteToggle={handleFavoriteToggle}
                onBotModeChange={handleBotModeChange}
                onPlaygroundFlowChange={handlePlaygroundFlowChange}
                onMarkRead={optimisticallyMarkRead}
                isWindowActive={isWindowActive && navMode === "chat"}
                canSend={canSendMessage}
                conversationInternallyBlocked={conversationInternallyBlocked}
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
        </Suspense>
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