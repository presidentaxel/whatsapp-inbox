# Fix Bug : Bot continue à répondre en mode humain

## 🐛 Problème identifié

Lorsqu'un utilisateur désactive le mode IA via le bouton prévu à cet effet pour passer en mode humain, le bot continue à envoyer des réponses automatiques pendant **jusqu'à 60 secondes** :
- "Je ne peux pas lire ce type de contenu, peux-tu me l'écrire ?"
- "Je me renseigne auprès d'un collègue et je reviens vers vous au plus vite."

## 🔍 Cause du bug

Le problème vient du **cache non invalidé** :

1. La fonction `get_conversation_by_id()` dans `conversation_service.py` est mise en cache avec un TTL de **60 secondes**
2. Quand l'utilisateur clique sur le bouton pour désactiver le bot, la fonction `set_conversation_bot_mode()` met à jour la base de données (`bot_enabled = false`)
3. **MAIS** le cache n'était pas invalidé, donc la version en cache avait encore `bot_enabled = true`
4. Quand un nouveau message arrive dans les 60 secondes suivantes, le webhook récupère la version **en cache** de la conversation
5. Le bot voit `bot_enabled = true` (valeur en cache) et continue à répondre automatiquement

## ✅ Solution implémentée

Ajout de l'invalidation du cache dans **toutes les fonctions** qui modifient les conversations :

### 1. `conversation_service.py`
- ✅ `set_conversation_bot_mode()` - **CRITIQUE** pour le bug
- ✅ `mark_conversation_read()`
- ✅ `set_conversation_favorite()`

### 2. `message_service.py`
- ✅ `_update_conversation_timestamp()`
- ✅ `_increment_unread_count()`
- ✅ Mise à jour de `bot_last_reply_at` dans `_maybe_trigger_bot_reply()`

## 📝 Changements techniques

### Import ajouté
```python
from app.core.cache import cached, invalidate_cache_pattern
```

### Pattern d'invalidation
```python
await invalidate_cache_pattern(f"conversation:{conversation_id}")
```

Cette ligne invalide immédiatement le cache Redis pour la conversation modifiée, forçant le prochain appel à `get_conversation_by_id()` à relire depuis la base de données.

## 🎯 Résultat attendu

Désormais, quand un utilisateur désactive le mode IA :
1. ✅ Le cache est invalidé **immédiatement**
2. ✅ Le prochain message entrant voit `bot_enabled = false`
3. ✅ Le bot **ne répond plus du tout**
4. ✅ Seul l'humain peut répondre

## 🧪 Test manuel recommandé

1. Ouvrir une conversation avec le bot activé
2. Envoyer un message → le bot répond ✅
3. Cliquer sur le bouton pour désactiver le bot
4. **Immédiatement** envoyer un autre message
5. Vérifier que le bot **ne répond pas** ✅

Avant le fix, à l'étape 5, le bot répondait encore pendant jusqu'à 60 secondes.

## 📊 Impact sur les performances

L'invalidation du cache a un impact minimal :
- ✅ Redis est très rapide (< 1ms pour invalider une clé)
- ✅ Les conversations ne changent pas si souvent
- ✅ Le cache reste utile pour les lectures fréquentes
- ✅ Garantit la **cohérence** des données

## 🔗 Fichiers modifiés

- `backend/app/services/conversation_service.py`
- `backend/app/services/message_service.py`

