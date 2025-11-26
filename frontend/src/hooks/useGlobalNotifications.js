import { useEffect, useRef } from 'react';
import { supabaseClient } from '../api/supabaseClient';
import { notifyNewMessage } from '../utils/notifications';

/**
 * Hook global pour écouter tous les nouveaux messages et afficher des notifications
 * Fonctionne comme WhatsApp : notifications pour tous les messages entrants
 */
export function useGlobalNotifications(accounts = [], selectedConversationId = null) {
  const channelRef = useRef(null);
  const lastNotifiedRef = useRef(new Set()); // Éviter les doublons
  const accountsIdsRef = useRef(new Set());

  // Mettre à jour la liste des IDs de comptes
  useEffect(() => {
    accountsIdsRef.current = new Set(accounts.map(acc => acc.id));
  }, [accounts]);

  useEffect(() => {
    // Nettoyer l'ancien channel
    if (channelRef.current) {
      supabaseClient.removeChannel(channelRef.current);
      channelRef.current = null;
    }
    lastNotifiedRef.current.clear();

    // Si pas de comptes, ne rien faire
    if (!accounts.length || accountsIdsRef.current.size === 0) {
      return;
    }

    // Écouter tous les nouveaux messages (on filtre côté client)
    // Note: Supabase Realtime ne permet pas de filtrer facilement par relation
    // On écoute tous les INSERT sur messages et on filtre intelligemment
    const channel = supabaseClient
      .channel('global-messages-notifications')
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
        },
        async (payload) => {
          const newMessage = payload.new;
          
          // Ignorer les messages sortants (de nous)
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

          // Charger la conversation pour vérifier qu'elle appartient à un compte géré
          try {
            const { data: conversation, error } = await supabaseClient
              .from('conversations')
              .select('*, contacts(*)')
              .eq('id', newMessage.conversation_id)
              .single();

            if (error || !conversation) {
              return;
            }

            // Vérifier que la conversation appartient à un compte géré
            if (!accountsIdsRef.current.has(conversation.account_id)) {
              return;
            }

            // Vérifier si on doit notifier
            // Ne pas notifier si l'app est au premier plan ET la conversation est ouverte
            const isAppVisible = !document.hidden;
            const isConversationOpen = selectedConversationId === conversation.id;
            
            if (isAppVisible && isConversationOpen) {
              // L'utilisateur est en train de regarder cette conversation
              // Pas besoin de notifier
              return;
            }

            // Afficher la notification
            // On passe checkConversationOpen: false car on l'a déjà vérifié
            await notifyNewMessage(newMessage, conversation, {
              checkConversationOpen: false
            });
          } catch (error) {
            console.error('Erreur lors de la notification:', error);
          }
        }
      )
      .subscribe();

    channelRef.current = channel;

    // Cleanup
    return () => {
      if (channelRef.current) {
        supabaseClient.removeChannel(channelRef.current);
        channelRef.current = null;
      }
      lastNotifiedRef.current.clear();
    };
  }, [accounts, selectedConversationId]);
}

