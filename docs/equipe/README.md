# Documentation équipe

Ensemble des guides pour **intégrer un développeur** et faire tourner le produit sans friction : processus, dépannage, sécurité, ownership.

## Parcours recommandé

1. **Machine et stack locale** - le notebook `[notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb](../../notebooks/EQUIPE_ONBOARDING_FROM_ZERO.ipynb)` est **autonome**
2. **Première contribution** - [premiere-contribution.md](./premiere-contribution.md).
3. **Contribuer au code** - [CONTRIBUTING.md](../../CONTRIBUTING.md) à la racine du dépôt.

## Index


| Document                                                     | Contenu                                       |
| ------------------------------------------------------------ | --------------------------------------------- |
| [premiere-contribution.md](./premiere-contribution.md)       | Objectif « premier PR », idées de tâches      |
| [troubleshooting.md](./troubleshooting.md)                   | Webhook, Supabase, auth, erreurs courantes    |
| [securite-conformite.md](./securite-conformite.md)           | Secrets, logs, données personnelles           |
| [SECURITY.md](../../SECURITY.md) (racine du dépôt)            | Signalement responsable des vulnérabilités     |
| [glossaire.md](./glossaire.md)                               | Termes WhatsApp / Meta / produit              |
| [schema-lmdcvtc-inbox.md](./schema-lmdcvtc-inbox.md)         | Tables inbox sur le projet Supabase LMDCVTC   |
| [supabase-source-of-truth.md](./supabase-source-of-truth.md) | Migrations : source de vérité, squash, pièges |


## Modèles GitHub

- [Pull request](../../.github/pull_request_template.md) - corps de PR par défaut.
- [Rapport de bug](../../.github/ISSUE_TEMPLATE/bug_report.md) - issue type bug.

## Environnement partagé

Pour ne pas dépendre uniquement des comptes personnels le jour J, l’équipe peut maintenir :

- un **projet Supabase** (ou schéma de staging) partagé ;
- une **app Meta / numéro de test** WhatsApp Cloud API pour le développement ;
- des **variables** documentées dans un gestionnaire de secrets d’équipe (hors Git).

