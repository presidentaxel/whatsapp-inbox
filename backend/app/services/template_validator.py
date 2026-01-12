"""
Service de validation des messages selon les règles Meta WhatsApp
"""
import re
from typing import Dict, List, Tuple


class TemplateValidator:
    """Valide les messages selon les règles Meta WhatsApp"""
    
    # Limites Meta
    MAX_BODY_LENGTH = 1024
    MAX_HEADER_LENGTH = 60
    MAX_FOOTER_LENGTH = 60
    MAX_TEMPLATE_NAME_LENGTH = 512
    
    # Caractères interdits dans les noms de templates
    INVALID_NAME_CHARS = re.compile(r'[^a-zA-Z0-9_\-]')
    
    # Mots interdits (exemples - à compléter selon vos besoins)
    FORBIDDEN_WORDS = [
        'spam', 'scam', 'fraud', 'phishing', 'virus', 'malware',
        # Ajoutez d'autres selon vos besoins
    ]
    
    @staticmethod
    def validate_text(text: str) -> Tuple[bool, List[str]]:
        """Valide un texte selon les règles Meta"""
        errors = []
        
        if not text or not text.strip():
            errors.append("Le message ne peut pas être vide")
            return False, errors
        
        text_length = len(text)
        if text_length > TemplateValidator.MAX_BODY_LENGTH:
            errors.append(
                f"Le message ne peut pas dépasser {TemplateValidator.MAX_BODY_LENGTH} caractères "
                f"(actuellement: {text_length})"
            )
        
        # Vérifier les mots interdits
        text_lower = text.lower()
        for word in TemplateValidator.FORBIDDEN_WORDS:
            if word in text_lower:
                errors.append(f"Le message contient un mot interdit: {word}")
        
        # Vérifier les URLs suspectes (trop d'URLs)
        url_pattern = re.compile(r'https?://[^\s]+')
        urls = url_pattern.findall(text)
        if len(urls) > 3:  # Trop d'URLs
            errors.append(f"Le message contient trop d'URLs (maximum 3, trouvé: {len(urls)})")
        
        # Vérifier les caractères spéciaux problématiques
        # Meta n'aime pas certains caractères dans les templates
        problematic_chars = ['\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07']
        for char in problematic_chars:
            if char in text:
                errors.append("Le message contient des caractères non autorisés")
                break
        
        return len(errors) == 0, errors
    
    @staticmethod
    def generate_template_name(text: str, conversation_id: str) -> str:
        """Génère un nom de template unique basé sur le texte"""
        import time
        import hashlib
        
        # Meta a des règles STRICTES pour les noms de templates:
        # - Maximum 512 caractères
        # - UNIQUEMENT lettres minuscules, chiffres, underscores et tirets
        # - Pas de majuscules !
        # - Pas d'espaces
        # - Doit commencer par une lettre ou un chiffre (pas un underscore ou tiret)
        
        # Prendre les 30 premiers caractères et convertir en minuscules
        clean_text = re.sub(r'[^a-zA-Z0-9]', '_', text[:30]).lower()
        # S'assurer que ça commence par une lettre ou un chiffre
        if clean_text and clean_text[0] in ['_', '-']:
            clean_text = 't' + clean_text[1:]
        if not clean_text:
            clean_text = "template"
        
        # Ajouter un hash court pour garantir l'unicité
        hash_suffix = hashlib.md5(f"{conversation_id}{time.time()}".encode()).hexdigest()[:8]
        timestamp = int(time.time()) % 1000000  # Limiter le timestamp pour éviter des noms trop longs
        
        template_name = f"auto_{clean_text}_{hash_suffix}_{timestamp}"
        
        # Limiter la longueur (Meta max 512, mais on garde une marge)
        if len(template_name) > 100:
            # Si trop long, raccourcir le clean_text
            max_clean_length = 100 - len(f"auto_{hash_suffix}_{timestamp}") - 3  # -3 pour les underscores
            if max_clean_length > 0:
                clean_text = clean_text[:max_clean_length]
                template_name = f"auto_{clean_text}_{hash_suffix}_{timestamp}"
            else:
                # Si même ça ne suffit pas, utiliser juste le hash et timestamp
                template_name = f"auto_{hash_suffix}_{timestamp}"
        
        # S'assurer que le nom respecte les règles Meta (uniquement minuscules, chiffres, underscores)
        template_name = re.sub(r'[^a-z0-9_]', '_', template_name.lower())
        if template_name[0] in ['_', '-']:
            template_name = 't' + template_name[1:]
        
        return template_name
    
    @staticmethod
    def sanitize_for_template(text: str) -> str:
        """Nettoie le texte pour qu'il soit compatible avec les templates Meta"""
        # Remplacer les retours à la ligne multiples par des espaces simples
        text = re.sub(r'\n+', ' ', text)
        # Remplacer les espaces multiples par un seul espace
        text = re.sub(r'\s+', ' ', text)
        # Limiter la longueur
        if len(text) > TemplateValidator.MAX_BODY_LENGTH:
            text = text[:TemplateValidator.MAX_BODY_LENGTH-3] + "..."
        return text.strip()
    
    @staticmethod
    def validate_template_name(name: str) -> Tuple[bool, List[str]]:
        """Valide un nom de template selon les règles Meta"""
        errors = []
        
        if not name or not name.strip():
            errors.append("Le nom du template ne peut pas être vide")
            return False, errors
        
        if len(name) > TemplateValidator.MAX_TEMPLATE_NAME_LENGTH:
            errors.append(
                f"Le nom du template ne peut pas dépasser {TemplateValidator.MAX_TEMPLATE_NAME_LENGTH} caractères"
            )
        
        # Vérifier les caractères valides (lettres, chiffres, underscore, tiret)
        if TemplateValidator.INVALID_NAME_CHARS.search(name):
            errors.append(
                "Le nom du template ne peut contenir que des lettres, chiffres, underscores et tirets"
            )
        
        return len(errors) == 0, errors

