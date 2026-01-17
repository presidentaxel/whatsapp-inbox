# Prévention du Spam des Templates WhatsApp

## Problème

Quand les utilisateurs envoient plusieurs fois le même message à beaucoup de personnes, le système créait un nouveau template WhatsApp pour chaque message. WhatsApp détecte cela comme du spam et commence à refuser les templates, même s'ils sont légitimes.

## Solution Implémentée

Un système de **déduplication intelligente des templates** qui :

1. **Détecte les messages identiques/similaires** avant de créer un nouveau template
2. **Réutilise les templates existants** quand ils sont déjà approuvés par Meta
3. **Prévient le spam** en limitant le nombre de templates identiques créés dans une période donnée
4. **Stocke un hash normalisé** pour une comparaison rapide

## Fonctionnement

### Détection de Similarité

Le système calcule un **hash MD5** du texte normalisé (minuscules, espaces multiples supprimés) pour identifier les messages identiques :

- **Body text** : Comparé et hashé
- **Header text** : Inclus dans le hash si présent
- **Footer text** : Inclus dans le hash si présent

### Réutilisation des Templates

Avant de créer un nouveau template, le système :

1. Cherche dans les templates des **90 derniers jours** pour ce compte
2. Compare le hash du nouveau message avec les templates existants
3. Si un template **APPROVED** est trouvé : **réutilise-le immédiatement**
4. Si un template **PENDING** est trouvé : **réutilise-le** et attend l'approbation
5. Sinon : **crée un nouveau template** normalement

### Détection de Risque de Spam

Le système vérifie s'il y a trop de messages identiques récents :

- **Fenêtre** : 60 minutes (1 heure)
- **Limite** : 10 messages identiques maximum
- **Action** : Log un avertissement (ne bloque pas l'envoi, mais alerte)

## Fichiers Créés/Modifiés

### Nouveau Service
- `backend/app/services/template_deduplication.py` : Service principal de déduplication

### Migration SQL
- `supabase/migrations/026_template_deduplication.sql` : Ajoute les colonnes nécessaires :
  - `template_hash` : Hash MD5 du template normalisé
  - `reused_from_template` : Référence au template original si réutilisé
  - `campaign_id` : Support des campagnes broadcast (si manquant)

### Modifications
- `backend/app/api/routes_messages.py` : Utilise `find_or_create_template` au lieu de `create_and_queue_template`
- `backend/app/services/broadcast_service.py` : Utilise `find_or_create_template` pour les broadcasts
- `backend/app/services/pending_template_service.py` : Stocke le hash lors de la création

## Utilisation

### Automatique

Le système fonctionne automatiquement. Quand un message est envoyé :

```python
# Avant (créait toujours un nouveau template)
template_result = await create_and_queue_template(...)

# Après (cherche d'abord un template existant)
template_result = await find_or_create_template(...)
```

### Réponse

La réponse inclut maintenant un champ `reused` pour indiquer si le template a été réutilisé :

```json
{
  "success": true,
  "template_name": "auto_message_abc123",
  "meta_template_id": "...",
  "reused": true,  // ✅ Template réutilisé
  "original_template_message_id": "..."
}
```

## Avantages

✅ **Prévient le spam** : Moins de templates identiques créés  
✅ **Plus rapide** : Réutilisation immédiate des templates approuvés  
✅ **Économique** : Moins de requêtes à l'API Meta  
✅ **Compatible** : Fonctionne avec les messages normaux et les broadcasts  
✅ **Transparent** : Aucun changement visible pour l'utilisateur final

## Logs

Le système log des informations utiles :

```
🔍 [DEDUP] Recherche de template existant pour hash: abc123...
✅ [DEDUP] Template similaire trouvé: auto_message_xyz (status: APPROVED)
♻️ [FIND-OR-CREATE] Réutilisation du template existant 'auto_message_xyz' pour le message 123
⚠️ [DEDUP] Risque de spam détecté: 15 messages identiques dans les 60 dernières minutes
```

## Configuration

### Paramètres de Détection

Dans `template_deduplication.py` :

- `max_age_days` : Période de recherche (défaut: 90 jours)
- `time_window_minutes` : Fenêtre pour détecter le spam (défaut: 60 minutes)
- `max_identical_messages` : Limite avant alerte (défaut: 10 messages)

### Ajustement

Si vous voulez être plus ou moins strict :

```python
# Plus strict (recherche sur 30 jours seulement)
existing_template = await TemplateDeduplication.find_existing_template(
    ..., max_age_days=30
)

# Moins strict (20 messages identiques autorisés)
is_spam_risk, details = await TemplateDeduplication.check_spam_risk(
    ..., max_identical_messages=20
)
```

## Application de la Migration

Pour activer cette fonctionnalité :

```bash
# Appliquer la migration SQL
supabase migration up 026_template_deduplication.sql

# Redémarrer le backend
```

## Résultat

Avant : Envoyer 50 fois le même message = 50 templates créés → Risque de rejet par Meta  
Après : Envoyer 50 fois le même message = 1 template créé + 49 réutilisations → ✅ Pas de spam

