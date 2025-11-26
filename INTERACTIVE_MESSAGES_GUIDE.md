# Guide : Messages interactifs WhatsApp

## 🤔 Comment ça marche ?

Les **messages interactifs** (boutons et listes) sont des fonctionnalités WhatsApp Business qui permettent à vos clients de répondre rapidement en cliquant sur des options prédéfinies.

## 📱 Boutons interactifs

### Ce que c'est :
- Maximum **3 boutons** par message
- Chaque bouton affiche un texte court (max 20 caractères)
- Quand l'utilisateur clique, **sa réponse apparaît comme un message normal** dans le chat

### Exemple d'utilisation :
```
Message : "Bonjour ! Comment puis-je vous aider ?"
Boutons :
- "Commander" (ID: cmd_order)
- "Catalogue" (ID: cmd_catalog)
- "Support" (ID: cmd_support)
```

Quand le client clique sur "Commander", vous recevez un message avec le texte **"Commander"** dans votre chat.

### ⚠️ Ce que ce N'EST PAS :
- ❌ Les boutons ne sont **pas des liens URL**
- ❌ Ils ne déclenchent **pas d'actions automatiques**
- ❌ Ils ne redirigent **pas vers un site web**

### ✅ Ce que c'EST :
- ✅ Une façon de recevoir des **réponses rapides** de vos clients
- ✅ Un moyen de **guider la conversation** avec des options
- ✅ Utile pour des **menus simples** ou des **choix multiples**

## 📋 Listes interactives

### Ce que c'est :
- Une liste déroulante avec plusieurs options organisées en sections
- Maximum **10 options** par liste
- L'utilisateur clique sur un bouton, une liste s'ouvre, il choisit une option
- Sa sélection apparaît comme un message dans le chat

### Exemple d'utilisation :
```
Message : "Choisissez votre produit"
Bouton : "Voir le catalogue"

Sections :
- Vêtements
  - T-shirt blanc (ID: tshirt_white)
  - Pantalon noir (ID: pants_black)
- Accessoires
  - Casquette (ID: cap)
  - Sac (ID: bag)
```

## 🔗 Pour des liens ou actions web

Si vous voulez envoyer des **liens** ou rediriger vers un **site web**, utilisez plutôt :

### 1. Messages texte avec URL
```
Visitez notre site : https://monsite.com
```
Les liens sont automatiquement cliquables dans WhatsApp.

### 2. Messages template avec boutons URL (à configurer sur Meta)
Ces templates nécessitent une configuration sur le Meta Business Manager et une validation de Meta.

## 💡 Quand utiliser les boutons interactifs ?

✅ **Bon cas d'usage :**
- Menu principal : "Catalogue", "Support", "Horaires"
- Confirmation : "Oui", "Non", "Plus tard"
- Évaluation : "⭐", "⭐⭐", "⭐⭐⭐"
- Catégories : "Homme", "Femme", "Enfant"

❌ **Mauvais cas d'usage :**
- Rediriger vers votre site (utilisez un lien texte)
- Faire un paiement (utilisez un lien de paiement)
- Ouvrir une application (pas possible sur WhatsApp)

## 🎯 L'ID des boutons : à quoi ça sert ?

L'**ID** (identifiant) est important pour **vous**, pas pour le client :

- Le client **ne voit que le titre** du bouton
- L'ID vous permet de **reconnaître** quelle option a été choisie dans votre code
- Exemple : si le client clique sur "Commander", vous pouvez vérifier `if (button_id === "cmd_order")` dans votre bot

**Astuce** : Utilisez des IDs descriptifs comme `btn_yes`, `category_shoes`, `action_cancel`, etc.

## 📊 Réception des réponses

Quand un client clique sur un bouton :

1. Vous recevez un **message normal** avec le texte du bouton
2. Dans votre webhook, vous pouvez récupérer l'ID du bouton pour automatiser la réponse
3. Vous pouvez ensuite envoyer un nouveau message en fonction du choix

## 🚀 Résumé

| Fonctionnalité | Usage | Limite |
|---------------|-------|--------|
| **Boutons** | Réponses rapides, menus simples | 3 boutons max |
| **Listes** | Catalogues, plusieurs options | 10 options max |
| **Liens** | Redirection web | Illimité (message texte) |

---

**Note importante** : Les messages interactifs sont uniquement disponibles avec WhatsApp Business API. Ils n'apparaissent pas dans l'application WhatsApp Business (version mobile simple).

