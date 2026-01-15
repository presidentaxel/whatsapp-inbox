"""
Script pour identifier et analyser les messages manquants.

IMPORTANT: L'API WhatsApp Cloud ne permet PAS de récupérer l'historique des messages.
Les messages ne sont disponibles que via les webhooks en temps réel.
Une fois qu'un webhook est perdu ou qu'un message n'a pas été inséré, il est perdu définitivement.

Ce script permet de:
1. Identifier les messages qui ont été reçus mais pas insérés (via les logs)
2. Vérifier les gaps dans la base de données
3. Analyser les erreurs récentes d'insertion
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# Ajouter le répertoire parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import supabase, supabase_execute
from app.services.account_service import get_all_accounts


async def find_missing_messages_by_timestamp_gaps(
    account_id: Optional[str] = None,
    hours_back: int = 24
) -> List[Dict]:
    """
    Identifie les gaps dans les timestamps des messages pour détecter des messages manquants.
    
    Cette méthode n'est pas parfaite car:
    - Les utilisateurs peuvent ne pas envoyer de messages pendant un certain temps
    - Mais si on voit un gap anormalement long, c'est suspect
    """
    print("\n" + "="*80)
    print("1. ANALYSE DES GAPS DANS LES TIMESTAMPS")
    print("="*80)
    
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    
    # Construire la requête
    query = (
        supabase.table("messages")
        .select("id, conversation_id, direction, timestamp, wa_message_id, message_type")
        .eq("direction", "inbound")
        .gte("timestamp", cutoff_time)
        .order("timestamp", desc=False)
    )
    
    if account_id:
        # Si on a un account_id, filtrer par les conversations de ce compte
        conversations_result = await supabase_execute(
            supabase.table("conversations")
            .select("id")
            .eq("account_id", account_id)
        )
        if conversations_result.data:
            conversation_ids = [c["id"] for c in conversations_result.data]
            query = query.in_("conversation_id", conversation_ids)
    
    result = await supabase_execute(query)
    
    if not result.data or len(result.data) < 2:
        print("⚠️ Pas assez de messages pour détecter des gaps")
        return []
    
    # Analyser les gaps
    gaps = []
    messages = sorted(result.data, key=lambda x: x["timestamp"])
    
    for i in range(len(messages) - 1):
        current_time = datetime.fromisoformat(messages[i]["timestamp"].replace("Z", "+00:00"))
        next_time = datetime.fromisoformat(messages[i + 1]["timestamp"].replace("Z", "+00:00"))
        gap_seconds = (next_time - current_time).total_seconds()
        
        # Si le gap est supérieur à 1 heure, c'est suspect
        if gap_seconds > 3600:
            gaps.append({
                "gap_seconds": gap_seconds,
                "gap_hours": gap_seconds / 3600,
                "before_message": messages[i],
                "after_message": messages[i + 1],
                "gap_start": messages[i]["timestamp"],
                "gap_end": messages[i + 1]["timestamp"],
            })
    
    if gaps:
        print(f"⚠️ {len(gaps)} gap(s) suspect(s) détecté(s):")
        for gap in gaps[:10]:  # Afficher les 10 premiers
            print(f"\n   Gap de {gap['gap_hours']:.1f} heures:")
            print(f"   - Avant: {gap['before_message']['timestamp']} (wa_message_id: {gap['before_message']['wa_message_id']})")
            print(f"   - Après: {gap['after_message']['timestamp']} (wa_message_id: {gap['after_message']['wa_message_id']})")
    else:
        print("✅ Aucun gap suspect détecté")
    
    return gaps


async def find_failed_insertions_in_logs() -> None:
    """
    Analyse les patterns d'erreur dans les logs pour identifier les messages qui ont échoué.
    
    Note: Cette fonction nécessite l'accès aux logs. Elle donne des instructions
    sur comment analyser les logs manuellement.
    """
    print("\n" + "="*80)
    print("2. ANALYSE DES ERREURS D'INSERTION")
    print("="*80)
    
    print("ℹ️ Pour identifier les messages qui ont échoué, cherchez dans les logs:")
    print("\n   Commandes utiles:")
    print("   docker logs <container_name> | grep 'MESSAGE INSERT'")
    print("   docker logs <container_name> | grep 'CRITICAL: Failed to upsert'")
    print("   docker logs <container_name> | grep 'UnboundLocalError'")
    
    print("\n   Patterns à chercher:")
    print("   - '❌ [MESSAGE INSERT] CRITICAL: Failed to upsert message'")
    print("   - 'UnboundLocalError: cannot access local variable'")
    print("   - 'wa_message_id=wamid...' (les IDs des messages qui ont échoué)")
    
    print("\n   Exemple de recherche:")
    print("   docker logs backend-1 --since 24h | grep -A 5 'Failed to upsert'")
    
    # Vérifier s'il y a des messages récents avec des erreurs dans la structure
    print("\n   Vérification des messages avec des champs manquants...")
    
    # Chercher les messages récents sans wa_message_id (suspect)
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    result = await supabase_execute(
        supabase.table("messages")
        .select("id, conversation_id, timestamp, wa_message_id, message_type")
        .eq("direction", "inbound")
        .gte("timestamp", one_hour_ago)
        .is_("wa_message_id", "null")
        .limit(10)
    )
    
    if result.data:
        print(f"   ⚠️ {len(result.data)} message(s) récent(s) sans wa_message_id (suspect):")
        for msg in result.data:
            print(f"      - ID: {msg['id']}, timestamp: {msg['timestamp']}")
    else:
        print("   ✅ Tous les messages récents ont un wa_message_id")


async def check_conversation_message_counts(
    account_id: Optional[str] = None,
    hours_back: int = 24
) -> None:
    """
    Vérifie le nombre de messages par conversation pour détecter des anomalies.
    """
    print("\n" + "="*80)
    print("3. ANALYSE DU NOMBRE DE MESSAGES PAR CONVERSATION")
    print("="*80)
    
    cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    
    # Requête pour compter les messages par conversation
    query = (
        supabase.table("messages")
        .select("conversation_id, direction, timestamp")
        .gte("timestamp", cutoff_time)
        .order("timestamp", desc=True)
    )
    
    if account_id:
        conversations_result = await supabase_execute(
            supabase.table("conversations")
            .select("id")
            .eq("account_id", account_id)
        )
        if conversations_result.data:
            conversation_ids = [c["id"] for c in conversations_result.data]
            query = query.in_("conversation_id", conversation_ids)
    
    result = await supabase_execute(query)
    
    if not result.data:
        print("⚠️ Aucun message trouvé dans la période")
        return
    
    # Compter par conversation
    counts = {}
    for msg in result.data:
        conv_id = msg["conversation_id"]
        if conv_id not in counts:
            counts[conv_id] = {"inbound": 0, "outbound": 0}
        counts[conv_id][msg["direction"]] += 1
    
    print(f"✅ {len(counts)} conversation(s) active(s) dans les dernières {hours_back} heures:")
    for conv_id, counts_dict in sorted(counts.items(), key=lambda x: sum(x[1].values()), reverse=True)[:10]:
        total = counts_dict["inbound"] + counts_dict["outbound"]
        print(f"   - Conversation {conv_id[:8]}...: {total} messages ({counts_dict['inbound']} inbound, {counts_dict['outbound']} outbound)")


async def explain_limitations() -> None:
    """
    Explique les limitations de l'API WhatsApp et pourquoi on ne peut pas récupérer les messages.
    """
    print("\n" + "="*80)
    print("4. LIMITATIONS DE L'API WHATSAPP CLOUD")
    print("="*80)
    
    print("❌ L'API WhatsApp Cloud ne permet PAS de:")
    print("   - Récupérer l'historique des messages")
    print("   - Lire les messages déjà envoyés/reçus")
    print("   - Accéder aux messages passés")
    
    print("\n✅ L'API WhatsApp Cloud permet seulement de:")
    print("   - Recevoir des messages en temps réel via webhooks")
    print("   - Envoyer de nouveaux messages")
    print("   - Gérer les templates et médias")
    
    print("\n💡 SOLUTIONS POUR ÉVITER LA PERTE DE MESSAGES:")
    print("   1. ✅ CORRIGER LE BUG (déjà fait - UnboundLocalError corrigé)")
    print("   2. ✅ Ajouter une gestion d'erreur robuste")
    print("   3. 💾 Sauvegarder les webhooks dans une table de backup")
    print("   4. 📊 Monitorer les erreurs d'insertion en temps réel")
    print("   5. 🔄 Implémenter un système de retry pour les insertions échouées")
    
    print("\n⚠️ MESSAGES PERDUS:")
    print("   Les messages qui ont été reçus mais pas insérés à cause du bug")
    print("   sont PERDUS DÉFINITIVEMENT et ne peuvent pas être récupérés.")


async def suggest_improvements() -> None:
    """
    Suggère des améliorations pour éviter la perte de messages à l'avenir.
    """
    print("\n" + "="*80)
    print("5. AMÉLIORATIONS SUGGÉRÉES")
    print("="*80)
    
    print("📋 Pour éviter la perte de messages à l'avenir:")
    print("\n   1. TABLE DE BACKUP DES WEBHOOKS:")
    print("      - Créer une table 'webhook_backup' pour sauvegarder tous les webhooks")
    print("      - Permet de re-traiter les webhooks en cas d'erreur")
    
    print("\n   2. SYSTÈME DE RETRY:")
    print("      - Implémenter un système de retry avec queue (Redis, etc.)")
    print("      - Re-essayer automatiquement les insertions échouées")
    
    print("\n   3. MONITORING:")
    print("      - Alertes en cas d'erreur d'insertion")
    print("      - Dashboard pour voir les messages manquants")
    
    print("\n   4. VALIDATION AVANT INSERTION:")
    print("      - Vérifier que tous les champs requis sont présents")
    print("      - Valider les données avant l'insertion")


async def main():
    print("\n" + "="*80)
    print("RÉCUPÉRATION DES MESSAGES MANQUANTS")
    print("="*80)
    print(f"Date: {datetime.now(timezone.utc).isoformat()}")
    print("\n⚠️  ATTENTION: L'API WhatsApp ne permet PAS de récupérer les messages perdus!")
    print("   Ce script identifie seulement les messages manquants pour diagnostic.")
    
    # Récupérer tous les comptes
    accounts = await get_all_accounts()
    if not accounts:
        print("\n❌ Aucun compte WhatsApp trouvé")
        return
    
    print(f"\n✅ {len(accounts)} compte(s) trouvé(s)")
    
    # Analyser pour chaque compte ou pour tous
    account_id = None
    if len(accounts) == 1:
        account_id = accounts[0]["id"]
        print(f"   Analyse pour le compte: {accounts[0]['name']}")
    else:
        print("   Analyse pour tous les comptes")
    
    # 1. Analyser les gaps
    gaps = await find_missing_messages_by_timestamp_gaps(account_id, hours_back=24)
    
    # 2. Analyser les erreurs dans les logs
    await find_failed_insertions_in_logs()
    
    # 3. Vérifier les comptes par conversation
    await check_conversation_message_counts(account_id, hours_back=24)
    
    # 4. Expliquer les limitations
    await explain_limitations()
    
    # 5. Suggérer des améliorations
    await suggest_improvements()
    
    # Résumé
    print("\n" + "="*80)
    print("RÉSUMÉ")
    print("="*80)
    
    if gaps:
        print(f"⚠️ {len(gaps)} gap(s) suspect(s) détecté(s)")
        print("   → Ces gaps peuvent indiquer des messages manquants")
        print("   → Mais ils peuvent aussi être normaux (pas de messages pendant un certain temps)")
    else:
        print("✅ Aucun gap suspect détecté")
    
    print("\n❌ IMPORTANT: Les messages perdus ne peuvent PAS être récupérés")
    print("   → L'API WhatsApp ne permet pas de lire l'historique")
    print("   → Les messages doivent être reçus via webhooks en temps réel")
    
    print("\n✅ Le bug UnboundLocalError a été corrigé")
    print("   → Les nouveaux messages devraient maintenant être insérés correctement")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    asyncio.run(main())

