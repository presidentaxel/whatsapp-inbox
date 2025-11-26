# 🔍 Debug : Images et Messages Optimistes sur Mobile

Date: 26 Novembre 2025

## 🛠️ Corrections Appliquées

### 1. Messages Optimistes Visibles

**Problème:** Les messages disparaissaient immédiatement

**Corrections:**
- ✅ Délai de refresh augmenté (500ms → 1500ms)
- ✅ Polling ralenti (3s → 5s)
- ✅ Détection intelligente des doublons
- ✅ Ajout du champ `message_type: "text"`

### 2. Images Plus Visibles

**Corrections:**
- ✅ Délai de refresh après média (0ms → 2000ms)
- ✅ Logs détaillés ajoutés
- ✅ Préparation pour aperçu optimiste

---

## 🧪 Tests à Effectuer

### Test 1: Messages Texte Optimistes

1. Ouvre la console du navigateur (F12)
2. Tape un message et envoie-le
3. **Tu devrais voir:**
   - Le message apparaître **instantanément**
   - Rester visible pendant ~1.5 secondes
   - Puis être remplacé par le message du serveur

**Logs attendus:**
```
📨 Messages récupérés: X
```

### Test 2: Upload d'Image

1. Ouvre la console
2. Envoie une image
3. **Tu devrais voir:**

```javascript
// Étape 1: Upload
📤 Upload de fichier: photo.jpg image/jpeg Account: xxx-xxx
✅ Upload réussi: {id: '1331276924968644'}
✅ Media ID extrait: 1331276924968644

// Étape 2: Envoi
📨 Envoi message média: {mediaType: "image", mediaId: "1331276924968644"}
🎨 Affichage aperçu optimiste
✅ Message média envoyé

// Étape 3: Attente et refresh
⏳ Attente traitement média...
🔄 Refresh après média
📨 Messages récupérés: X

// Étape 4: Message média dans la liste
🖼️ Message média: {
  id: "uuid-...",
  type: "image",
  media_id: "1331276924968644",
  content: "[image]" ou "caption"
}
```

---

## ❓ Si les Images ne S'Affichent Toujours Pas

### Vérification 1: Le Message a-t-il un media_id ?

Cherche dans les logs:
```javascript
🖼️ Message média: {
  id: "...",
  type: "image",      // ← Doit être "image"
  media_id: "...",    // ← Doit être présent !
  content: "..."
}
```

**Si `media_id` est null/undefined:**
- Le message n'a pas été enregistré correctement côté backend
- Vérifier les logs backend

### Vérification 2: Le Type de Message est-il Correct ?

Le `message_type` doit être:
- `"image"` pour les images
- `"video"` pour les vidéos
- `"document"` pour les documents
- `"audio"` pour les audios

**Si le type est wrong:**
- C'est un problème côté backend dans `send_media_message_with_storage`

### Vérification 3: L'API Média Fonctionne-t-elle ?

Ouvre les DevTools → Network et cherche:
```
GET /api/messages/media/{message_id}
```

**Statut attendu:** 200 OK

**Si 404:**
- Le message n'existe pas dans la DB
- Ou le `media_id` est incorrect

**Si 500:**
- Erreur serveur backend
- Vérifier les logs backend

### Vérification 4: L'Image se Charge-t-elle ?

Dans le MessageBubble, tu devrais voir:
```
1. "Chargement…" (loading)
2. Puis l'image OU "Média non disponible" (erreur)
```

**Si "Chargement…" reste bloqué:**
- L'API `/messages/media/{id}` ne répond pas
- Timeout réseau

**Si "Média non disponible":**
- L'API a répondu avec une erreur
- Ou le blob est vide/corrompu

---

## 🐛 Problèmes Connus

### Problème A: Images Apparaissent Après Plusieurs Secondes

**Cause:** Le polling (5s) ou le realtime met du temps

**Solution temporaire:** Rafraîchir manuellement en scrollant

**Solution permanente:** 
- Réduire le délai de refresh après média (actuellement 2s)
- Ou implémenter websockets plus fiables

### Problème B: Messages Optimistes Disparaissent Immédiatement

**Cause:** Le polling écrase trop vite

**Solution déjà appliquée:**
- Polling à 5s au lieu de 3s
- Refresh à 1.5s au lieu de 500ms

