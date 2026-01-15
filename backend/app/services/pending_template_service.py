"""
Service pour gérer les templates en attente de validation Meta
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from app.core.db import supabase, supabase_execute
from app.services import whatsapp_api_service
from app.services.template_validator import TemplateValidator
from app.services.message_service import send_template_message
from app.services.account_service import get_account_by_id

logger = logging.getLogger(__name__)


async def create_and_queue_template(
    conversation_id: str,
    account_id: str,
    message_id: str,
    text_content: str,
    campaign_id: Optional[str] = None
) -> Dict[str, Any]:
    """Crée un template Meta et le met en file d'attente"""
    
    logger.info("=" * 80)
    logger.info(f"🔧 [CREATE-TEMPLATE] Début - conversation_id={conversation_id}, account_id={account_id}, message_id={message_id}")
    logger.info(f"🔧 [CREATE-TEMPLATE] Texte à valider (premiers 100 caractères): {text_content[:100]}")
    
    # Valider le texte
    is_valid, errors = TemplateValidator.validate_text(text_content)
    logger.info(f"✅ [CREATE-TEMPLATE] Validation du texte: is_valid={is_valid}, errors={errors}")
    if not is_valid:
        logger.error(f"❌ [CREATE-TEMPLATE] Texte invalide: {errors}")
        return {
            "success": False,
            "errors": errors
        }
    
    # Générer un nom de template unique
    template_name = TemplateValidator.generate_template_name(text_content, conversation_id)
    
    # Valider le nom généré
    name_valid, name_errors = TemplateValidator.validate_template_name(template_name)
    if not name_valid:
        return {
            "success": False,
            "errors": name_errors
        }
    
    sanitized_text = TemplateValidator.sanitize_for_template(text_content)
    
    # Récupérer le compte
    account = await get_account_by_id(account_id)
    if not account:
        logger.error(f"❌ Compte {account_id} non trouvé pour la création du template")
        return {"success": False, "errors": ["Compte non trouvé"]}
    
    waba_id = account.get("waba_id")
    access_token = account.get("access_token")
    account_name = account.get("name", "Inconnu")
    
    logger.info(f"📝 Création du template '{template_name}' pour le message {message_id}")
    logger.info(f"   Compte WhatsApp: {account_name} (ID: {account_id}, WABA: {waba_id})")
    
    if not waba_id or not access_token:
        logger.error(f"❌ WhatsApp non configuré pour le compte {account_name}: waba_id={waba_id}, access_token={'présent' if access_token else 'absent'}")
        return {"success": False, "errors": ["WhatsApp non configuré (waba_id ou access_token manquant)"]}
    
    # Créer le template via Meta API
    try:
        components = [{
            "type": "BODY",
            "text": sanitized_text
        }]
        
        logger.info(f"📤 [CREATE-TEMPLATE] Appel à l'API Meta pour créer le template...")
        logger.info(f"   - WABA ID: {waba_id}")
        logger.info(f"   - Template name: {template_name}")
        logger.info(f"   - Category: UTILITY")
        logger.info(f"   - Language: fr")
        logger.info(f"   - Components: {components}")
        
        result = await whatsapp_api_service.create_message_template(
            waba_id=waba_id,
            access_token=access_token,
            name=template_name,
            category="UTILITY",  # UTILITY pour les messages transactionnels
            language="fr",
            components=components
        )
        
        logger.info(f"📥 [CREATE-TEMPLATE] Réponse de Meta: {result}")
        
        meta_template_id = result.get("id")
        
        if not meta_template_id:
            logger.error(f"❌ [CREATE-TEMPLATE] Meta n'a pas retourné d'ID pour le template '{template_name}'")
            logger.error(f"   Réponse complète: {result}")
            return {
                "success": False,
                "errors": ["Erreur lors de la création du template: aucun ID retourné par Meta"]
            }
        
        logger.info(f"✅ [CREATE-TEMPLATE] Template créé sur Meta avec l'ID: {meta_template_id}")
        
        # Stocker dans la base
        from app.core.db import supabase
        pending_template_payload = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "account_id": account_id,
            "template_name": template_name,
            "text_content": text_content,
            "meta_template_id": meta_template_id,
            "template_status": "PENDING"
        }
        if campaign_id:
            pending_template_payload["campaign_id"] = campaign_id
        
        await supabase_execute(
            supabase.table("pending_template_messages").insert(pending_template_payload)
        )
        
        logger.info(f"✅ Template '{template_name}' créé et mis en file d'attente (ID Meta: {meta_template_id})")
        logger.info(f"   Compte: {account_name} (WABA: {waba_id})")
        
        # Faire une première vérification immédiate (le template peut être approuvé très rapidement)
        asyncio.create_task(check_template_status_once(message_id))
        
        # Lancer la vérification périodique en arrière-plan (non bloquant)
        asyncio.create_task(check_template_status_async(message_id))
        
        # Vérifier si le message est déjà lu (au cas où il serait lu très rapidement)
        # et nettoyer le template si nécessaire
        from app.core.db import supabase
        message_check = await supabase_execute(
            supabase.table("messages")
            .select("status")
            .eq("id", message_id)
            .limit(1)
        )
        if message_check.data and len(message_check.data) > 0 and message_check.data[0].get("status") == "read":
            # Le message est déjà lu, supprimer le template immédiatement
            asyncio.create_task(delete_auto_template_for_message(message_id))
        
        return {
            "success": True,
            "template_name": template_name,
            "meta_template_id": meta_template_id
        }
        
    except Exception as e:
        logger.error(f"❌ [CREATE-TEMPLATE] Erreur lors de la création du template: {e}", exc_info=True)
        error_msg = str(e)
        
        # Extraire le message d'erreur de Meta si disponible
        if hasattr(e, 'response'):
            try:
                if hasattr(e.response, 'json'):
                    error_data = e.response.json()
                    logger.error(f"❌ [CREATE-TEMPLATE] Détails de l'erreur Meta: {error_data}")
                    if 'error' in error_data:
                        error_info = error_data['error']
                        error_msg = error_info.get('message', error_msg)
                        # Ajouter les détails supplémentaires si disponibles
                        if 'error_subcode' in error_info:
                            error_msg += f" (subcode: {error_info['error_subcode']})"
                        if 'error_user_title' in error_info:
                            error_msg += f" - {error_info['error_user_title']}"
                elif hasattr(e.response, 'text'):
                    error_text = e.response.text
                    logger.error(f"❌ [CREATE-TEMPLATE] Réponse texte d'erreur Meta: {error_text}")
                    error_msg = error_text[:200]  # Limiter la longueur
            except Exception as parse_error:
                logger.error(f"❌ [CREATE-TEMPLATE] Erreur lors du parsing de l'erreur: {parse_error}")
        
        return {
            "success": False,
            "errors": [f"Erreur lors de la création du template: {error_msg}"]
        }


