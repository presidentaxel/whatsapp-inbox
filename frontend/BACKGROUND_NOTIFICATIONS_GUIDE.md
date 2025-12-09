# Guide : Notifications en arrière-plan sur mobile

## 📱 Situation actuelle

Votre application utilise **Supabase Realtime** pour recevoir les messages. Cela fonctionne bien quand l'app est ouverte, mais **la connexion WebSocket se ferme** quand l'app est en arrière-plan ou fermée sur mobile.

## ✅ Solutions disponibles

### Option 1 : PWA Installée (Recommandé pour Android)

**Avantages :**
- L'app peut rester plus longtemps active en arrière-plan
- Meilleure gestion de la mémoire
- Expérience proche d'une app native

**Comment installer :**
1. Ouvrez l'app dans Chrome/Edge sur Android
2. Menu (⋮) → "Ajouter à l'écran d'accueil"
3. L'app sera installée comme PWA
4. Le service worker fonctionnera mieux en mode standalone

**Limitations :**
- Les WebSockets peuvent toujours être interrompus par le système
- iOS Safari limite fortement les WebSockets en arrière-plan

### Option 2 : Web Push Notifications (Recommandé pour tous)

**Avantages :**
- Fonctionne même quand l'app est complètement fermée
- Notifications natives via le système d'exploitation
- Supporté sur Android et iOS (Safari 16+)

**Configuration nécessaire :**
1. Générer une clé VAPID (pour Web Push)
2. Configurer Supabase Realtime avec Web Push
3. Enregistrer un subscription endpoint

**Pour implémenter :**
Voir la documentation Supabase Realtime avec Web Push : https://supabase.com/docs/guides/realtime/push-notifications

### Option 3 : Background Sync API (Limité)

**Avantages :**
- Synchronisation périodique même en arrière-plan
- Pas besoin de serveur push externe

**Limitations :**
- Support limité (principalement Chrome/Edge)
- Pas disponible sur iOS Safari
- Dépend des cycles de réveil du navigateur

## 🚀 Ce qui a été amélioré

J'ai ajouté au service worker :
- Support pour Background Sync (si disponible)
- Meilleure gestion des notifications push
- Synchronisation périodique pour vérifier les nouveaux messages

## 📋 Recommandations pour mobile

### Android (Chrome/Edge)
1. ✅ **Installez l'app comme PWA** : Menu → "Ajouter à l'écran d'accueil"
2. ✅ **Autorisez les notifications** : Paramètres du site → Notifications → Autoriser
3. ✅ **Désactivez l'optimisation de batterie** pour l'app (Paramètres Android → Batterie → Optimisation)
4. ✅ Le service worker continuera à fonctionner en arrière-plan

### iOS (Safari)
1. ⚠️ **Limitations importantes** : iOS limite fortement les WebSockets en arrière-plan
2. ✅ **Installez comme PWA** : Partager → "Sur l'écran d'accueil"
3. ✅ **Autorisez les notifications** : Réglages Safari → Notifications → Autoriser
4. ⚠️ Pour une vraie notification en arrière-plan, il faut implémenter **Web Push Notifications** avec Supabase

## 🔧 Prochaines étapes (optionnel)

Pour une solution complète avec notifications même quand l'app est fermée :

1. **Activer Web Push dans Supabase** :
   ```sql
   -- Voir la documentation Supabase pour configurer les push notifications
   ```

2. **Enregistrer le subscription** :
   ```javascript
   // Dans votre app
   const registration = await navigator.serviceWorker.ready;
   const subscription = await registration.pushManager.subscribe({
     userVisibleOnly: true,
     applicationServerKey: 'VAPID_PUBLIC_KEY'
   });
   ```

3. **Envoyer le subscription à votre backend** pour qu'il puisse envoyer des push notifications

## 📝 Notes importantes

- Les **WebSockets se ferment** automatiquement après quelques minutes d'inactivité sur mobile
- Les **notifications locales** (via `showNotification()`) fonctionnent seulement quand le service worker est actif
- Pour des notifications **réelles en arrière-plan**, il faut utiliser **Web Push Notifications**
- Sur iOS, les limitations sont plus strictes - Web Push est nécessaire

## 🎯 Solution immédiate

**Pour Android :**
1. Installez l'app comme PWA
2. Autorisez les notifications
3. L'app restera active plus longtemps en arrière-plan

**Pour iOS :**
L'implémentation de Web Push Notifications est nécessaire pour recevoir des notifications quand l'app est fermée.

