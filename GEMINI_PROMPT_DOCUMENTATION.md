# 📋 Documentation Complète du Prompt Gemini

Ce document explique **exactement** ce qui est envoyé à l'API Gemini pour générer les réponses automatiques.

## 🎯 Structure du Payload

Le payload envoyé à Gemini a cette structure :

```json
{
  "system_instruction": {
    "role": "system",
    "parts": [
      {
        "text": "[INSTRUCTION DE BASE]\n\nContexte entreprise:\n[KNOWLEDGE_TEXT]"
      }
    ]
  },
  "contents": [
    {"role": "user", "parts": [{"text": "Message 1"}]},
    {"role": "model", "parts": [{"text": "Réponse 1"}]},
    {"role": "user", "parts": [{"text": "Message 2"}]},
    ...
  ],
  "generationConfig": {
    "temperature": 0.4,
    "maxOutputTokens": 250
  }
}
```

## 📝 1. System Instruction (Instructions de Base)

**Ligne 243-252 de `bot_service.py`**

```python
instruction = (
    "Tu es un assistant WhatsApp francophone pour l'entreprise décrite ci-dessous. "
    "Réponds uniquement en texte. "
    "Si un utilisateur envoie une image, vidéo, audio ou tout contenu non textuel, réponds : "
    "\"Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?\" "
    "N'invente jamais de données. "
    "Si une information manque dans le contexte, indique simplement que tu dois la vérifier et pose des questions pour avancer. "
    "N'interromps pas la conversation tant que tu peux guider l'utilisateur ou collecter des détails utiles. "
    "Ne promets jamais de tarifs, délais, disponibilités ou réservations sans confirmation explicite dans le contexte."
)
```

## 🏢 2. Knowledge Text (Contexte Entreprise)

**Fonction `_build_knowledge_text()` - Lignes 316-339**

Le contexte entreprise est construit dans cet ordre :

### A. Template Config (si présent)
**Fonction `_render_template_sections()` - Lignes 436-561**

