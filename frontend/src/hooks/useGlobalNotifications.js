import { useEffect, useRef } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import { 
  notifyNewMessage, 
  askForNotificationPermission,
  isNotificationEnabledForAccount 
} from '../utils/notifications';
import { useAuth } from '../context/AuthContext';

/**
 * Hook global pour écouter TOUS les nouveaux messages et afficher des notifications
 * Vérifie les permissions avant d'envoyer une notification
 * Ne notifie que si l'utilisateur a accès au compte/conversation
 */
export function useGlobalNotifications(selectedConversationId = null, onInboundMessage = null) {
  const { hasPermission, profile } = useAuth();
  const channelRef = useRef(null);
  const lastNotifiedRef = useRef(new Set());

  useEffect(() => {
    askForNotificationPermission();

    if (channelRef.current) {
      supabaseClient.removeChannel(channelRef.current);
      channelRef.current = null;
    }
    lastNotifiedRef.current.clear();

    // Only subscribe if we have a profile with permissions loaded
    if (!profile?.permissions?.account_access_levels) {
      return;
    }

    // Filter: only listen for inbound messages (direction = 'inbound')
    const channel = supabaseClient
      .channel('global-messages-notifications-inbound')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: 'direction=eq.inbound',
        },
        async (payload) => {
          const newMessage = payload.new;

          // Éviter les doublons (notifications multiples pour le même message)
          const messageKey = `${newMessage.id}-${newMessage.conversation_id}`;
          if (lastNotifiedRef.current.has(messageKey)) {
            return;
          }
          lastNotifiedRef.current.add(messageKey);

          // Nettoyer les anciennes clés après 5 minutes
          setTimeout(() => {
            lastNotifiedRef.current.delete(messageKey);
          }, 5 * 60 * 1000);

          // Charger la conversation pour obtenir les infos du contact
          try {
            const { data: conversation, error } = await supabaseClient
              .from('conversations')
              .select('*, contacts(*)')
              .eq('id', newMessage.conversation_id)
              .single();

            if (error || !conversation) {
              return;
            }

            // Vérifier que l'utilisateur a accès à ce compte/conversation
            const accountId = conversation.account_id;
            if (!accountId) {
              // Pas de compte associé, ne pas notifier
              return;
            }

            const accountAccessLevels = profile.permissions.account_access_levels;

            // Vérification STRICTE : si l'utilisateur a access_level = 'aucun' pour ce compte,
            // ne pas envoyer de notification
            // On vérifie avec différentes variantes de la clé pour être sûr (format UUID peut varier)
            const accountIdStr = String(accountId);
            const accessLevel = accountAccessLevels[accountId] || 
                               accountAccessLevels[accountIdStr] ||
                               accountAccessLevels[accountIdStr.trim()];
            
            // Blocage explicite si access_level = 'aucun'
            // Cette vérification est critique : elle doit bloquer TOUTES les notifications
            // pour les utilisateurs avec access_level = 'aucun'
            if (accessLevel === "aucun") {
              // L'utilisateur n'a aucun accès à ce compte, ne pas notifier
              // Cette vérification passe avant hasPermission pour être absolument sûr
              return;
            }

            // Vérifier les permissions : l'utilisateur doit avoir conversations.view pour ce compte
            // Cela vérifie automatiquement si access_level = 'aucun' (via hasPermission)
            // Cette vérification est redondante mais ajoute une couche de sécurité supplémentaire
            if (!hasPermission || !hasPermission('conversations.view', accountId)) {
              return;
            }

            // Signal the parent to refresh conversation list immediately
            if (onInboundMessage) {
              try { onInboundMessage(newMessage, conversation); } catch {}
            }

            if (!isNotificationEnabledForAccount(accountId, 'messages')) {
              return;
            }

            const isVisible = document.visibilityState === 'visible';
            const hasFocus = document.hasFocus?.() === true;
            const isForeground = isVisible && hasFocus;
            const isConversationOpen = selectedConversationId === conversation.id;
            
            if (isForeground && isConversationOpen) {
              return;
            }

            await notifyNewMessage(newMessage, conversation, {
              checkConversationOpen: false,
              force: false
            });
          } catch (error) {
            // Erreur silencieuse
          }
        }
      )
      .subscribe(() => {});

    channelRef.current = channel;

    // Cleanup
    return () => {
      if (channelRef.current) {
        supabaseClient.removeChannel(channelRef.current);
        channelRef.current = null;
      }
      lastNotifiedRef.current.clear();
    };
  }, [selectedConversationId, hasPermission, profile, onInboundMessage]);
}

