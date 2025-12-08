import { useEffect, useRef } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import { notifyNewMessage, askForNotificationPermission } from '../utils/notifications';

/**
 * Hook global pour écouter TOUS les nouveaux messages et afficher des notifications
 * Fonctionne comme WhatsApp : notifications pour TOUS les messages entrants
 * Peu importe le compte, la plateforme, etc.
 * 
 * La gestion fine (par compte, etc.) sera ajoutée plus tard
 */
export function useGlobalNotifications(selectedConversationId = null) {
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

            // Afficher la notification pour TOUS les autres cas
            console.log('🔔 Notification pour message:', {
              messageId: newMessage.id,
              conversationId: conversation.id,
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
  }, [selectedConversationId]);
}

