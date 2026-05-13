# Mode Playground - Guide pour créatifs et équipe produit

Document de référence pour préparer une présentation, un storyboard ou une campagne de communication autour du **Playground** : éditeur de scénarios conversationnels WhatsApp intégré à l’application *WhatsApp Inbox*.

Ce guide comporte une **partie explicative** (langage accessible) et une **partie technique** (fidèle au comportement réel du produit et du backend).

---

## Table des matières

1. [En deux phrases](#1-en-deux-phrases)
2. [Pourquoi le Playground existe](#2-pourquoi-le-playground-existe)
3. [Où le trouver dans l’app](#3-où-le-trouver-dans-lapp)
4. [Concepts clés (vue métier)](#4-concepts-clés-vue-métier)
5. [Parcours utilisateur type](#5-parcours-utilisateur-type)
6. [Les blocs (nœuds) et ce qu’ils font](#6-les-blocs-nœuds-et-ce-quils-font)
7. [Déclencheurs et entrées du scénario](#7-déclencheurs-et-entrées-du-scénario)
8. [Variables et personnalisation `{{…}}`](#8-variables-et-personnalisation)
9. [IA : nœud Gemini dans le graphe](#9-ia--nœud-gemini-dans-le-graphe)
10. [Tester sans risque : bac à sable](#10-tester-sans-risque--bac-à-sable)
11. [Assistant conversationnel « aide à la conception »](#11-assistant-conversationnel-aide-à-la-conception)
12. [Bonnes pratiques de conception](#12-bonnes-pratiques-de-conception)
13. [Partie technique](#13-partie-technique)
14. [Limites connues et écarts UI / moteur](#14-limites-connues-et-écarts-ui--moteur)
15. [Pistes créatives pour une présentation](#15-pistes-créatives-pour-une-présentation)
16. [Glossaire](#16-glossaire)

---

## 1. En deux phrases

Le **Playground** est un **éditeur visuel de parcours** (graphe de blocs reliés par des flèches) qui pilote ce que le **bot WhatsApp** envoie et demande aux clients, étape par étape.

Il s’oppose au mode **Gemini** « conversation libre » (même onglet *Assistant*) : ici, on **orchestre** des messages, des choix, des délais et des branches plutôt que de laisser un seul grand prompt gouverner toute la discussion.

---

## 2. Pourquoi le Playground existe

| Besoin métier | Ce que le Playground apporte |
|---------------|------------------------------|
| **Qualification de leads** | Questions à choix multiples, branchement selon la réponse |
| **Accueil structuré** | Séquence fixe (message → options → suite) |
| **Conformité WhatsApp** | Envoi de **templates** approuvés Meta aux bons moments |
| **Horaires d’ouverture** | Routage « dans la plage » / « hors plage » |
| **Relances** | Délai réel ou timeout sur un message interactif |
| **Passage à l’humain** | Bloc **Handoff** pour sortir du bot et prévenir l’équipe |
| **IA ciblée** | Nœud **Gemini** pour comprendre une intention puis **router** vers la bonne branche |

En résumé : c’est l’outil pour des **parcours maîtrisés**, traçables et répétables - proche d’un *builder* type automation, mais **connecté au canal WhatsApp Business** et à l’infra du produit.

---

## 3. Où le trouver dans l’app

- Navigation principale : entrée **Assistant** (selon les droits du compte utilisateur).
- Dans le hub Assistant, deux onglets :
  - **Gemini** - configuration du bot « classique » (prompt, base de connaissances, etc.).
  - **Playground** - l’éditeur de graphe et les outils de test.

Si plusieurs comptes WhatsApp Business sont liés à l’utilisateur, un **sélecteur de compte** en haut du panneau permet de charger les scénarios du bon compte.

**Message pour les créatifs :** visuellement, c’est un **canevas** (grille, zoom, mini-carte), des **cartes compactes** par bloc, une barre d’outils (liste des flux, duplication, collage, test sandbox), et des **modales de réglage** au clic sur un bloc.

---

## 4. Concepts clés (vue métier)

### Scénario = graphe

- **Nœud** : un bloc d’action ou de décision (envoyer un texte, poser une question, router, etc.).
- **Arête (lien)** : flèche qui dit « ensuite, aller là ». Certaines sorties sont **nommées** (ex. branche « oui » / « non », intention 0, 1, *inconnu*).
- **Point d’entrée** : au moins un bloc **Déclencheur** (`start`). Un scénario peut en avoir plusieurs (priorité configurable).

### Persistance et brouillon

- Les graphes sont **enregistrés côté serveur** (avec sauvegarde différée côté UI).
- Une copie **locale** peut servir de secours / amorçage lors de la première création de flux.

### Plusieurs flux par compte

On peut avoir **plusieurs scénarios** nommés ; l’un peut être marqué comme **flux par défaut** pour le compte. Une **conversation** peut aussi être rattachée à un scénario précis (surcharge du défaut).

---

## 5. Parcours utilisateur type

1. Ouvrir **Assistant → Playground** et choisir le **compte** WABA.
2. Sélectionner un **flux** dans la liste ou en créer un nouveau.
3. **Composer** le parcours : ajouter des blocs, les relier, ouvrir les **paramètres** (icône engrenage sur chaque carte).
4. Utiliser l’**assistant IA** (panneau dédié) pour décrire en langage naturel ce que le graphe doit faire - il peut proposer une structure (selon configuration produit).
5. Lancer le **mode test (bac à sable)** : simuler des messages « client » et voir les réponses **comme en production** (y compris appels d’envoi WhatsApp pour les comptes réels, selon les permissions).
6. Itérer jusqu’à validation métier, puis s’appuyer sur le **flux par défaut** ou l’affectation par conversation pour la mise en ligne opérationnelle.

---

## 6. Les blocs (nœuds) et ce qu’ils font

Le tableau ci-dessous résume l’intention **métier**. Le détail du comportement exact (limites Meta, file d’attente, etc.) est en [section 13](#13-partie-technique).

| Bloc (type interne) | Rôle principal |
|----------------------|----------------|
| **Déclencheur** (`start`) | Définit **comment** le scénario démarre (message entrant, campagne planifiée, etc.) et des filtres (mot-clé, audience). |
| **Texte** (`sendText`) | Envoie un **message texte** WhatsApp. |
| **Template** (`sendTemplate`) | Envoie un **template WhatsApp** (modèle approuvé Meta) avec variables. |
| **Interactif** (`interactiveNode`) | Message avec **boutons** (jusqu’à 3) ou **liste** (jusqu’à 10 lignes) ; peut enregistrer la réponse dans une variable ; peut avoir une **branche timeout**. |
| **Gemini** (`gemini`) | Appelle l’IA pour classifier une **intention** (mots-clés / optionnellement similarité sémantique) et suivre la sortie correspondante ; peut poser des **questions de clarification** avant une branche « inconnu ». |
| **Routeur** (`routerNode`) | Route selon le texte reçu ou l’id bouton / ligne de liste (plusieurs routes + branche « échappatoire »). |
| **Handoff** (`handoffNode`) | **Désactive le bot** sur la conversation et **notifie** l’équipe (passage humain). |
| **Délai** (`delayNode`) | **Pause réelle** (secondes à jours) avant la suite du scénario. |
| **Date / attente** (`waitUntilNode`) | Peut **planifier une reprise** à une date/heure résolue ; sinon enchaînement ou passthrough selon cas (voir partie technique). |
| **Fenêtre horaire** (`timeWindowNode`) | Branche **dans la plage** ou **hors plage** (jours + heures). |
| **Logique** (`logicNode`) | Mode **si** : condition vraie / fausse (deux sorties). Les modes **et / ou** dans l’UI ne font pas de vrai routage multi-sortie côté moteur - voir [section 14](#14-limites-connues-et-écarts-ui--moteur). |

### Repères UX dans l’interface

- Chaque bloc affiche un **résumé lisible** (titre tronqué, type, indices).
- Les **poignées** sur les bords des cartes correspondent aux **sorties nommées** (intentions Gemini, routes, inside/outside, etc.). Un **double-clic** sur une poignée peut **détacher** les liens pour réorganiser vite le graphe.
- Une **validation** du graphe signale les problèmes courants (ex. déclencheur sans suite, scénario vide).

---

## 7. Déclencheurs et entrées du scénario

### Message entrant (`message_in`)

Le scénario peut démarrer quand un client envoie un message, avec un filtre :

- **N’importe quel message**
- **Contient** / **égal** / **expression régulière** sur un mot-clé

### Priorité entre plusieurs déclencheurs

Si plusieurs blocs **Déclencheur** matchent, un **nombre de priorité** (`entryPriority`) permet de trancher (plus grand = prioritaire). À priorité égale, le moteur favorise un déclencheur **message entrant** par rapport à une entrée **campagne** - pour éviter qu’une campagne « mange » toujours la place d’une entrée conversationnelle.

### Audience restreinte

Pour `message_in` (et les entrées campagne qui réutilisent les mêmes filtres texte), on peut limiter **qui** est concerné :

- **Tout le monde**
- **Un groupe de diffusion** (broadcast group)
- **Une liste de numéros** (persistée côté produit)

Cela permet d’avoir **plusieurs scénarios** ou variantes selon les segments.

### Campagne planifiée (`playground_audience`)

Entrée dédiée aux **lancements** type campagne : à l’heure prévue, le moteur **enchaîne** depuis ce déclencheur **sans message client** (le fil du parcours commence au nœud suivant le `start`).

L’UI permet de lier un **groupe d’audience**, une **date/heure de lancement** (brouillon), et des workflows d’**import** d’audience / planification côté API.

### Autres types affichés dans l’éditeur

L’interface peut proposer des modes (planification, webhook, manuel, etc.) pour **évolution produit** ou cas avancés. Le cœur du routage **message par message** repose surtout sur **`message_in`** et **`playground_audience`** pour les parcours documentés ici.

---

## 8. Variables et personnalisation

### Syntaxe

Dans les textes (et certains champs), la substitution utilise la forme :

```text
{{nomVariable}}
```

### Origine des valeurs

- **Variables de session** : stockées dans l’état du flux sur la conversation (ex. réponses aux interactifs, clés définies par certains blocs).
- **Variables « intégrées »** : à chaque exécution, le moteur injecte des informations **contact / conversation**, par exemple :
  - `contact_name`, `nom_client`
  - `contact_phone`, `numero_client`
  - `contact_first_name`, `prenom_client`
  - variantes avec notation `contact.name`, `contact.phone`, etc.

Ces clés **écrasent** des variables utilisateur du même nom pour éviter les conflits involontaires.

### Intérêt créatif

C’est le levier pour des messages **personnalisés** (« Bonjour {{prenom_client}} ») sans coder - tant que la donnée est disponible côté contact.

---

## 9. IA : nœud Gemini dans le graphe

Ce n’est **pas** le même écran que l’onglet *Gemini* du hub : ici, Gemini sert surtout à :

1. **Extraire un mot-clé / intention** à partir du message utilisateur (flux « keyword »).
2. **Faire correspondre** cette intention à des **branches** sortantes définies dans le graphe.
3. Optionnellement, utiliser des **embeddings** pour rapprocher sémantiquement le message des intentions si le mot-clé strict ne suffit pas.
4. Envoyer de **courtes relances de clarification** si l’intention est floue, jusqu’à un plafond réglable, avant de basculer sur la branche « inconnu ».
5. Tenir un **journal structuré** de session (`flow_structured_notes`) lorsque l’option est activée - utile pour contextualiser les prompts ou le suivi.

**Note scénaristique :** pour un simple « Bonjour » sans autre contenu, le moteur peut **basculer vers la première intention** définie (parcours principal), pour éviter de bloquer l’utilisateur sur la branche « inconnu ».

---

## 10. Tester sans risque : bac à sable

### Principe

Le produit réserve un **numéro client fictif** pour une **conversation de test** par scénario. Cette conversation :

- **N’apparaît pas** dans la liste principale de l’inbox (filtrée côté client).
- Permet de **simuler** des messages entrants et de voir les réponses **réelles** du pipeline (y compris envoi WhatsApp quand le compte est configuré - selon droits).

### Actions typiques

- **Créer / réinitialiser** la session de test pour un flux donné.
- **Simuler** un message entrant.
- Enchaîner des **lots de messages** de test.
- Simuler un **lancement campagne** aligné sur le déclencheur `playground_audience`.

### Templates en sandbox

Les envois template peuvent être **matérialisés** dans le fil de test avec un format dédié pour vérifier nom de template, langue et paramètres - sans ambiguïté pour le recetteur.

---

## 11. Assistant conversationnel « aide à la conception »

Le panneau **Assistant Playground** (chat) permet de :

- Décrire un besoin en langage naturel (« accueil + qualification + handoff »).
- S’appuyer sur des **starters** (exemples de formulations).
- Conserver des **fils de discussion** (threads) pour itérer sur un même scénario.

**Important :** l’assistant est un **copilote** de conception ; le graphe final reste éditable manuellement sur le canevas. Les temps de réponse peuvent être longs lorsque le modèle génère ou analyse tout un JSON de graphe.

---

## 12. Bonnes pratiques de conception

Alignées sur la documentation interne du produit :

1. **Commencer simple** - peu de blocs, test sandbox, puis complexifier.
2. **Libellés courts** sur boutons et intentions (contraintes WhatsApp : longueurs max sur titres de boutons et lignes de liste).
3. **Une intention = un chemin clair** sur le nœud Gemini ; éviter douze intentions quasi identiques.
4. **Préférer les connexions explicites** sur les sorties nommées (poignées) plutôt que de s’appuyer sur l’ordre implicite des liens - surtout pour **fenêtre horaire** et **timeout** interactif.
5. **Ne pas surcharger** les champs « avancés » (timeouts template, métadonnées) tant que le besoin n’est pas clair.
6. Pour les campagnes et segments : **documenter** qui reçoit quoi (groupe vs liste de numéros) pour éviter les mauvaises surprises en prod.

---

## 13. Partie technique

### 13.1 Architecture générale

| Couche | Rôle |
|--------|------|
| **Frontend (React + React Flow / XYFlow)** | Édition du graphe, validation statique, sauvegarde, sandbox UI, chat d’assistance. |
| **API FastAPI** (`/bot/playground-flows/...`) | CRUD flux, défaut, duplication, collage de sous-graphe, sandbox, simulation, assistant, threads, import audience, planification. |
| **Moteur** (`flow_runtime_service.try_run_playground_flow`) | Interprète le graphe à chaque message (ou réveil programmé), met à jour `bot_flow_state` sur la conversation. |
| **Persistance** | Table des flux `playground_flows` ; profil bot `bot_profiles` (ex. `default_playground_flow_id`, legacy `published_playground_flow`) ; état de session JSON sur `conversations.bot_flow_state`. |

### 13.2 Résolution du graphe pour une conversation

Ordre appliqué côté serveur :

1. `conversations.playground_flow_id` si défini ;
2. sinon `bot_profiles.default_playground_flow_id` ;
3. sinon ancien champ **legacy** `published_playground_flow` sur le profil bot.

### 13.3 Mode bot sur la conversation

Lorsque le mode de réponse bot est **`playground`**, le pipeline de messages entrants tente d’abord **`try_run_playground_flow`**. Si le flux **traite** le message (retour positif), le bot Gemini « classique » n’est pas invoqué pour ce tour.

### 13.4 État de session (`bot_flow_state`)

Champs notables (conceptuellement) :

- `phoneNumber`, `currentNodeId` (attente de réponse sur un interactif), `variables`, `continueFromNodeId`, `entryStartNodeId`, `activeFlowId`
- **Délai** : `flowDelayUntil`, `flowDelayResumeNodeId` pour `delayNode`, timeouts d’interactif, ou certaines attentes calendaires résolues
- **Gemini** : compteur de clarifications par nœud (`geminiClarifyByNode`)

Si l’identifiant de flux actif change, une partie de l’état est **réinitialisée** pour éviter des incohérences entre graphes.

### 13.5 File d’exécution et limite de pas

À chaque invocation, le moteur enchaîne des **pas** jusqu’à attendre une entrée utilisateur, un délai, ou une limite **`maxStepsPerInvocation`** (valeur documentée dans la référence interne, typiquement de l’ordre de **40** pas). C’est une garde-fou contre les boucles infinies.

### 13.6 Délais réels (`delayNode`)

- Unités : **s**, **m**, **h**, **d** ; plafond d’environ **30 jours**.
- Implémentation : boucle **asyncio** périodique côté API (pas Celery dans la doc interne) qui réveille les conversations dues.
- Pendant un délai **sans** attente interactif en cours, un nouveau message client peut être **ignoré** jusqu’à l’échéance (comportement documenté dans la référence).

### 13.7 Signaux entrants WhatsApp

Le moteur exploite notamment : **texte**, **id de bouton**, **id de ligne de liste** - pour réactiver les bons nœuds après un interactif ou un routeur.

### 13.8 API utiles (aperçu)

Les préfixes exacts suivent le client HTTP du frontend (`playgroundFlowsApi.js`) :

- CRUD : liste / get / create / update / delete / set-default / duplicate / paste-subgraph
- Sandbox : `sandbox-session`, `sandbox-reset`, `simulate-inbound`, `simulate-inbound-batch`, `simulate-campaign-launch`
- Assistant : `assistant`, `assist-threads` (CRUD + restauration)
- Audience / planning : `schedule-flow-launch`, `import-audience`, `import-audience-csv`

Les endpoints sensibles (simulation, sandbox) exigent typiquement la permission **`messages.send`** sur le compte.

### 13.9 Référence machine lisible

Le dépôt contient une **référence JSON** alignée sur le moteur : `backend/docs/playground_flow_reference.json` - utile pour les développeurs et pour vérifier les écarts après une évolution.

---

## 14. Limites connues et écarts UI / moteur

### 14.1 Fonctionnalités souvent absentes vs outils no-code génériques

La référence interne liste notamment :

- **Pas de nœud HTTP / webhook** sortant pour enrichir depuis un CRM externe dans le graphe.
- **Pas de nœud « set variable » arbitraire** - la persistance passe surtout par interactifs, saisies, Gemini, etc.
- **Médias natifs** (image, PDF, audio) hors template : pas de blocs dédiés ; les médias passent par **templates** Meta si le modèle le prévoit.
- **Tags** saisis sur le bloc Handoff dans l’UI : **non lus** par le moteur documenté - le handoff reste centré sur la désactivation du bot et la remontée humaine.

### 14.2 Cas où le canevas peut « mentir » légèrement

- **Logique ET / OU** : l’UI dessine des branchements multiples, mais le moteur fait essentiellement du **passthrough** simple - seul le mode **si** réalise un **vrai** routage conditionnel à deux sorties.
- **Fenêtre horaire** : si des arêtes anciennes n’ont **pas** de poignée `inside` / `outside`, l’ordre des deux liens **sans poignée** compte (convention documentée : premier = hors plage, second = dans la plage - vérifier la référence à jour).
- **Handoff** : champs visuels comme tags / assignation d’agent peuvent ne pas être tous **câblés** côté runtime - se référer au code ou à la référence JSON.

Ces points ne sont pas forcément des « bugs » : ce sont des **décalages** entre la promesse visuelle et le moteur actuel - à intégrer dans une communication honnête et dans les tests recette.

---

## 15. Pistes créatives pour une présentation

### Storytelling

- **Avant / après** : la même équipe passant d’une réponse libre Gemini à un **parcours validé** avec handoff mesurable.
- **Journée type** : client écrit le matin → fenêtre horaire → message différent le soir → relance J+2 avec `delayNode`.

### Visuels

- Vue **grand écran** du graphe avec **mini-map** et zoom.
- Gros plan sur un **interactif** 3 boutons et la **trace** dans le bac à sable.
- Capture du **template** WhatsApp avec variables `{{…}}` remplies.

### Ton

- Insister sur **contrôle**, **conformité Meta** (templates), **passage à l’humain** au bon moment.
- Ne pas vendre le Playground comme un **iPaaS** généraliste : c’est un **orchestrateur WhatsApp** dans l’écosystème du produit.

### Démo live (checklist)

1. Un graphe **court** (accueil → 2 boutons → 2 messages).
2. Un **test sandbox** montrant la vraie réponse utilisateur.
3. Optionnel : un **handoff** vers l’équipe interne.

---

## 16. Glossaire

| Terme | Signification |
|-------|----------------|
| **WABA** | WhatsApp Business Account - compte business rattaché au produit. |
| **Template / gabarit** | Message modèle **approuvé** par Meta ; requis pour certains envois hors session. |
| **Interactif** | Message WhatsApp avec **boutons** ou **liste**. |
| **Graphe** | Ensemble de nœuds et d’arêtes (le scénario). |
| **Sandbox / bac à sable** | Conversation de test isolée avec numéro réservé. |
| **Handoff** | Passage de la main au **humain**, bot désactivé sur la conversation. |
| **Playground flow id** | Identifiant UUID du scénario en base. |
| **`bot_flow_state`** | État JSON du parcours en cours sur une conversation. |

---

## Document vivant

- Pour les **réglages rapides par type de nœud** : `frontend/docs/playground-node-setup.md`
- Pour le **contrat technique détaillé** (champs, limites, mismatches) : `backend/docs/playground_flow_reference.json`

*Généré pour faciliter le travail des équipes créatives et la préparation de présentations - à actualiser si le produit évolue.*
