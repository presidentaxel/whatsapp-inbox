import { useEffect, useRef } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import { notifyNewMessage } from '../utils/notifications';

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
          if (newMessage.from_me) {
            return;
          }

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
              console.warn('⚠️ Conversation non trouvée pour le message:', newMessage.id);
              return;
            }

            // Vérifier si on doit notifier
            // Ne notifier QUE si :
            // 1. L'app est en arrière-plan OU
            // 2. La conversation n'est pas ouverte
            const isAppVisible = !document.hidden;
            const isConversationOpen = selectedConversationId === conversation.id;
            
            if (isAppVisible && isConversationOpen) {
              // L'utilisateur est en train de regarder cette conversation
              // Pas besoin de notifier
              return;
            }

            // Afficher la notification pour TOUS les autres cas
            console.log('🔔 Notification pour message:', {
              messageId: newMessage.id,
              conversationId: conversation.id,
              contact: conversation.contacts?.display_name || conversation.client_number,
              isAppVisible,
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

