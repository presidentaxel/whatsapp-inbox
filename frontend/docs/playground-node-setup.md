# Playground - Setup minimal des nodes

Objectif: configurer vite. Les modales affichent l'essentiel, le reste est ici.

## Raccourci par node

- `Déclencheur`: choisir le type, puis le critère principal.
- `Texte`: écrire le message.
- `Template`: choisir le template puis remplir les variables.
- `Gemini`: définir le prompt système.
- `Interactif`: message + type + options.
- `Routeur`: ajouter les branches attendues.
- `Handoff`: tags + message interne.
- `Délai` / `Date` / `Horaires`: définir uniquement la contrainte de temps.
- `Logique`: écrire l'expression si/sinon.

## Champs avancés (masqués)

Ces champs existent toujours, mais ne sont plus prioritaires:

- Statut Meta d'un template.
- Timeout de relance (`template` et `interactif`).
- Contexte Gemini (`hint`, `knowledgeBase`).
- Assignation agent sur handoff.

## Convention recommandée

- Commencer simple, tester, puis affiner.
- Garder des libellés courts et explicites.
- Éviter d'ajouter des options avancées sans besoin concret.

## Référence moteur

Pour les limites techniques et le comportement exact côté backend:

- `backend/docs/playground_flow_reference.json`
