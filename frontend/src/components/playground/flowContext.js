import { createContext } from "react";

/** Ouvre la modale de configuration pour ce nœud */
export const OpenNodeSettingsContext = createContext((_nodeId) => {});

/** (nodeId, partialData) => void */
export const PatchNodeContext = createContext(() => {});

/** (nodeId) => void - supprime le nœud et ses arêtes */
export const DeleteNodeContext = createContext(() => {});

/** { templates: array, loading: boolean } */
export const TemplatesContext = createContext({ templates: [], loading: false });

/** { items: { id, label, varKey }[] } - varKey utilisable dans l’expression SI */
export const VarListContext = createContext({ items: [] });

/** Liste des nœuds du graphe (pour lister les templates dans le SI) */
export const PlaygroundGraphContext = createContext([]);

/** Double-clic sur une poignée : détache toutes les arêtes sur ce point */
export const DetachHandleContext = createContext(() => {});
