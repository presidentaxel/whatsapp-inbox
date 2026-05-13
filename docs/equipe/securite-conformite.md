# Sécurité et conformité - rappels équipe

Résumé **opérationnel** pour les développeurs. Compléter par vos politiques internes (RGPD, sous-traitants, pays de résidence des données).

## Secrets

- **Ne jamais** committer : tokens Meta (`WHATSAPP_TOKEN`, etc.), clés Supabase (`service_role`, clés privées), `GEMINI_API_KEY`, mots de passe.
- Utiliser `backend/.env.example` comme **liste de variables** sans valeurs réelles.
- Rotation : en cas de fuite ou départ d’un membre, **révoquer** côté Meta / Supabase / Google et régénérer.

## Logs et support

- Éviter de logger **contenu de messages** clients, numéros complets ou tokens en clair.
- Pour le debug, préférer des **identifiants internes** (UUID message, id conversation) et tronquer les PII si nécessaire.
- Les captures d’écran de bug doivent être **anonymisées** avant partage public (issue GitHub).

## Données et accès

- Les opérateurs passent par **Supabase Auth** ; les droits fins sont portés par **Postgres / RLS** selon votre déploiement.
- Tout accès « admin » (clé `service_role`) est **côté serveur uniquement** - jamais exposé au navigateur.

## WhatsApp / Meta

- Respecter les [politiques commerciales](https://www.whatsapp.com/legal) et les règles d’usage de l’API Cloud (opt-in, templates, etc.).
- Ne pas contourner les mécanismes officiels (envoi, webhooks) pour des usages interdits par Meta.

## Signalement

- Canal ou contact interne pour **vulnérabilité** ou incident de sécurité.