**Si ça persiste:**
- Désactiver temporairement le polling pour tester
- Commenter les lignes 78-90 dans `MobileChatWindow.jsx`

### Problème C: Doublons de Messages

**Cause:** Le message optimiste + le message réel

**Solution déjà appliquée:**
- Détection intelligente des doublons par timestamp
- Filtrage des messages temporaires

---

## 🔧 Configuration de Debug Avancé

### Option 1: Désactiver le Polling (Test)

Dans `MobileChatWindow.jsx`, commente:
```javascript
// Polling régulier pour mobile (plus fiable que realtime sur mobile)
useEffect(() => {
  if (!conversation?.id) return;

  // TEMPORAIREMENT DÉSACTIVÉ POUR DEBUG
  return;
  
  const pollInterval = setInterval(() => {
    refreshMessages();
  }, 5000);

  return () => {
    clearInterval(pollInterval);
  };
}, [conversation?.id, refreshMessages]);
```

### Option 2: Forcer le Refresh Manuel

Ajoute un bouton de refresh:
```jsx
<button onClick={refreshMessages}>
  🔄 Rafraîchir
</button>
```

### Option 3: Augmenter les Délais

Dans `MobileChatWindow.jsx`:
```javascript
// Ligne 71: Refresh après envoi message
setTimeout(refreshMessages, 3000); // Au lieu de 1500

// Ligne 240: Refresh après média  
setTimeout(refreshMessages, 5000); // Au lieu de 2000
```

---

## 📊 Checklist de Diagnostic

### Messages Texte
- [ ] Le message apparaît instantanément ?
- [ ] Le message reste visible au moins 1 seconde ?
- [ ] Le message est remplacé par la version serveur ?
- [ ] Pas de doublon ?

### Images
- [ ] L'upload réussit (logs `✅ Upload réussi`) ?
- [ ] Le media_id est extrait (logs `✅ Media ID extrait`) ?
- [ ] Le message média est envoyé (logs `✅ Message média envoyé`) ?
- [ ] Le refresh récupère le message média (logs `🖼️ Message média`) ?
- [ ] Le message a bien un `media_id` ?
- [ ] Le message a le bon `message_type` ?
- [ ] L'image commence à se charger ?
- [ ] L'image s'affiche finalement ?

---

## 🚀 Solutions Rapides

### Si Messages Optimistes ne Marchent Pas

**Solution 1: Désactiver le polling**
```javascript
// Dans MobileChatWindow.jsx, ligne 78-90
// Commenter tout le useEffect du polling
```

**Solution 2: Augmenter tous les délais**
```javascript
// Ligne 71
setTimeout(refreshMessages, 5000); // 5 secondes

// Ligne 85
}, 10000); // Polling toutes les 10 secondes

// Ligne 240
setTimeout(refreshMessages, 5000); // 5 secondes
```

### Si Images ne S'Affichent Pas

**Solution 1: Vérifier que le message contient media_id**

Regarde les logs console après upload:
```javascript
🖼️ Message média: {...}
```

Si pas de log `🖼️`, le message n'a pas de `media_id`.

**Solution 2: Tester l'API directement**

Dans la console:
```javascript
// Remplace MESSAGE_ID par un vrai ID de message
fetch('/api/messages/media/MESSAGE_ID')
  .then(r => r.blob())
  .then(b => console.log('Blob size:', b.size))
  .catch(e => console.error('Error:', e));
```

**Solution 3: Vérifier les logs backend**

Cherche dans les logs backend:
```
INFO: Sending media message...
ERROR: ...
```

---

## 📞 Informations à Fournir pour Support

Si ça ne fonctionne toujours pas, fournis:

1. **Logs console complets** après envoi d'image
2. **Network tab** (requêtes HTTP et leurs réponses)
3. **Logs backend** (si accessible)
4. **Version du navigateur** mobile
5. **Capture d'écran** de l'interface

---

## ✅ Validation Finale

Après les corrections, tu devrais avoir:

| Feature | Status |
|---------|--------|
| Message texte apparaît instantanément | ✅ |
| Message texte reste visible 1-2s | ✅ |
| Pas de doublon de messages | ✅ |
| Upload d'image réussit | ✅ |
| Message média créé avec media_id | ⏳ À vérifier |
| Image se charge | ⏳ À vérifier |
| Image s'affiche | ⏳ À vérifier |

Les deux derniers points dépendent du backend et de la synchronisation avec WhatsApp.