Le template est rendu avec ces sections (dans l'ordre) :

1. **## SYSTEM RULES**
   - Rôle
   - Mission
   - Langue par défaut
   - Ton attendu
   - Style de réponse
   - Priorité des sources
   - Politique de réponse
   - Règles de sécurité

2. **## INFOS ENTREPRISE**
   - Nom entreprise
   - Adresse
   - Horaires détaillés
   - Zone couverte
   - Rendez-vous
   - Activité principale

3. **## OFFRES / SERVICES**
   - Pour chaque offre :
     - Catégorie
     - Contenu

4. **## CONDITIONS & PROCÉDURES**
   - Zone
   - Paiement / dépôt
   - Engagement
   - Restrictions
   - Documents requis

5. **## PROCÉDURES SIMPLIFIÉES**
   - Pour chaque procédure :
     - Nom
     - Étapes

6. **## FAQ**
   - Pour chaque FAQ :
     - Q: [question]
     - R: [réponse]

7. **## CAS SPÉCIAUX**
   - Pour chaque cas :
     - Si [cas]: [réponse]

8. **## LIENS UTILES**
   - Site
   - Produits
   - Formulaire
   - Autre

9. **## ESCALADE HUMAIN**
   - Procédure
   - Contact
   - Horaires du contact

10. **## RÈGLES SPÉCIALES BOT**
    - Règles spéciales (texte libre)

### B. Informations du Profil (si présentes)
**Lignes 322-336**

- `Nom: {business_name}`
- `Description: {description}`
- `Adresse: {address}`
- `Horaires: {hours}`
- `Informations additionnelles: {knowledge_base}`
- Pour chaque `custom_field` : `{label}: {value}`
- `Prenom/nom du contact: {contact_name}` (si disponible)

### C. Fallback
Si aucune information n'est fournie : `"Aucune information fournie."`

## 💬 3. Contents (Historique de Conversation)

**Lignes 213-235**

L'historique est construit ainsi :

1. **Récupération** : Les 10 derniers messages de la conversation (ordre chronologique)
2. **Formatage** :
   - Messages **inbound** → `role: "user"`
   - Messages **outbound** → `role: "model"`
3. **Filtrage** : Les messages vides sont ignorés
4. **Ajout** : Si le dernier message n'est pas un message utilisateur, le `latest_user_message` est ajouté

**Structure** :
```python
[
  {"role": "user", "parts": [{"text": "Message utilisateur 1"}]},
  {"role": "model", "parts": [{"text": "Réponse bot 1"}]},
  {"role": "user", "parts": [{"text": "Message utilisateur 2"}]},
  ...
]
```

## ⚙️ 4. Generation Config

**Lignes 262-265**

```python
"generationConfig": {
    "temperature": 0.4,        # Créativité (0.0 = déterministe, 1.0 = créatif)
    "maxOutputTokens": 250    # Longueur max de la réponse
}
```

## 📊 Exemple Complet de Payload

Voici un exemple concret de ce qui est envoyé :

```json
{
  "system_instruction": {
    "role": "system",
    "parts": [
      {
        "text": "Tu es un assistant WhatsApp francophone pour l'entreprise décrite ci-dessous. Réponds uniquement en texte. Si un utilisateur envoie une image, vidéo, audio ou tout contenu non textuel, réponds : \"Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?\" N'invente jamais de données. Si une information manque dans le contexte, indique simplement que tu dois la vérifier et pose des questions pour avancer. N'interromps pas la conversation tant que tu peux guider l'utilisateur ou collecter des détails utiles. Ne promets jamais de tarifs, délais, disponibilités ou réservations sans confirmation explicite dans le contexte.\n\nContexte entreprise:\n## SYSTEM RULES\nRôle: Assistant commercial\nMission: Aider les clients à réserver des services\nLangue par défaut: Français\nTon attendu: Professionnel et amical\n\n## INFOS ENTREPRISE\nNom entreprise: Ma Maison du Chauffeur VTC\nAdresse: 123 Rue Example, Paris\nHoraires détaillés: Lun-Ven 9h-18h\nZone couverte: Île-de-France\n\n## OFFRES / SERVICES\n### Catégorie: Transport\nService de VTC disponible 24/7\n\nPrenom/nom du contact: Jean Dupont"
      }
    ]
  },
  "contents": [
    {"role": "user", "parts": [{"text": "Bonjour, je cherche un chauffeur"}]},
    {"role": "model", "parts": [{"text": "Bonjour ! Je peux vous aider à réserver un chauffeur VTC."}]},
    {"role": "user", "parts": [{"text": "Pour demain matin à 8h"}]}
  ],
  "generationConfig": {
    "temperature": 0.4,
    "maxOutputTokens": 250
  }
}
```

## 🔍 Points Importants pour l'Optimisation

### 1. Longueur du Prompt
- **System instruction** : ~500-2000 caractères (selon le template)
- **Knowledge text** : Variable selon les données
- **Contents** : Maximum 10 messages (les plus récents)

### 2. Ordre des Informations
- Les instructions système sont **toujours en premier**
- Le template config est rendu **avant** les infos du profil
- L'historique est dans l'ordre **chronologique** (plus ancien → plus récent)

### 3. Limitations
- `maxOutputTokens: 250` limite les réponses à ~200 mots
- `temperature: 0.4` = plutôt déterministe (peu créatif)
- Seuls les **10 derniers messages** sont inclus

### 4. Filtrage
- Messages vides sont **ignorés**
- Seul le **texte** est envoyé (pas les médias)
- Les messages sont **trimés** (espaces enlevés)

## 🛠️ Comment Optimiser

### Pour Réduire les Tokens
1. **Limiter le template config** : Ne garder que les sections essentielles
2. **Réduire l'historique** : Passer de 10 à 5 messages si nécessaire
3. **Optimiser le knowledge_base** : Éviter les répétitions

### Pour Améliorer les Réponses
1. **Augmenter maxOutputTokens** : De 250 à 500 pour des réponses plus longues
2. **Ajuster temperature** : 0.4 = déterministe, 0.7 = plus naturel
3. **Améliorer les instructions système** : Plus précises et spécifiques
4. **Enrichir le template** : Ajouter plus de contexte dans les sections

### Pour Déboguer
Les logs montrent :
- `Gemini knowledge payload` : Le knowledge_text complet (tronqué à 500 chars)
- `Gemini conversation payload` : Les 8 derniers messages (tronqués à 250 chars)

## 📍 Fichiers Concernés

- **`backend/app/services/bot_service.py`** : Construction du prompt
  - Ligne 243-252 : Instructions système
  - Ligne 254-266 : Payload complet
  - Ligne 316-339 : `_build_knowledge_text()`
  - Ligne 436-561 : `_render_template_sections()`

- **`backend/app/services/message_service.py`** : Appel du bot
  - Ligne 622-638 : Invocation de Gemini

## 🔗 Endpoint API

```
POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent
```

Avec :
- `GEMINI_MODEL` : Défini dans `settings.GEMINI_MODEL` (par défaut `gemini-1.5-flash`)
- Paramètre `key` : `settings.GEMINI_API_KEY`