async def check_template_status_once(message_id: str):
    """Fait une vérification unique du statut du template (pour vérification immédiate)"""
    # Attendre 5 secondes pour que Meta synchronise
    logger.info(f"⏳ [CHECK-ONCE] Attente de 5 secondes avant vérification immédiate pour le message {message_id}")
    print(f"⏳ [CHECK-ONCE] Attente de 5 secondes avant vérification immédiate pour le message {message_id}")
    await asyncio.sleep(5)
    
    try:
        logger.info(f"🔍 [CHECK-ONCE] Vérification immédiate du statut pour le message {message_id}")
        print(f"🔍 [CHECK-ONCE] Vérification immédiate du statut pour le message {message_id}")
        
        result = await check_and_update_template_status(message_id)
        
        logger.info(f"📊 [CHECK-ONCE] Résultat pour message {message_id}: statut={result.get('status')}")
        print(f"📊 [CHECK-ONCE] Résultat pour message {message_id}: statut={result.get('status')}")
        
        if result["status"] == "APPROVED":
            logger.info(f"✅ [CHECK-ONCE] Template approuvé immédiatement pour le message {message_id}, envoi en cours...")
            print(f"✅ [CHECK-ONCE] Template approuvé immédiatement pour le message {message_id}, envoi en cours...")
            await send_pending_template(message_id)
        elif result["status"] == "REJECTED":
            logger.warning(f"❌ [CHECK-ONCE] Template rejeté immédiatement pour le message {message_id}: {result.get('rejection_reason', 'Raison inconnue')}")
            print(f"❌ [CHECK-ONCE] Template rejeté immédiatement pour le message {message_id}: {result.get('rejection_reason', 'Raison inconnue')}")
            await mark_message_as_failed(message_id, result.get("rejection_reason", "Template rejeté par Meta"))
        else:
            logger.info(f"⏳ [CHECK-ONCE] Template encore en attente pour le message {message_id} (statut: {result.get('status')})")
            print(f"⏳ [CHECK-ONCE] Template encore en attente pour le message {message_id} (statut: {result.get('status')})")
    except Exception as e:
        logger.error(f"❌ [CHECK-ONCE] Erreur lors de la vérification immédiate pour le message {message_id}: {e}", exc_info=True)
        print(f"❌ [CHECK-ONCE] Erreur lors de la vérification immédiate pour le message {message_id}: {e}")


