import { useEffect, useRef } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import { notifyNewMessage, askForNotificationPermission } from '../utils/notifications';
import { useAuth } from '../context/AuthContext';

/**
 * Hook global pour écouter TOUS les nouveaux messages et afficher des notifications
 * Vérifie les permissions avant d'envoyer une notification
 * Ne notifie que si l'utilisateur a accès au compte/conversation
 */
export function useGlobalNotifications(selectedConversationId = null) {
  const { hasPermission } = useAuth();
  const channelRef = useRef(null);
  const lastNotifiedRef = useRef(new Set()); // Éviter les doublons

  useEffect(() => {
    // S'assurer d'avoir la permission (une seule demande ici)
    askForNotificationPermission();

    // Nettoyer l'ancien channel
    if (channelRef.current) {
      supabaseClient.removeChannel(channelRef.current);
      channelRef.current = null;
    }
    lastNotifiedRef.current.clear();

    console.log('🔔 Initialisation des notifications globales - Écoute de TOUS les messages');

    // Écouter TOUS les nouveaux messages sans aucune restriction
    // On écoute tous les INSERT sur messages et on notifie tout sauf si la conversation est ouverte
    const channel = supabaseClient
      .channel('global-messages-notifications-all')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
        },
        async (payload) => {
          const newMessage = payload.new;
          
          // Ignorer UNIQUEMENT les messages sortants (de nous)
          if (newMessage.direction === 'outbound') {
            console.debug('🔕 Skip notify (outbound message)', {
              messageId: newMessage.id,
              conversationId: newMessage.conversation_id,
            });
            return;
          }

          // Éviter les doublons (notifications multiples pour le même message)
          const messageKey = `${newMessage.id}-${newMessage.conversation_id}`;
          if (lastNotifiedRef.current.has(messageKey)) {
            console.debug('🔕 Skip notify (duplicate)', { messageKey });
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
              console.warn('⚠️ Conversation non trouvée pour le message:', newMessage.id);
              return;
            }

            // Vérifier que l'utilisateur a accès à ce compte/conversation
            const accountId = conversation.account_id;
            if (!accountId) {
              console.warn('⚠️ Conversation sans account_id:', conversation.id);
              return;
            }

            // Vérifier les permissions : l'utilisateur doit avoir conversations.view pour ce compte
            // Cela vérifie automatiquement si access_level = 'aucun' (via hasPermission)
            if (!hasPermission || !hasPermission('conversations.view', accountId)) {
              console.debug('🔕 Skip notify (no access to account)', {
                messageId: newMessage.id,
                conversationId: conversation.id,
                accountId: accountId,
              });
              return;
            }

            // Vérifier si on doit notifier
            // Notifier si :
            // - l'app n'est pas au premier plan (tab masqué ou fenêtre non focus)
            // - ou si la conversation n'est pas ouverte
            const isVisible = document.visibilityState === 'visible';
            const hasFocus = document.hasFocus?.() === true;
            const isForeground = isVisible && hasFocus;
            const isConversationOpen = selectedConversationId === conversation.id;
            
            if (isForeground && isConversationOpen) {
              // L'utilisateur regarde déjà cette conversation dans une fenêtre active
              console.debug('🔕 Skip notify (foreground & open conversation)', {
                messageId: newMessage.id,
                conversationId: conversation.id,
              });
              return;
            }

            // Afficher la notification seulement si l'utilisateur a accès
            console.log('🔔 Notification pour message:', {
              messageId: newMessage.id,
              conversationId: conversation.id,
              accountId: accountId,
              contact: conversation.contacts?.display_name || conversation.client_number,
              isAppVisible: isVisible,
              hasFocus,
              isConversationOpen
            });

            await notifyNewMessage(newMessage, conversation, {
              checkConversationOpen: false,
              force: false
            });
          } catch (error) {
            console.error('❌ Erreur lors de la notification:', error);
          }
        }
      )
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          console.log('✅ Notifications globales activées - Écoute de TOUS les messages entrants');
        } else if (status === 'CHANNEL_ERROR') {
          console.error('❌ Erreur de connexion aux notifications');
        }
      });

    channelRef.current = channel;

    // Cleanup
    return () => {
      if (channelRef.current) {
        supabaseClient.removeChannel(channelRef.current);
        channelRef.current = null;
      }
      lastNotifiedRef.current.clear();
      console.log('🔕 Notifications globales désactivées');
    };
  }, [selectedConversationId, hasPermission]);
}

