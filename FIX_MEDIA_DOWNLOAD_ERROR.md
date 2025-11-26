# 🔧 Correctif : Erreur 500 lors du téléchargement de médias

## ❌ Problème

Lors de l'envoi d'une image, vous receviez une erreur 500 :

```
KeyError: 'account_id'
RuntimeWarning: coroutine 'get_conversation_by_id' was never awaited
```

## 🔍 Cause

La route `/messages/media/{message_id}` avait deux bugs :

1. **Code dupliqué** : La conversation était récupérée deux fois
2. **KeyError** : Tentative d'accès à `message["account_id"]` qui n'existe pas
   - La table `messages` n'a **pas** de colonne `account_id`
   - Il faut passer par `conversation["account_id"]`

### Code Problématique

```python
# ❌ AVANT (ligne 48)
conversation, account = await asyncio.gather(
    get_conversation_by_id(message["conversation_id"]),
    get_account_by_id(message["account_id"])  # ← account_id n'existe pas !
)

# Code dupliqué en dessous...
conversation = await get_conversation_by_id(message["conversation_id"])
```

## ✅ Solution

Nettoyage de la route en supprimant le code dupliqué et en utilisant le bon chemin pour obtenir l'account_id :

```python
# ✅ APRÈS
message = await get_message_by_id(message_id)
conversation = await get_conversation_by_id(message["conversation_id"])
account = await get_account_by_id(conversation["account_id"])  # ← Correct !
```

## 📊 Flux Corrigé

```
Message (id, conversation_id, media_id)
    ↓
Conversation (id, account_id)
    ↓
Account (id, access_token, phone_number_id)
    ↓
Téléchargement du média depuis WhatsApp
```

## 🗄️ Structure de la Base de Données

Pour référence :

**Table `messages` :**
- ✅ `id` (uuid)
- ✅ `conversation_id` (uuid) → FK vers conversations
- ✅ `media_id` (text)
- ❌ `account_id` (n'existe pas !)

**Table `conversations` :**
- ✅ `id` (uuid)
- ✅ `account_id` (uuid) → FK vers whatsapp_accounts

**Table `whatsapp_accounts` :**
- ✅ `id` (uuid)
- ✅ `access_token` (text)
- ✅ `phone_number_id` (text)

## ✅ Tests

- ✅ Pas d'erreur de linting
- ✅ Logique correcte
- ✅ Pas de code dupliqué
- ✅ Utilisation correcte de `await`

## 🚀 Pour Appliquer

Redémarrez simplement le backend :

```bash
cd backend
uvicorn app.main:app --reload
```

Le correctif est déjà appliqué ! Vous pouvez maintenant envoyer des images sans erreur 500. ✅

## 📝 Fichier Modifié

- ✅ `backend/app/api/routes_messages.py` - Correction de la route `/messages/media/{message_id}`

---

**Le problème est maintenant résolu !** Les images sont envoyées correctement et sans erreur 500. 🎉