async def check_template_status_async(message_id: str):
    """Vérifie le statut d'un template en arrière-plan de manière périodique"""
    # Attendre un peu avant la première vérification (Meta peut prendre quelques secondes)
    # On a déjà fait une vérification immédiate, donc on attend plus longtemps ici
    await asyncio.sleep(60)  # 1 minute après la création
    
    max_attempts = 288  # 24h avec vérification toutes les 5 minutes (24*60/5 = 288)
    attempt = 0
    
    logger.info(f"🔄 [CHECK-ASYNC] Début de la vérification périodique du statut du template pour le message {message_id}")
    print(f"🔄 [CHECK-ASYNC] Début de la vérification périodique du statut du template pour le message {message_id}")
    
    while attempt < max_attempts:
        try:
            logger.info(f"🔍 [CHECK-ASYNC] Vérification #{attempt + 1}/{max_attempts} pour le message {message_id}")
            print(f"🔍 [CHECK-ASYNC] Vérification #{attempt + 1}/{max_attempts} pour le message {message_id}")
            
            result = await check_and_update_template_status(message_id)
            
            logger.info(f"📊 [CHECK-ASYNC] Résultat pour message {message_id}: statut={result.get('status')}")
            print(f"📊 [CHECK-ASYNC] Résultat pour message {message_id}: statut={result.get('status')}")
            
            if result["status"] in ["APPROVED", "REJECTED"]:
                # Terminé
                if result["status"] == "APPROVED":
                    logger.info(f"✅ [CHECK-ASYNC] Template approuvé pour le message {message_id}, envoi en cours...")
                    print(f"✅ [CHECK-ASYNC] Template approuvé pour le message {message_id}, envoi en cours...")
                    # Envoyer le template
                    await send_pending_template(message_id)
                else:
                    logger.warning(f"❌ [CHECK-ASYNC] Template rejeté pour le message {message_id}: {result.get('rejection_reason', 'Raison inconnue')}")
                    print(f"❌ [CHECK-ASYNC] Template rejeté pour le message {message_id}: {result.get('rejection_reason', 'Raison inconnue')}")
                    # Marquer le message comme échoué
                    await mark_message_as_failed(message_id, result.get("rejection_reason", "Template rejeté par Meta"))
                break
            elif result["status"] == "NOT_FOUND":
                logger.warning(f"⚠️ [CHECK-ASYNC] Template non trouvé pour le message {message_id}, arrêt de la vérification")
                print(f"⚠️ [CHECK-ASYNC] Template non trouvé pour le message {message_id}, arrêt de la vérification")
                break
            else:
                logger.info(f"⏳ [CHECK-ASYNC] Template encore en attente pour le message {message_id} (statut: {result.get('status')})")
                print(f"⏳ [CHECK-ASYNC] Template encore en attente pour le message {message_id} (statut: {result.get('status')})")
                
        except Exception as e:
            logger.error(f"❌ [CHECK-ASYNC] Erreur lors de la vérification du statut du template pour {message_id}: {e}", exc_info=True)
            print(f"❌ [CHECK-ASYNC] Erreur lors de la vérification du statut du template pour {message_id}: {e}")
        
        # Attendre 5 minutes avant la prochaine vérification
        if attempt < max_attempts - 1:  # Ne pas attendre après le dernier essai
            logger.info(f"⏰ [CHECK-ASYNC] Attente de 5 minutes avant la prochaine vérification pour le message {message_id}")
            print(f"⏰ [CHECK-ASYNC] Attente de 5 minutes avant la prochaine vérification pour le message {message_id}")
            await asyncio.sleep(300)  # 5 minutes (au lieu de 30)
        attempt += 1
    
    if attempt >= max_attempts:
        logger.warning(f"⏰ [CHECK-ASYNC] Timeout: Le template pour le message {message_id} n'a pas été approuvé après 24h")
        print(f"⏰ [CHECK-ASYNC] Timeout: Le template pour le message {message_id} n'a pas été approuvé après 24h")


