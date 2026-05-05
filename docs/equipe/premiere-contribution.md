# Première contribution

Objectif mesurable : **un premier PR mergé** (ou au minimum ouvert et vert en CI), après l’environnement local fonctionnel.

## Critères de « bon » premier PR

- **Petit** : idéalement moins de 300 lignes nettes, un seul sujet clair.
- **Testé localement** : commandes du [CONTRIBUTING.md](../../CONTRIBUTING.md) (`pytest`, `npm run lint` / `npm run test` selon la zone touchée).
- **Documenté** : description de PR qui explique le *pourquoi* et le comportement attendu.

## Idées de premières tâches (à taguer `good first issue` côté board)

Adapter à votre backlog réel ; exemples de nature **sûre** pour un nouveau :

- **Frontend** : composant UI (libellé, accessibilité, petit correctif visuel), test Vitest sur une fonction utilitaire.
- **Backend** : test unitaire supplémentaire sur un service existant, docstring ou message d’erreur plus explicite.
- **Docs** : correction de lien, précision dans le notebook ou le troubleshooting (toujours utile).
- **Supabase** : uniquement avec **accord** du owner schéma - les migrations impactent tout le monde.

## Ce qu’il vaut mieux éviter en premier PR

- Refactor massif sans besoin produit immédiat.
- Changement de schéma DB ou de politiques RLS sans revue.
- Modification des chemins **webhook** / signature Meta sans tests et sans pair familier du flux.

