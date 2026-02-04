"""
Service pour détecter et réutiliser les templates similaires/identiques
Prévient le spam en réutilisant les templates existants au lieu d'en créer de nouveaux
"""
import hashlib
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Any, Tuple

from app.core.db import supabase, supabase_execute
from app.core.pg import execute as pg_execute, fetch_all, fetch_one, get_pool
from app.services.account_service import get_account_by_id

logger = logging.getLogger(__name__)


class TemplateDeduplication:
    """Gère la déduplication des templates pour éviter le spam"""
    
    @staticmethod
    def normalize_text_for_hash(text: str) -> str:
        """Normalise un texte pour créer un hash stable"""
        if not text:
            return ""
        
        # Convertir en minuscules
        text = text.lower().strip()
        
        # Supprimer les espaces multiples
        text = re.sub(r'\s+', ' ', text)
        
        # Supprimer la ponctuation de fin (optionnel, pour détecter les variantes)
        # text = re.sub(r'[.!?]+$', '', text)
        
        return text
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """Calcule un hash MD5 du texte normalisé"""
        normalized = TemplateDeduplication.normalize_text_for_hash(text)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    @staticmethod
    def compute_template_hash(
        body_text: str,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> str:
        """Calcule un hash unique pour un template (header + body + footer)"""
        # Combiner tous les textes
        parts = []
        if header_text:
            parts.append(f"header:{TemplateDeduplication.normalize_text_for_hash(header_text)}")
        parts.append(f"body:{TemplateDeduplication.normalize_text_for_hash(body_text)}")
        if footer_text:
            parts.append(f"footer:{TemplateDeduplication.normalize_text_for_hash(footer_text)}")
        
        combined = "|".join(parts)
        return hashlib.md5(combined.encode('utf-8')).hexdigest()
    
    @staticmethod
    async def find_existing_template(
        account_id: str,
        body_text: str,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        max_age_days: int = 90  # Chercher dans les templates des 90 derniers jours
    ) -> Optional[Dict[str, Any]]:
        """Cherche un template existant similaire/identique pour ce compte
        
        Args:
            account_id: ID du compte WhatsApp
            body_text: Texte du body
            header_text: Texte du header (optionnel)
            footer_text: Texte du footer (optionnel)
            max_age_days: Nombre de jours max pour chercher dans les anciens templates
        
        Returns:
            Dict avec les infos du template existant si trouvé, None sinon
        """
        # Calculer le hash du template
        template_hash = TemplateDeduplication.compute_template_hash(
            body_text, header_text, footer_text
        )
        
        logger.info(f"🔍 [DEDUP] Recherche de template existant pour hash: {template_hash[:16]}...")
        
        # Date limite (templates créés dans les X derniers jours)
        date_limit_dt = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        date_limit_iso = date_limit_dt.isoformat()
        
        # Chercher dans la base de données
        # On cherche par hash du texte normalisé
        # On stocke le hash normalisé dans une colonne dédiée si elle existe,
        # sinon on cherche par comparaison du texte normalisé
        
        try:
            # Option 1: Si on a une colonne template_hash, l'utiliser directement
            # Pour l'instant, on va chercher par comparaison du texte normalisé
            
            # Normaliser les textes pour comparaison
            normalized_body = TemplateDeduplication.normalize_text_for_hash(body_text)
            normalized_header = TemplateDeduplication.normalize_text_for_hash(header_text) if header_text else None
            normalized_footer = TemplateDeduplication.normalize_text_for_hash(footer_text) if footer_text else None
            
            rows = None
            if get_pool():
                rows = await fetch_all(
                    """
                    SELECT p.id, p.message_id, p.conversation_id, p.account_id, p.template_name, p.text_content,
                           p.meta_template_id, p.template_status, p.template_hash, p.created_at
                    FROM pending_template_messages p
                    WHERE p.account_id = $1::uuid AND p.created_at >= ($2::text)::timestamptz
                      AND p.template_status IN ('APPROVED', 'PENDING')
                    """,
                    account_id, date_limit_iso,
                )
            else:
                query = supabase.table("pending_template_messages")\
                    .select("*, whatsapp_accounts!inner(id, waba_id, access_token)")\
                    .eq("account_id", account_id)\
                    .gte("created_at", date_limit_iso)\
                    .in_("template_status", ["APPROVED", "PENDING"])
                result = await supabase_execute(query)
                rows = result.data
            
            if not rows:
                logger.info(f"🔍 [DEDUP] Aucun template trouvé dans la période de {max_age_days} jours")
                return None
            
            # Comparer avec les templates existants
            for pending_template in rows:
                existing_text = pending_template.get("text_content", "")
                existing_normalized = TemplateDeduplication.normalize_text_for_hash(existing_text)
                
                # Comparer les hashes du body
                if normalized_body == existing_normalized:
                    # Vérifier aussi header et footer si fournis
                    # Pour l'instant, on compare juste le body car c'est le plus important
                    logger.info(f"✅ [DEDUP] Template similaire trouvé: {pending_template.get('template_name')} (status: {pending_template.get('template_status')})")
                    
                    return {
                        "template_name": pending_template.get("template_name"),
                        "meta_template_id": pending_template.get("meta_template_id"),
                        "template_status": pending_template.get("template_status"),
                        "message_id": pending_template.get("message_id"),
                        "template_id": pending_template.get("id"),  # ID dans pending_template_messages
                        "created_at": pending_template.get("created_at"),
                        "account_id": account_id
                    }
            
            logger.info(f"🔍 [DEDUP] Aucun template similaire trouvé")
            return None
            
        except Exception as e:
            logger.error(f"❌ [DEDUP] Erreur lors de la recherche de template similaire: {e}", exc_info=True)
            # En cas d'erreur, retourner None pour créer un nouveau template
            return None
    
    @staticmethod
    async def check_spam_risk(
        account_id: str,
        body_text: str,
        time_window_minutes: int = 60,
        max_identical_messages: int = 10
    ) -> Tuple[bool, Dict[str, Any]]:
        """Vérifie s'il y a un risque de spam (trop de messages identiques récents)
        
        Args:
            account_id: ID du compte WhatsApp
            body_text: Texte du message
            time_window_minutes: Fenêtre de temps en minutes
            max_identical_messages: Nombre maximum de messages identiques autorisés
        
        Returns:
            Tuple (is_spam_risk, details) où details contient les infos sur les messages similaires
        """
        normalized_body = TemplateDeduplication.normalize_text_for_hash(body_text)
        
        # Date limite
        time_limit_dt = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        time_limit_iso = time_limit_dt.isoformat()
        
        try:
            rows = None
            if get_pool():
                rows = await fetch_all(
                    """
                    SELECT id, template_name, text_content, created_at, template_status
                    FROM pending_template_messages
                    WHERE account_id = $1::uuid AND created_at >= ($2::text)::timestamptz
                    """,
                    account_id, time_limit_iso,
                )
            else:
                query = supabase.table("pending_template_messages")\
                    .select("id, template_name, text_content, created_at, template_status")\
                    .eq("account_id", account_id)\
                    .gte("created_at", time_limit_iso)
                result = await supabase_execute(query)
                rows = result.data or []
            
            if not rows:
                return False, {"count": 0, "window_minutes": time_window_minutes}
            
            # Compter les messages avec le même texte normalisé
            identical_count = 0
            for template in rows:
                existing_text = template.get("text_content", "")
                existing_normalized = TemplateDeduplication.normalize_text_for_hash(existing_text)
                if normalized_body == existing_normalized:
                    identical_count += 1
            
            is_risk = identical_count >= max_identical_messages
            
            if is_risk:
                logger.warning(
                    f"⚠️ [DEDUP] Risque de spam détecté: {identical_count} messages identiques "
                    f"dans les {time_window_minutes} dernières minutes (max: {max_identical_messages})"
                )
            
            return is_risk, {
                "count": identical_count,
                "max_allowed": max_identical_messages,
                "window_minutes": time_window_minutes,
                "is_risk": is_risk
            }
            
        except Exception as e:
            logger.error(f"❌ [DEDUP] Erreur lors de la vérification du spam: {e}", exc_info=True)
            # En cas d'erreur, ne pas bloquer (false negative acceptable)
            return False, {"count": 0, "window_minutes": time_window_minutes, "error": str(e)}


async def find_or_create_template(
    conversation_id: str,
    account_id: str,
    message_id: str,
    text_content: str,
    campaign_id: Optional[str] = None,
    header_text: Optional[str] = None,
    body_text: Optional[str] = None,
    footer_text: Optional[str] = None,
    buttons: Optional[list] = None,
    created_by_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Cherche un template existant ou crée un nouveau si nécessaire
    
    Cette fonction remplace la création systématique de templates par une logique
    de réutilisation intelligente pour éviter le spam.
    """
    from app.services.pending_template_service import create_and_queue_template
    
    logger.info(f"🔍 [FIND-OR-CREATE] ========== DÉBUT FIND_OR_CREATE ==========")
    logger.info(f"🔍 [FIND-OR-CREATE] conversation_id={conversation_id}")
    logger.info(f"🔍 [FIND-OR-CREATE] account_id={account_id}")
    logger.info(f"🔍 [FIND-OR-CREATE] message_id={message_id}")
    logger.info(f"🔍 [FIND-OR-CREATE] Paramètres reçus:")
    logger.info(f"   - header_text: {repr(header_text)} (type: {type(header_text).__name__})")
    logger.info(f"   - body_text: {repr(body_text)} (type: {type(body_text).__name__})")
    logger.info(f"   - footer_text: {repr(footer_text)} (type: {type(footer_text).__name__})")
    logger.info(f"   - buttons: {repr(buttons)} (type: {type(buttons).__name__})")
    logger.info(f"   - text_content: {repr(text_content[:100] if text_content else None)}")
    
    # Utiliser body_text si fourni, sinon text_content
    actual_body_text = body_text if body_text is not None else text_content
    logger.info(f"🔍 [FIND-OR-CREATE] actual_body_text: {repr(actual_body_text[:100] if actual_body_text else None)}")
    logger.info(f"🔍 [FIND-OR-CREATE] Recherche de template existant pour message {message_id}")
    
    # Vérifier le risque de spam
    is_spam_risk, spam_details = await TemplateDeduplication.check_spam_risk(
        account_id=account_id,
        body_text=actual_body_text,
        time_window_minutes=60,  # 1 heure
        max_identical_messages=10  # Max 10 messages identiques par heure
    )
    
    if is_spam_risk:
        logger.warning(
            f"⚠️ [FIND-OR-CREATE] Risque de spam détecté: {spam_details['count']} messages identiques "
            f"dans les {spam_details['window_minutes']} dernières minutes"
        )
        # On continue quand même, mais on va essayer de réutiliser un template existant
    
    # Chercher un template existant
    existing_template = await TemplateDeduplication.find_existing_template(
        account_id=account_id,
        body_text=actual_body_text,
        header_text=header_text,
        footer_text=footer_text,
        max_age_days=90  # Chercher dans les 90 derniers jours
    )
    
    if existing_template and existing_template.get("template_status") == "APPROVED":
        # Réutiliser le template existant
        template_name = existing_template["template_name"]
        logger.info(
            f"♻️ [FIND-OR-CREATE] Réutilisation du template existant '{template_name}' "
            f"pour le message {message_id} (créé le {existing_template.get('created_at')})"
        )
        
        # Créer une entrée dans pending_template_messages qui référence le template existant
        template_hash = TemplateDeduplication.compute_template_hash(
            actual_body_text, header_text, footer_text
        )
        if get_pool():
            await pg_execute(
                """
                INSERT INTO pending_template_messages
                (message_id, conversation_id, account_id, template_name, text_content, meta_template_id, template_status, reused_from_template, template_hash, campaign_id, created_by_user_id)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8::uuid, $9, $10::uuid, $11::uuid)
                """,
                message_id, conversation_id, account_id, template_name, text_content,
                existing_template.get("meta_template_id"), "APPROVED",
                existing_template.get("template_id"), template_hash, campaign_id, created_by_user_id,
            )
        else:
            from app.core.db import supabase
            pending_template_payload = {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "account_id": account_id,
                "template_name": template_name,
                "text_content": text_content,
                "meta_template_id": existing_template.get("meta_template_id"),
                "template_status": "APPROVED",
                "reused_from_template": existing_template.get("template_id"),
                "template_hash": template_hash,
            }
            if campaign_id:
                pending_template_payload["campaign_id"] = campaign_id
            if created_by_user_id is not None:
                pending_template_payload["created_by_user_id"] = created_by_user_id
            await supabase_execute(
                supabase.table("pending_template_messages").insert(pending_template_payload)
            )
        
        logger.info(
            f"✅ [FIND-OR-CREATE] Template réutilisé '{template_name}' associé au message {message_id}"
        )
        
        # Envoyer immédiatement le template puisqu'il est déjà approuvé
        from app.services.pending_template_service import send_pending_template
        await send_pending_template(message_id)
        
        return {
            "success": True,
            "template_name": template_name,
            "meta_template_id": existing_template.get("meta_template_id"),
            "reused": True,
            "original_template_message_id": existing_template.get("message_id"),
            "original_template_id": existing_template.get("template_id")
        }
    
    elif existing_template and existing_template.get("template_status") == "PENDING":
        # Un template similaire existe mais n'est pas encore approuvé
        template_name = existing_template["template_name"]
        logger.info(
            f"⏳ [FIND-OR-CREATE] Template similaire existe mais en attente '{template_name}' "
            f"pour le message {message_id}"
        )
        
        # On peut soit:
        # 1. Réutiliser le même template en attente (recommandé)
        # 2. Créer un nouveau template (déconseillé si trop de spam)
        
        # Option 1: Réutiliser le template en attente
        template_hash = TemplateDeduplication.compute_template_hash(
            actual_body_text, header_text, footer_text
        )
        if get_pool():
            await pg_execute(
                """
                INSERT INTO pending_template_messages
                (message_id, conversation_id, account_id, template_name, text_content, meta_template_id, template_status, reused_from_template, template_hash, campaign_id, created_by_user_id)
                VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8::uuid, $9, $10::uuid, $11::uuid)
                """,
                message_id, conversation_id, account_id, template_name, text_content,
                existing_template.get("meta_template_id"), "PENDING",
                existing_template.get("template_id"), template_hash, campaign_id, created_by_user_id,
            )
        else:
            from app.core.db import supabase
            pending_template_payload = {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "account_id": account_id,
                "template_name": template_name,
                "text_content": text_content,
                "meta_template_id": existing_template.get("meta_template_id"),
                "template_status": "PENDING",
                "reused_from_template": existing_template.get("template_id"),
                "template_hash": template_hash,
            }
            if campaign_id:
                pending_template_payload["campaign_id"] = campaign_id
            if created_by_user_id is not None:
                pending_template_payload["created_by_user_id"] = created_by_user_id
            await supabase_execute(
                supabase.table("pending_template_messages").insert(pending_template_payload)
            )
        
        logger.info(
            f"✅ [FIND-OR-CREATE] Template en attente réutilisé '{template_name}' associé au message {message_id}"
        )
        
        # Le template sera envoyé automatiquement une fois approuvé via check_template_status_async
        from app.services.pending_template_service import check_template_status_async
        import asyncio
        asyncio.create_task(check_template_status_async(message_id))
        
        return {
            "success": True,
            "template_name": template_name,
            "meta_template_id": existing_template.get("meta_template_id"),
            "reused": True,
            "status": "PENDING",
            "original_template_message_id": existing_template.get("message_id"),
            "original_template_id": existing_template.get("template_id")
        }
    
    else:
        # Aucun template similaire trouvé, créer un nouveau
        logger.info(f"🆕 [FIND-OR-CREATE] Aucun template similaire trouvé, création d'un nouveau pour message {message_id}")
        
        # Si risque de spam élevé, logger un avertissement
        if is_spam_risk:
            logger.warning(
                f"⚠️ [FIND-OR-CREATE] Création d'un nouveau template malgré le risque de spam "
                f"({spam_details['count']} messages similaires récents). "
                f"Considérez de réutiliser des templates existants."
            )
        
        # Créer le template normalement
        logger.info(f"🆕 [FIND-OR-CREATE] Appel à create_and_queue_template avec:")
        logger.info(f"   - header_text: {repr(header_text)}")
        logger.info(f"   - body_text: {repr(body_text)}")
        logger.info(f"   - footer_text: {repr(footer_text)}")
        logger.info(f"   - buttons: {repr(buttons)}")
        logger.info(f"   - text_content: {repr(text_content[:100] if text_content else None)}")
        
        result = await create_and_queue_template(
            conversation_id=conversation_id,
            account_id=account_id,
            message_id=message_id,
            text_content=text_content,
            campaign_id=campaign_id,
            header_text=header_text,
            body_text=body_text,
            footer_text=footer_text,
            buttons=buttons,
            created_by_user_id=created_by_user_id,
        )
        
        logger.info(f"🆕 [FIND-OR-CREATE] Résultat de create_and_queue_template: {result.get('success')}")
        logger.info(f"🆕 [FIND-OR-CREATE] ========== FIN FIND_OR_CREATE ==========")
        
        return result