async def check_and_update_template_status(message_id: str) -> Dict[str, Any]:
    """Vérifie le statut d'un template auprès de Meta et met à jour la base"""
    from app.core.db import supabase
    
    logger.info(f"🔍 [CHECK-STATUS] Vérification du statut Meta pour le message {message_id}")
    print(f"🔍 [CHECK-STATUS] Vérification du statut Meta pour le message {message_id}")
    
    # Récupérer les infos du template en attente avec le compte associé
    # On cherche d'abord les templates PENDING, mais aussi APPROVED au cas où le statut n'a pas été mis à jour
    result = await supabase_execute(
        supabase.table("pending_template_messages")
        .select("*, whatsapp_accounts!inner(waba_id, access_token)")
        .eq("message_id", message_id)
        .in_("template_status", ["PENDING", "APPROVED"])  # Chercher aussi les APPROVED au cas où
        .limit(1)
    )
    
    if not result.data or len(result.data) == 0:
        logger.info(f"⚠️ [CHECK-STATUS] Template non trouvé avec statut PENDING/APPROVED pour le message {message_id}, recherche de tous les statuts...")
        print(f"⚠️ [CHECK-STATUS] Template non trouvé avec statut PENDING/APPROVED pour le message {message_id}, recherche de tous les statuts...")
        # Si pas trouvé, vérifier si le message existe déjà avec un autre statut
        result_all = await supabase_execute(
            supabase.table("pending_template_messages")
            .select("*, whatsapp_accounts!inner(waba_id, access_token)")
            .eq("message_id", message_id)
            .limit(1)
        )
        if result_all.data and len(result_all.data) > 0:
            # Le template existe mais avec un statut différent (probablement REJECTED)
            status = result_all.data[0].get("template_status", "UNKNOWN")
            logger.info(f"ℹ️ [CHECK-STATUS] Template trouvé avec statut {status} pour le message {message_id}")
            print(f"ℹ️ [CHECK-STATUS] Template trouvé avec statut {status} pour le message {message_id}")
            return {"status": status}
        logger.warning(f"❌ [CHECK-STATUS] Aucun template trouvé pour le message {message_id}")
        print(f"❌ [CHECK-STATUS] Aucun template trouvé pour le message {message_id}")
        return {"status": "NOT_FOUND"}
    
    pending = result.data[0]
    template_name = pending.get("template_name", "inconnu")
    logger.info(f"📋 [CHECK-STATUS] Template trouvé: {template_name} (ID Meta: {pending.get('meta_template_id')}) pour le message {message_id}")
    print(f"📋 [CHECK-STATUS] Template trouvé: {template_name} (ID Meta: {pending.get('meta_template_id')}) pour le message {message_id}")
    # Extraire les infos du compte depuis la relation
    account_info = pending.get("whatsapp_accounts", {})
    if isinstance(account_info, list) and len(account_info) > 0:
        account_info = account_info[0]
    elif isinstance(account_info, dict):
        pass  # Déjà un dict
    else:
        account_info = {}
    
    pending["waba_id"] = account_info.get("waba_id")
    pending["access_token"] = account_info.get("access_token")
    
    # Vérifier le statut auprès de Meta
    try:
        # Récupérer tous les templates avec pagination pour trouver le nôtre
        all_templates = []
        after = None
        limit = 100
        
        while True:
            templates_result = await whatsapp_api_service.list_message_templates(
                waba_id=pending["waba_id"],
                access_token=pending["access_token"],
                limit=limit,
                after=after
            )
            
            templates_batch = templates_result.get("data", [])
            if not templates_batch:
                break
            
            all_templates.extend(templates_batch)
            
            # Vérifier s'il y a une page suivante
            paging = templates_result.get("paging", {})
            after = paging.get("cursors", {}).get("after")
            if not after:
                break
        
        # Chercher notre template par ID Meta ou par nom
        template = None
        for t in all_templates:
            if t.get("id") == pending["meta_template_id"]:
                template = t
                break
            elif t.get("name") == pending["template_name"]:
                template = t
                break
        
        if not template:
            logger.warning(f"⚠️ Template {pending['template_name']} (ID: {pending['meta_template_id']}) non trouvé dans la liste Meta")
            return {"status": "PENDING"}  # Peut-être pas encore synchronisé
        
        status = template.get("status", "PENDING")
        
        # Normaliser le statut Meta vers notre format
        # Meta peut retourner "APPROVED", "PENDING", "REJECTED", etc.
        meta_status_upper = status.upper() if isinstance(status, str) else str(status).upper()
        
        # Mettre à jour dans la base seulement si le statut a changé
        current_status = pending.get("template_status", "PENDING")
        
        logger.info(f"📊 [CHECK-STATUS] Statut Meta: {meta_status_upper}, Statut base: {current_status} pour le message {message_id}")
        print(f"📊 [CHECK-STATUS] Statut Meta: {meta_status_upper}, Statut base: {current_status} pour le message {message_id}")
        
        if meta_status_upper == "APPROVED" and current_status != "APPROVED":
            await supabase_execute(
                supabase.table("pending_template_messages")
                .update({"template_status": "APPROVED"})
                .eq("message_id", message_id)
            )
            logger.info(f"✅ [CHECK-STATUS] Template {pending['template_name']} approuvé par Meta (statut mis à jour) pour le message {message_id}")
            print(f"✅ [CHECK-STATUS] Template {pending['template_name']} approuvé par Meta (statut mis à jour) pour le message {message_id}")
        elif meta_status_upper == "REJECTED" and current_status != "REJECTED":
            reason = template.get("reason", "Rejeté par Meta")
            await supabase_execute(
                supabase.table("pending_template_messages")
                .update({"template_status": "REJECTED", "rejection_reason": reason})
                .eq("message_id", message_id)
            )
            logger.warning(f"❌ [CHECK-STATUS] Template {pending['template_name']} rejeté par Meta: {reason} pour le message {message_id}")
            print(f"❌ [CHECK-STATUS] Template {pending['template_name']} rejeté par Meta: {reason} pour le message {message_id}")
        elif meta_status_upper == "APPROVED" and current_status == "APPROVED":
            logger.info(f"ℹ️ [CHECK-STATUS] Template {pending['template_name']} déjà marqué comme approuvé pour le message {message_id}")
            print(f"ℹ️ [CHECK-STATUS] Template {pending['template_name']} déjà marqué comme approuvé pour le message {message_id}")
        
        return {"status": meta_status_upper, "rejection_reason": template.get("reason")}
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la vérification du statut du template: {e}", exc_info=True)
        return {"status": "PENDING"}


