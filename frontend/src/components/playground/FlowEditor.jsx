import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import NodeSettingsModal from "./NodeSettingsModal";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MiniMap,
  addEdge,
  reconnectEdge,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { listTemplates } from "../../api/whatsappApi";
import { saveBotProfile } from "../../api/botApi";
import { getAccounts } from "../../api/accountsApi";
import {
  listPlaygroundFlows,
  getPlaygroundFlow,
  createPlaygroundFlow,
  updatePlaygroundFlow,
  deletePlaygroundFlow,
  setPlaygroundFlowDefault,
  duplicatePlaygroundFlow,
  pastePlaygroundSubgraph,
} from "../../api/playgroundFlowsApi";
import {
  PatchNodeContext,
  DeleteNodeContext,
  TemplatesContext,
  VarListContext,
  PlaygroundGraphContext,
  OpenNodeSettingsContext,
  DetachHandleContext,
} from "./flowContext";
import { playgroundNodeTypes } from "./flowNodes";
import { loadFlow, saveFlow } from "./flowStorage";
import { migrateFlowPayload, makeVarKeyFromId } from "./flowMigrate";
import PlaygroundAssistantChat from "./PlaygroundAssistantChat";

import "./playground.css";

const flowUid = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `n_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;

const initialNodes = () => [
  {
    id: "start",
    type: "start",
    position: { x: 260, y: 24 },
    data: {
      varKey: "réponse_entrée",
      triggerType: "message_in",
      messageMatch: "any",
      messageKeyword: "",
      scheduleAt: "",
      scheduleRepeat: "none",
      webhookSecretRef: "",
      entryPriority: 0,
    },
  },
];

function defaultDataForType(type) {
  switch (type) {
    case "start":
      return {
        triggerType: "message_in",
        messageMatch: "any",
        messageKeyword: "",
        scheduleAt: "",
        scheduleRepeat: "none",
        webhookSecretRef: "",
        entryPriority: 0,
      };
    case "sendText":
      return { body: "" };
    case "sendTemplate":
      return {
        selectedTemplateKey: "",
        templateName: "",
        templateLanguage: "",
        variableValues: {},
      };
    case "gemini":
      return { hint: "", systemPrompt: "", intents: [] };
    case "interactiveNode":
      return {
        body: "",
        uiKind: "buttons",
        choices: [
          { id: "btn_0", title: "Oui" },
          { id: "btn_1", title: "Non" },
        ],
        listButtonText: "Voir les options",
        timeoutDuration: "",
        timeoutUnit: "h",
      };
    case "routerNode":
      return {
        routes: [
          { label: "Option A", match: "Option A" },
          { label: "Option B", match: "Option B" },
        ],
      };
    case "handoffNode":
      return { tagsText: "", assignAgent: "", internalMessage: "" };
    case "logicNode":
      return { logicMode: "si", condition: "" };
    case "delayNode":
      return { duration: "5", unit: "s" };
    case "waitUntilNode":
      return { until: "", timezoneNote: "" };
    case "timeWindowNode":
      return {
        activeDays: ["1", "2", "3", "4", "5"],
        startTime: "09:00",
        endTime: "18:00",
      };
    default:
      return {};
  }
}

function subgraphFromSelection(nodes, edges) {
  const sel = nodes.filter((n) => n.selected);
  if (!sel.length) return null;
  const ids = new Set(sel.map((n) => n.id));
  const subEdges = edges.filter(
    (e) => ids.has(e.source) && ids.has(e.target)
  );
  const cleanNodes = sel.map((n) => {
    const { selected: _s, dragging: _d, ...rest } = n;
    return {
      ...rest,
      position: { ...rest.position },
      data: rest.data ? { ...rest.data } : {},
    };
  });
  const cleanEdges = subEdges.map((e) => ({ ...e }));
  return { nodes: cleanNodes, edges: cleanEdges };
}

function FlowEditorInner({ accountId }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [settingsNodeId, setSettingsNodeId] = useState(null);
  const [publishStatus, setPublishStatus] = useState(null);
  const [flowsList, setFlowsList] = useState([]);
  const [activeFlowId, setActiveFlowId] = useState(null);
  const [flowName, setFlowName] = useState("");
  const [flowsLoading, setFlowsLoading] = useState(true);
  const [clipboardBlocks, setClipboardBlocks] = useState(null);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copyTargetAccount, setCopyTargetAccount] = useState("");
  const [copySubgraphOnly, setCopySubgraphOnly] = useState(false);
  const [accountsList, setAccountsList] = useState([]);
  const hydratedRef = useRef(false);
  const allowSaveRef = useRef(false);
  const saveTimerRef = useRef(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const activeFlowIdRef = useRef(activeFlowId);
  const accountIdRef = useRef(accountId);

  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [nodes, edges]);

  useEffect(() => {
    activeFlowIdRef.current = activeFlowId;
  }, [activeFlowId]);

  useEffect(() => {
    accountIdRef.current = accountId;
  }, [accountId]);

  const openNodeSettings = useCallback((nodeId) => {
    if (nodeId && typeof nodeId === "string") setSettingsNodeId(nodeId);
  }, []);

  const settingsNode = useMemo(
    () =>
      settingsNodeId
        ? nodes.find((n) => n.id === settingsNodeId) ?? null
        : null,
    [nodes, settingsNodeId]
  );

  useEffect(() => {
    if (settingsNodeId && !nodes.some((n) => n.id === settingsNodeId)) {
      setSettingsNodeId(null);
    }
  }, [nodes, settingsNodeId]);

  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    setTemplatesLoading(true);
    listTemplates(accountId)
      .then((res) => {
        if (cancelled) return;
        const list = res?.data?.data ?? res?.data ?? [];
        setTemplates(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!cancelled) setTemplates([]);
      })
      .finally(() => {
        if (!cancelled) setTemplatesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  const applyGraph = useCallback(
    (g) => {
      let raw = g;
      if (typeof raw === "string") {
        try {
          raw = JSON.parse(raw);
        } catch {
          raw = {};
        }
      }
      if (!raw || typeof raw !== "object") raw = {};
      const migrated = migrateFlowPayload(raw);
      const hasNodeList = Array.isArray(migrated.nodes);
      setNodes(hasNodeList ? migrated.nodes : initialNodes());
      setEdges(Array.isArray(migrated.edges) ? migrated.edges : []);
    },
    [setNodes, setEdges]
  );

  const refreshFlowsList = useCallback(async () => {
    if (!accountId) return [];
    const res = await listPlaygroundFlows(accountId);
    const list = Array.isArray(res.data) ? res.data : [];
    setFlowsList(list);
    return list;
  }, [accountId]);

  useEffect(() => {
    if (!accountId) return;
    let cancelled = false;
    (async () => {
      setFlowsLoading(true);
      hydratedRef.current = false;
      allowSaveRef.current = false;
      try {
        let list = await refreshFlowsList();
        if (cancelled) return;
        if (!list.length) {
          const local = loadFlow(accountId);
          const seed = local
            ? migrateFlowPayload(local)
            : { nodes: initialNodes(), edges: [], v: 2 };
          const cr = await createPlaygroundFlow({
            account_id: accountId,
            name: "Flux principal",
            graph: {
              nodes: seed.nodes || initialNodes(),
              edges: seed.edges || [],
              v: 2,
            },
          });
          if (cr.data?.id) {
            list = await refreshFlowsList();
          }
        }
        if (cancelled) return;
        const def = list.find((f) => f.is_default) || list[0];
        if (def?.id) {
          setActiveFlowId(def.id);
          const gr = await getPlaygroundFlow(def.id);
          if (cancelled) return;
          setFlowName(gr.data?.name || def.name || "");
          applyGraph(gr.data?.graph);
          allowSaveRef.current = true;
        }
      } catch (e) {
        console.error(e);
        applyGraph({ nodes: initialNodes(), edges: [] });
        allowSaveRef.current = false;
      } finally {
        if (!cancelled) {
          hydratedRef.current = true;
          setFlowsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accountId, refreshFlowsList, applyGraph]);

  const flushPlaygroundSave = useCallback(async () => {
    const aid = accountIdRef.current;
    const fid = activeFlowIdRef.current;
    if (!allowSaveRef.current || !aid || !fid) return;
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const g = {
      nodes: nodesRef.current,
      edges: edgesRef.current,
      v: 2,
    };
    try {
      await updatePlaygroundFlow(fid, { graph: g });
      saveFlow(aid, g);
    } catch (err) {
      console.error("playground save failed", err);
    }
  }, []);

  useEffect(() => {
    const onHidden = () => {
      if (document.visibilityState === "hidden") {
        void flushPlaygroundSave();
      }
    };
    document.addEventListener("visibilitychange", onHidden);
    return () => document.removeEventListener("visibilitychange", onHidden);
  }, [flushPlaygroundSave]);

  useEffect(() => {
    const onUnload = () => {
      void flushPlaygroundSave();
    };
    window.addEventListener("pagehide", onUnload);
    return () => window.removeEventListener("pagehide", onUnload);
  }, [flushPlaygroundSave]);

  useEffect(() => {
    if (
      !accountId ||
      !activeFlowId ||
      !hydratedRef.current ||
      flowsLoading ||
      !allowSaveRef.current
    )
      return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const g = { nodes, edges, v: 2 };
      updatePlaygroundFlow(activeFlowId, { graph: g })
        .then(() => saveFlow(accountId, g))
        .catch((err) => {
          console.error("playground autosave failed", err);
          setPublishStatus("Erreur sauvegarde — vérifiez la connexion");
          setTimeout(() => setPublishStatus(null), 5000);
        });
    }, 450);
    return () => clearTimeout(saveTimerRef.current);
  }, [nodes, edges, activeFlowId, accountId, flowsLoading]);

  const switchFlow = useCallback(
    async (newId) => {
      if (!newId) return;
      const cur = activeFlowId;
      if (cur && hydratedRef.current && allowSaveRef.current) {
        try {
          await updatePlaygroundFlow(cur, {
            graph: {
              nodes: nodesRef.current,
              edges: edgesRef.current,
              v: 2,
            },
          });
          saveFlow(accountIdRef.current, {
            nodes: nodesRef.current,
            edges: edgesRef.current,
            v: 2,
          });
        } catch (_) {
          /* ignore */
        }
      }
      hydratedRef.current = false;
      allowSaveRef.current = false;
      setActiveFlowId(newId);
      try {
        const gr = await getPlaygroundFlow(newId);
        setFlowName(gr.data?.name || "");
        applyGraph(gr.data?.graph);
        allowSaveRef.current = true;
      } catch (e) {
        console.error(e);
        applyGraph({ nodes: initialNodes(), edges: [] });
        allowSaveRef.current = false;
      }
      hydratedRef.current = true;
    },
    [activeFlowId, applyGraph]
  );

  const patchNode = useCallback(
    (id, partial) => {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === id
            ? { ...node, data: { ...node.data, ...partial } }
            : node
        )
      );
    },
    [setNodes]
  );

  const deleteNode = useCallback(
    (id) => {
      setNodes((nds) => {
        const target = nds.find((n) => n.id === id);
        if (target?.type === "start") {
          const nStarts = nds.filter((n) => n.type === "start").length;
          if (nStarts <= 1) return nds;
        }
        return nds.filter((n) => n.id !== id);
      });
      setEdges((eds) =>
        eds.filter((e) => e.source !== id && e.target !== id)
      );
    },
    [setNodes, setEdges]
  );

  const varListItems = useMemo(() => {
    const labels = {
      start: "Entrée",
      sendText: "Message",
      sendTemplate: "Template",
      gemini: "Gemini",
      interactiveNode: "Interactif",
      routerNode: "Routeur",
      handoffNode: "Handoff",
      delayNode: "Délai",
      waitUntilNode: "Jusqu’à",
      timeWindowNode: "Plage",
      logicNode: "Logique",
    };
    return nodes
      .map((n) => {
        const varKey = n.data?.varKey;
        if (!varKey) return null;
        let label = labels[n.type] || n.type;
        if (n.type === "sendTemplate") {
          const tn =
            n.data?.templateName ||
            (n.data?.selectedTemplateKey || "").split("||")[0] ||
            "";
          label = tn
            ? `Réponse template « ${tn} »`
            : "Réponse après template";
        }
        return {
          id: n.id,
          label,
          varKey,
        };
      })
      .filter(Boolean);
  }, [nodes]);

  const onConnect = useCallback(
    (params) =>
      setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges]
  );

  const onReconnect = useCallback(
    (oldEdge, newConnection) => {
      setEdges((eds) => reconnectEdge(oldEdge, newConnection, eds));
    },
    [setEdges]
  );

  const onReconnectEnd = useCallback(
    (_evt, edge, _handleType, connectionState) => {
      if (connectionState?.isValid === true) return;
      setEdges((eds) => eds.filter((e) => e.id !== edge.id));
    },
    [setEdges]
  );

  const detachAtHandle = useCallback(
    ({ nodeId, handleId, handleType }) => {
      const hid = handleId ?? null;
      setEdges((eds) =>
        eds.filter((e) => {
          if (handleType === "target") {
            const th = e.targetHandle ?? null;
            return !(e.target === nodeId && th === hid);
          }
          const sh = e.sourceHandle ?? null;
          return !(e.source === nodeId && sh === hid);
        })
      );
    },
    [setEdges]
  );

  const addNode = useCallback(
    (type) => {
      const id = flowUid();
      const varKey = makeVarKeyFromId(id);
      setNodes((nds) => [
        ...nds,
        {
          id,
          type,
          position: {
            x: 80 + Math.random() * 220,
            y: 120 + Math.random() * 180,
          },
          data: { varKey, ...defaultDataForType(type) },
        },
      ]);
    },
    [setNodes]
  );

  const exportJson = useCallback(() => {
    const blob = new Blob([JSON.stringify({ nodes, edges, v: 2 }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `playground-${accountId || "flow"}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }, [nodes, edges, accountId]);

  const publishToWebhook = useCallback(async () => {
    if (!accountId || !activeFlowId) return;
    setPublishStatus("…");
    try {
      await setPlaygroundFlowDefault(activeFlowId);
      await saveBotProfile(accountId, {
        published_playground_flow: { nodes, edges, v: 2 },
        default_playground_flow_id: activeFlowId,
      });
      await refreshFlowsList();
      setPublishStatus("ok");
      setTimeout(() => setPublishStatus(null), 4000);
    } catch (e) {
      setPublishStatus(
        e?.response?.data?.detail || e?.message || "Erreur publication"
      );
    }
  }, [accountId, activeFlowId, nodes, edges, refreshFlowsList]);

  const persistFlowName = useCallback(async () => {
    if (!activeFlowId || !flowName.trim()) return;
    try {
      await updatePlaygroundFlow(activeFlowId, { name: flowName.trim() });
      setFlowsList((prev) =>
        prev.map((f) =>
          f.id === activeFlowId ? { ...f, name: flowName.trim() } : f
        )
      );
    } catch (_) {
      /* ignore */
    }
  }, [activeFlowId, flowName]);

  const newEmptyFlow = useCallback(async () => {
    if (!accountId) return;
    try {
      const cr = await createPlaygroundFlow({
        account_id: accountId,
        name: `Flux ${(flowsList.length || 0) + 1}`,
        graph: { nodes: initialNodes(), edges: [], v: 2 },
      });
      if (cr.data?.id) {
        await refreshFlowsList();
        await switchFlow(cr.data.id);
      }
    } catch (e) {
      console.error(e);
    }
  }, [accountId, flowsList.length, refreshFlowsList, switchFlow]);

  const duplicateLocalFlow = useCallback(async () => {
    if (!activeFlowId) return;
    try {
      const cr = await duplicatePlaygroundFlow({
        source_flow_id: activeFlowId,
        target_account_id: accountId,
        name: `${flowName || "Flux"} (copie)`,
      });
      if (cr.data?.id) {
        await refreshFlowsList();
        await switchFlow(cr.data.id);
      }
    } catch (e) {
      console.error(e);
    }
  }, [activeFlowId, accountId, flowName, refreshFlowsList, switchFlow]);

  const removeCurrentFlow = useCallback(async () => {
    if (!activeFlowId || flowsList.length <= 1) return;
    if (!window.confirm("Supprimer ce flux ?")) return;
    try {
      await deletePlaygroundFlow(activeFlowId);
      const next = flowsList.filter((f) => f.id !== activeFlowId)[0];
      await refreshFlowsList();
      if (next?.id) await switchFlow(next.id);
    } catch (e) {
      console.error(e);
    }
  }, [activeFlowId, flowsList, refreshFlowsList, switchFlow]);

  const copySelectionBlocks = useCallback(() => {
    const sub = subgraphFromSelection(nodes, edges);
    if (!sub) {
      setPublishStatus("Sélectionnez des nœuds");
      setTimeout(() => setPublishStatus(null), 2500);
      return;
    }
    setClipboardBlocks(sub);
    setPublishStatus(`${sub.nodes.length} nœud(s) copiés`);
    setTimeout(() => setPublishStatus(null), 2500);
  }, [nodes, edges]);

  const pasteBlocks = useCallback(async () => {
    if (!activeFlowId || !clipboardBlocks?.nodes?.length) return;
    try {
      const res = await pastePlaygroundSubgraph(activeFlowId, clipboardBlocks);
      if (res.data?.graph) applyGraph(res.data.graph);
    } catch (e) {
      console.error(e);
    }
  }, [activeFlowId, clipboardBlocks, applyGraph]);

  const openCopyToAccountModal = useCallback(async () => {
    setShowCopyModal(true);
    setCopySubgraphOnly(false);
    try {
      const res = await getAccounts();
      const arr = Array.isArray(res.data) ? res.data : [];
      setAccountsList(arr);
      const def =
        arr.find((a) => a.id !== accountId)?.id ?? arr[0]?.id ?? "";
      setCopyTargetAccount(def);
    } catch (_) {
      setAccountsList([]);
      setCopyTargetAccount("");
    }
  }, [accountId]);

  const runCopyToAccount = useCallback(async () => {
    if (!activeFlowId || !copyTargetAccount) return;
    const sub = copySubgraphOnly
      ? subgraphFromSelection(nodes, edges)
      : null;
    if (copySubgraphOnly && (!sub?.nodes?.length)) {
      setPublishStatus("Sélectionnez des nœuds pour copier une série de blocs");
      setTimeout(() => setPublishStatus(null), 3500);
      return;
    }
    try {
      const payload = {
        source_flow_id: activeFlowId,
        target_account_id: copyTargetAccount,
        name: `${flowName || "Flux"}`,
      };
      if (sub?.nodes?.length) {
        payload.node_ids = sub.nodes.map((n) => n.id);
      }
      await duplicatePlaygroundFlow(payload);
      setShowCopyModal(false);
      setPublishStatus("Copie envoyée vers l’autre compte");
      setTimeout(() => setPublishStatus(null), 4000);
    } catch (e) {
      console.error(e);
    }
  }, [
    activeFlowId,
    copyTargetAccount,
    copySubgraphOnly,
    nodes,
    edges,
    flowName,
  ]);

  const importRef = useRef(null);
  const onImportFile = useCallback(
    (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        void (async () => {
          try {
            const data = JSON.parse(String(reader.result || ""));
            const migrated = migrateFlowPayload(data);
            const nextNodes = Array.isArray(migrated.nodes)
              ? migrated.nodes
              : initialNodes();
            const nextEdges = Array.isArray(migrated.edges)
              ? migrated.edges
              : [];
            setNodes(nextNodes);
            setEdges(nextEdges);
            if (saveTimerRef.current) {
              clearTimeout(saveTimerRef.current);
              saveTimerRef.current = null;
            }
            const graph = { nodes: nextNodes, edges: nextEdges, v: 2 };
            if (accountId) saveFlow(accountId, graph);
            if (accountId && activeFlowId) {
              await updatePlaygroundFlow(activeFlowId, { graph });
              setPublishStatus("Import enregistré (scénario sauvegardé)");
              setTimeout(() => setPublishStatus(null), 4000);
            } else if (accountId && !activeFlowId) {
              setPublishStatus(
                "Import affiché — enregistrement serveur dès qu’un scénario est chargé"
              );
              setTimeout(() => setPublishStatus(null), 4000);
            }
          } catch (err) {
            console.error(err);
            setPublishStatus("Import impossible (fichier JSON invalide)");
            setTimeout(() => setPublishStatus(null), 4000);
          }
        })();
      };
      reader.readAsText(file);
      e.target.value = "";
    },
    [setNodes, setEdges, accountId, activeFlowId]
  );

  const resetFlow = useCallback(() => {
    setNodes(initialNodes());
    setEdges([]);
  }, [setNodes, setEdges]);

  const templatesValue = useMemo(
    () => ({ templates, loading: templatesLoading }),
    [templates, templatesLoading]
  );

  const varListValue = useMemo(() => ({ items: varListItems }), [varListItems]);

  const getGraphSnapshot = useCallback(
    () => ({
      nodes: nodesRef.current,
      edges: edgesRef.current,
      v: 2,
    }),
    []
  );

  const publishStatusTitle =
    publishStatus === "ok"
      ? "Ce scénario est le défaut du compte pour le webhook (mode Playground), sauf si une conversation a un autre scénario dans le chat."
      : publishStatus || "";
  const publishStatusShort =
    publishStatus === "ok"
      ? "✓ Enregistré"
      : publishStatus && publishStatus.length > 36
        ? `${publishStatus.slice(0, 33)}…`
        : publishStatus;

  return (
    <div className="playground-shell">
      <div className="playground-shell__main">
      <div className="playground-compact">
        <div className="playground-compact__row playground-compact__row--controls">
          <select
            id="playground-flow-select"
            className="playground-compact__select"
            value={activeFlowId || ""}
            disabled={flowsLoading || !flowsList.length}
            onChange={(e) => switchFlow(e.target.value)}
            aria-label="Scénario actif"
            title="Scénario ouvert dans l’éditeur"
          >
            {flowsList.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
                {f.is_default ? " (défaut)" : ""}
              </option>
            ))}
          </select>
          <input
            className="playground-compact__name"
            type="text"
            value={flowName}
            onChange={(e) => setFlowName(e.target.value)}
            onBlur={persistFlowName}
            placeholder="Nom…"
            aria-label="Nom du scénario"
          />
          <button
            type="button"
            className="playground-btn playground-btn--primary playground-btn--compact"
            onClick={publishToWebhook}
            title="Définir ce scénario comme défaut du compte pour les réponses automatiques (webhook, mode Playground)."
          >
            Par défaut
          </button>
          {publishStatus ? (
            <span
              className={`playground-compact__status ${
                publishStatus === "ok" ? "is-ok" : ""
              }`}
              title={publishStatusTitle}
            >
              {publishStatusShort}
            </span>
          ) : null}
          <span className="playground-compact__grow" aria-hidden />
          <details className="playground-more playground-more--toolbar">
            <summary className="playground-more__summary">Plus</summary>
            <div className="playground-more__panel">
              <div className="playground-more__section">
                <span className="playground-more__section-title">Gérer les scénarios</span>
                <div className="playground-more__buttons">
                  <button type="button" className="ghost" onClick={newEmptyFlow}>
                    Nouveau scénario
                  </button>
                  <button type="button" className="ghost" onClick={duplicateLocalFlow}>
                    Dupliquer
                  </button>
                  <button
                    type="button"
                    className="ghost danger-text"
                    onClick={removeCurrentFlow}
                  >
                    Supprimer
                  </button>
                  <button type="button" className="ghost" onClick={openCopyToAccountModal}>
                    Copier vers un autre compte…
                  </button>
                </div>
              </div>
              <div className="playground-more__section">
                <span className="playground-more__section-title">Blocs sur le canevas</span>
                <p className="playground-more__hint muted">
                  Sélectionnez des nœuds (cadre ou clic + Shift), puis copiez pour les réutiliser
                  ou les envoyer vers un autre compte via « Copier vers un autre compte ».
                </p>
                <div className="playground-more__buttons">
                  <button type="button" className="ghost" onClick={copySelectionBlocks}>
                    Copier la sélection
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={!clipboardBlocks}
                    onClick={pasteBlocks}
                  >
                    Coller sur ce scénario
                  </button>
                </div>
              </div>
              <div className="playground-more__section">
                <span className="playground-more__section-title">Fichier</span>
                <div className="playground-more__buttons">
                  <button type="button" className="ghost" onClick={exportJson}>
                    Exporter en JSON
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => importRef.current?.click()}
                  >
                    Importer un JSON
                  </button>
                  <input
                    ref={importRef}
                    type="file"
                    accept="application/json,.json"
                    className="playground-file-input"
                    onChange={onImportFile}
                  />
                  <button type="button" className="ghost danger-text" onClick={resetFlow}>
                    Vider le canevas
                  </button>
                </div>
              </div>
            </div>
          </details>
          <details className="playground-help-pop">
            <summary className="playground-help-pop__summary" title="Aide">
              Aide
            </summary>
            <div className="playground-help-pop__panel">
              <p className="playground-help-pop__p">
                Reliez les blocs sur le canevas. Le scénario <strong>par défaut</strong> est utilisé
                par le webhook (mode Playground), sauf si une conversation a un autre scénario
                choisi dans le chat.
              </p>
              <p className="playground-help-pop__p muted">
                Plusieurs blocs <strong>Entrée</strong> : ouvrez un bloc pour mots-clés et priorité.
                Molette ou clic droit sur le canevas pour déplacer la vue.
              </p>
              <p className="playground-help-pop__p playground-help-pop__p--warn">
                <strong>Limites moteur (UI vs production)</strong> — certains blocs dessinent des
                branches que le serveur ne distingue pas : <strong>Horaires</strong> (inside/outside)
                enchaîne comme un seul chemin ; <strong>Date</strong> (attente calendaire) ne fait pas
                attendre (seul <strong>Délai</strong> pause réellement en relatif) ; <strong>Logique</strong>{" "}
                en modes ET/OU ne route pas, et le mode « si » ne lit pas la condition (pas d’IF métier :
                préférer Routeur, Interactif ou Gemini). Détail :{" "}
                <code className="playground-help-pop__code">backend/docs/playground_flow_reference.json</code>.
              </p>
              <p className="playground-help-pop__p muted">
                <strong>Absents aujourd’hui</strong> (vs outils type Make / chatbots classiques) : appel
                HTTP sortant, nœud « définir variable » hors choix interactif, tags sans handoff (le
                handoff coupe le bot ; <code className="playground-help-pop__code">tagsText</code> n’est
                pas appliqué côté serveur), envoi média natif (hors contenu prévu par un template Meta).
              </p>
            </div>
          </details>
        </div>

        <div
          className="playground-compact__row playground-compact__row--blocks"
          role="toolbar"
          aria-label="Ajouter des blocs au scénario"
        >
          <span className="playground-compact__tag" aria-hidden>
            Envoi
          </span>
          <button type="button" className="playground-chip" onClick={() => addNode("start")}>
            Entrée
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("sendText")}>
            Texte
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("sendTemplate")}>
            Template
          </button>
          <span className="playground-compact__sep" aria-hidden />
          <span className="playground-compact__tag" aria-hidden>
            Parcours
          </span>
          <button type="button" className="playground-chip" onClick={() => addNode("gemini")}>
            Gemini
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("interactiveNode")}>
            Boutons
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("routerNode")}>
            Routeur
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("handoffNode")}>
            Handoff
          </button>
          <span className="playground-compact__sep" aria-hidden />
          <span className="playground-compact__tag" aria-hidden>
            Temps
          </span>
          <button type="button" className="playground-chip" onClick={() => addNode("delayNode")}>
            Délai
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("waitUntilNode")}>
            Date
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("timeWindowNode")}>
            Horaires
          </button>
          <button type="button" className="playground-chip" onClick={() => addNode("logicNode")}>
            Si / sinon
          </button>
        </div>
      </div>

      {showCopyModal ? (
        <div className="playground-modal-overlay" role="dialog">
          <div className="playground-modal">
            <h3 className="playground-modal__title">Copier vers un autre compte</h3>
            <label className="pg-modal__label">
              Compte WABA cible
              <select
                className="pg-modal__input"
                value={copyTargetAccount}
                onChange={(e) => setCopyTargetAccount(e.target.value)}
              >
                {accountsList.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name || a.slug || a.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="pg-modal__label playground-modal__check">
              <input
                type="checkbox"
                checked={copySubgraphOnly}
                onChange={(e) => setCopySubgraphOnly(e.target.checked)}
              />
              Copier uniquement les nœuds sélectionnés (série de blocs)
            </label>
            <div className="playground-modal__actions">
              <button type="button" className="ghost" onClick={() => setShowCopyModal(false)}>
                Annuler
              </button>
              <button type="button" className="ghost" onClick={runCopyToAccount}>
                Copier
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="playground-editor">
        <PlaygroundGraphContext.Provider value={nodes}>
          <OpenNodeSettingsContext.Provider value={openNodeSettings}>
            <DetachHandleContext.Provider value={detachAtHandle}>
              <PatchNodeContext.Provider value={patchNode}>
                <DeleteNodeContext.Provider value={deleteNode}>
                  <TemplatesContext.Provider value={templatesValue}>
                    <VarListContext.Provider value={varListValue}>
                      <div className="playground-flow-wrap">
                        <ReactFlow
                          nodes={nodes}
                          edges={edges}
                          onNodesChange={onNodesChange}
                          onEdgesChange={onEdgesChange}
                          onConnect={onConnect}
                          onReconnect={onReconnect}
                          onReconnectEnd={onReconnectEnd}
                          reconnectRadius={16}
                          nodeTypes={playgroundNodeTypes}
                          fitView
                          fitViewOptions={{ padding: 0.2 }}
                          deleteKeyCode={["Backspace", "Delete"]}
                          minZoom={0.35}
                          maxZoom={1.5}
                          proOptions={{ hideAttribution: true }}
                          selectionOnDrag
                          panOnDrag={[1, 2]}
                        >
                          <Background gap={18} size={1} />
                          <Controls showZoom showFitView showInteractive={false} />
                          <MiniMap
                            className="playground-minimap"
                            zoomable
                            pannable
                          />
                        </ReactFlow>
                      </div>
                      <NodeSettingsModal
                        node={settingsNode}
                        open={Boolean(settingsNodeId && settingsNode)}
                        onClose={() => setSettingsNodeId(null)}
                        patchNode={patchNode}
                      />
                    </VarListContext.Provider>
                  </TemplatesContext.Provider>
                </DeleteNodeContext.Provider>
              </PatchNodeContext.Provider>
            </DetachHandleContext.Provider>
          </OpenNodeSettingsContext.Provider>
        </PlaygroundGraphContext.Provider>
      </div>
      </div>
      <PlaygroundAssistantChat
        accountId={accountId}
        flowId={activeFlowId}
        flowName={flowName}
        disabled={flowsLoading || !activeFlowId}
        getGraphSnapshot={getGraphSnapshot}
        onApplyGraph={applyGraph}
      />
    </div>
  );
}

export default function FlowEditor({ accountId }) {
  return (
    <ReactFlowProvider>
      <FlowEditorInner accountId={accountId} />
    </ReactFlowProvider>
  );
}