async def cleanup_read_auto_templates():
    """Nettoie les templates auto-créés pour les messages déjà lus"""
    from app.core.db import supabase
    
    try:
        # Récupérer tous les templates auto-créés associés à des messages lus
        # Note: Supabase ne supporte pas directement LIKE dans le query builder,
        # on va filtrer après récupération ou utiliser une fonction RPC
        result = await supabase_execute(
            supabase.table("pending_template_messages")
            .select("message_id, template_name, messages!inner(status)")
            .eq("messages.status", "read")
            .limit(1000)  # Limite pour éviter de charger trop de données
        )
        
        if not result.data or len(result.data) == 0:
            return
        
        # Filtrer les templates auto-créés (commencent par "auto_")
        auto_templates = [
            row for row in result.data 
            if row.get("template_name", "").startswith("auto_")
        ]
        
        if not auto_templates:
            return
        
        logger.info(f"🧹 Nettoyage de {len(auto_templates)} templates auto-créés pour messages déjà lus")
        
        for row in auto_templates:
            try:
                await delete_auto_template_for_message(row["message_id"])
            except Exception as e:
                logger.warning(f"⚠️ Erreur lors du nettoyage du template pour message {row['message_id']}: {e}")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du nettoyage des templates auto-créés: {e}", exc_info=True)


async def send_pending_template(message_id: str):
    """Envoie un template une fois qu'il est approuvé (message individuel ou campagne broadcast)"""
    from app.core.db import supabase
    
    logger.info(f"📤 [SEND-TEMPLATE] Début de l'envoi du template pour le message {message_id}")
    print(f"📤 [SEND-TEMPLATE] Début de l'envoi du template pour le message {message_id}")
    
    result = await supabase_execute(
        supabase.table("pending_template_messages")
        .select("*, conversations!inner(client_number), whatsapp_accounts!inner(phone_number_id, access_token)")
        .eq("message_id", message_id)
        .eq("template_status", "APPROVED")
        .limit(1)
    )
    
    if not result.data or len(result.data) == 0:
        logger.warning(f"⚠️ [SEND-TEMPLATE] Aucun template approuvé trouvé pour le message {message_id}")
        print(f"⚠️ [SEND-TEMPLATE] Aucun template approuvé trouvé pour le message {message_id}")
        return
    
    pending = result.data[0]
    template_name = pending.get("template_name", "inconnu")
    campaign_id = pending.get("campaign_id")
    
    # Extraire les infos des relations
    conversation_info = pending.get("conversations", {})
    if isinstance(conversation_info, list) and len(conversation_info) > 0:
        conversation_info = conversation_info[0]
    
    account_info = pending.get("whatsapp_accounts", {})
    if isinstance(account_info, list) and len(account_info) > 0:
        account_info = account_info[0]
    
    phone_number_id = account_info.get("phone_number_id")
    access_token = account_info.get("access_token")
    
    if not phone_number_id or not access_token:
        logger.error(f"❌ WhatsApp non configuré pour le compte {pending['account_id']}")
        if campaign_id:
            # Marquer tous les destinataires de la campagne comme échoués
            await _mark_campaign_as_failed(campaign_id, "WhatsApp non configuré")
        else:
            await mark_message_as_failed(message_id, "WhatsApp non configuré")
        return
    
    # Si c'est une campagne broadcast, envoyer à tous les destinataires
    if campaign_id:
        logger.info(f"📧 [SEND-TEMPLATE] Template approuvé pour campagne broadcast {campaign_id}, envoi à tous les destinataires")
        print(f"📧 [SEND-TEMPLATE] Template approuvé pour campagne broadcast {campaign_id}, envoi à tous les destinataires")
        await _send_broadcast_template(campaign_id, template_name, phone_number_id, access_token, pending.get("text_content"))
        return
    
    # Sinon, envoi normal pour un message individuel
    logger.info(f"📋 [SEND-TEMPLATE] Template à envoyer: {template_name} pour le message {message_id}")
    print(f"📋 [SEND-TEMPLATE] Template à envoyer: {template_name} pour le message {message_id}")
    
    to_number = conversation_info.get("client_number")
    
    try:
        logger.info(f"📤 [SEND-TEMPLATE] Envoi du template '{template_name}' vers {to_number} pour le message {message_id}")
        print(f"📤 [SEND-TEMPLATE] Envoi du template '{template_name}' vers {to_number} pour le message {message_id}")
        
        # Utiliser la fonction existante pour envoyer le template
        response = await whatsapp_api_service.send_template_message(
            phone_number_id=phone_number_id,
            access_token=access_token,
            to=to_number,
            template_name=template_name,
            language_code="fr",
            components=None  # Pas de variables pour les templates auto-créés
        )
        
        logger.info(f"📥 [SEND-TEMPLATE] Réponse Meta pour le message {message_id}: {response}")
        print(f"📥 [SEND-TEMPLATE] Réponse Meta pour le message {message_id}: {response}")
        
        # Mettre à jour le message avec le wa_message_id si disponible
        wa_message_id = response.get("messages", [{}])[0].get("id") if response.get("messages") else None
        if wa_message_id:
            logger.info(f"✅ [SEND-TEMPLATE] Message envoyé avec succès! wa_message_id={wa_message_id} pour le message {message_id}")
            print(f"✅ [SEND-TEMPLATE] Message envoyé avec succès! wa_message_id={wa_message_id} pour le message {message_id}")
            await supabase_execute(
                supabase.table("messages")
                .update({"wa_message_id": wa_message_id, "status": "sent"})
                .eq("id", message_id)
            )
        else:
            logger.warning(f"⚠️ [SEND-TEMPLATE] Pas de wa_message_id dans la réponse pour le message {message_id}, mais on marque comme envoyé")
            print(f"⚠️ [SEND-TEMPLATE] Pas de wa_message_id dans la réponse pour le message {message_id}, mais on marque comme envoyé")
            await supabase_execute(
                supabase.table("messages")
                .update({"status": "sent"})
                .eq("id", message_id)
            )
        
        logger.info(f"✅ [SEND-TEMPLATE] Template '{template_name}' envoyé avec succès et message {message_id} mis à jour")
        print(f"✅ [SEND-TEMPLATE] Template '{template_name}' envoyé avec succès et message {message_id} mis à jour")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'envoi du template pour le message {message_id}: {e}", exc_info=True)
        error_msg = str(e)
        if hasattr(e, 'response') and hasattr(e.response, 'json'):
            try:
                error_data = e.response.json()
                if 'error' in error_data:
                    error_msg = error_data['error'].get('message', error_msg)
            except:
                pass
        await mark_message_as_failed(message_id, f"Erreur lors de l'envoi: {error_msg}")


async def _send_broadcast_template(
    campaign_id: str,
    template_name: str,
    phone_number_id: str,
    access_token: str,
    text_content: str
):
    """Envoie un template approuvé à tous les destinataires d'une campagne broadcast"""
    from app.core.db import supabase
    from app.services.broadcast_service import get_group_recipients, update_recipient_stat, update_campaign_counters
    
    logger.info(f"📧 [BROADCAST-TEMPLATE] Envoi du template '{template_name}' à tous les destinataires de la campagne {campaign_id}")
    print(f"📧 [BROADCAST-TEMPLATE] Envoi du template '{template_name}' à tous les destinataires de la campagne {campaign_id}")
    
    # Récupérer la campagne
    campaign_result = await supabase_execute(
        supabase.table("broadcast_campaigns")
        .select("group_id, account_id")
        .eq("id", campaign_id)
        .single()
    )
    
    if not campaign_result.data:
        logger.error(f"❌ [BROADCAST-TEMPLATE] Campagne {campaign_id} non trouvée")
        return
    
    campaign = campaign_result.data
    group_id = campaign["group_id"]
    account_id = campaign["account_id"]
    
    # Récupérer tous les destinataires
    recipients = await get_group_recipients(group_id)
    
    if not recipients:
        logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Aucun destinataire pour la campagne {campaign_id}")
        return
    
    # Récupérer toutes les stats de la campagne
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("id, phone_number, message_id")
        .eq("campaign_id", campaign_id)
    )
    
    if not stats_result.data:
        logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Aucune stat trouvée pour la campagne {campaign_id}")
        return
    
    stats = {stat["phone_number"]: stat for stat in stats_result.data}
    
    # Envoyer le template à chaque destinataire
    sent_count = 0
    failed_count = 0
    
    for recipient in recipients:
        phone_number = recipient["phone_number"]
        stat = stats.get(phone_number)
        
        if not stat:
            logger.warning(f"⚠️ [BROADCAST-TEMPLATE] Pas de stat trouvée pour {phone_number}")
            continue
        
        try:
            # Envoyer le template
            response = await whatsapp_api_service.send_template_message(
                phone_number_id=phone_number_id,
                access_token=access_token,
                to=phone_number,
                template_name=template_name,
                language_code="fr",
                components=None  # Pas de variables pour les templates auto-créés
            )
            
            wa_message_id = response.get("messages", [{}])[0].get("id") if response.get("messages") else None
            timestamp_iso = datetime.now(timezone.utc).isoformat()
            
            # Mettre à jour le message "fake" avec le vrai wa_message_id
            if stat.get("message_id"):
                await supabase_execute(
                    supabase.table("messages")
                    .update({
                        "wa_message_id": wa_message_id,
                        "status": "sent",
                        "timestamp": timestamp_iso
                    })
                    .eq("id", stat["message_id"])
                )
            
            # Mettre à jour la stat
            await update_recipient_stat(stat["id"], {
                "sent_at": timestamp_iso,
            })
            
            sent_count += 1
            logger.info(f"✅ [BROADCAST-TEMPLATE] Template envoyé à {phone_number} (wa_message_id: {wa_message_id})")
            
        except Exception as e:
            logger.error(f"❌ [BROADCAST-TEMPLATE] Erreur lors de l'envoi à {phone_number}: {e}", exc_info=True)
            failed_count += 1
            
            # Marquer la stat comme échouée
            await update_recipient_stat(stat["id"], {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": str(e)
            })
    
    # Mettre à jour les compteurs de la campagne
    await update_campaign_counters(campaign_id)
    
    logger.info(f"✅ [BROADCAST-TEMPLATE] Campagne {campaign_id} terminée: {sent_count} envoyés, {failed_count} échoués")
    print(f"✅ [BROADCAST-TEMPLATE] Campagne {campaign_id} terminée: {sent_count} envoyés, {failed_count} échoués")


async def _mark_campaign_as_failed(campaign_id: str, error_message: str):
    """Marque tous les destinataires d'une campagne comme échoués"""
    from app.core.db import supabase
    from app.services.broadcast_service import update_recipient_stat, update_campaign_counters
    
    stats_result = await supabase_execute(
        supabase.table("broadcast_recipient_stats")
        .select("id")
        .eq("campaign_id", campaign_id)
    )
    
    if stats_result.data:
        for stat in stats_result.data:
            await update_recipient_stat(stat["id"], {
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": error_message
            })
        
        await update_campaign_counters(campaign_id)


async def mark_message_as_failed(message_id: str, error_message: str):
    """Marque un message comme échoué dans la base"""
    from app.core.db import supabase
    await supabase_execute(
        supabase.table("messages")
        .update({"status": "failed", "error_message": error_message})
        .eq("id", message_id)
    )
    logger.info(f"❌ Message {message_id} marqué comme échoué: {error_message}")


async def delete_auto_template_for_message(message_id: str):
    """Supprime le template auto-créé associé à un message une fois qu'il est lu"""
    from app.core.db import supabase
    
    try:
        # Récupérer les infos du template en attente
        result = await supabase_execute(
            supabase.table("pending_template_messages")
            .select("*, whatsapp_accounts!inner(waba_id, access_token)")
            .eq("message_id", message_id)
            .limit(1)
        )
        
        if not result.data or len(result.data) == 0:
            # Pas de template auto-créé pour ce message
            return
        
        pending = result.data[0]
        # Extraire les infos du compte depuis la relation
        account_info = pending.get("whatsapp_accounts", {})
        if isinstance(account_info, list) and len(account_info) > 0:
            account_info = account_info[0]
        elif isinstance(account_info, dict):
            pass  # Déjà un dict
        else:
            account_info = {}
        
        pending["waba_id"] = account_info.get("waba_id")
        pending["access_token"] = account_info.get("access_token")
        template_name = pending["template_name"]
        
        # Vérifier que c'est bien un template auto-créé (commence par "auto_")
        if not template_name.startswith("auto_"):
            logger.info(f"ℹ️ Template {template_name} n'est pas un template auto-créé, pas de suppression")
            return
        
        waba_id = pending["waba_id"]
        access_token = pending["access_token"]
        
        if not waba_id or not access_token:
            logger.warning(f"⚠️ Impossible de supprimer le template {template_name}: waba_id ou access_token manquant")
            return
        
        logger.info(f"🗑️ Suppression du template auto-créé '{template_name}' pour le message {message_id}")
        
        # Supprimer le template via l'API Meta
        try:
            await whatsapp_api_service.delete_message_template(
                waba_id=waba_id,
                access_token=access_token,
                name=template_name
            )
            logger.info(f"✅ Template '{template_name}' supprimé avec succès de Meta")
        except Exception as e:
            logger.warning(f"⚠️ Erreur lors de la suppression du template '{template_name}' depuis Meta: {e}")
            # Continuer quand même pour supprimer l'entrée en base
        
        # Supprimer l'entrée dans pending_template_messages
        from app.core.db import supabase
        await supabase_execute(
            supabase.table("pending_template_messages")
            .delete()
            .eq("message_id", message_id)
        )
        
        logger.info(f"✅ Entrée pending_template_messages supprimée pour le message {message_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la suppression du template auto-créé pour le message {message_id}: {e}", exc_info=True)

