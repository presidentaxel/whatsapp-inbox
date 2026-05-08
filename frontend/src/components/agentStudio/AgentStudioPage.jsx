import { useCallback, useEffect, useMemo, useState } from "react";
import {
  activateAgentStudio,
  createAgentStudioConfig,
  deployAgentStudioCanary,
  getAgentStudioRuntimeGraph,
  listAgentStudioConfigs,
  pauseAgentStudio,
  setAgentStudioDefault,
  simulateAgentStudioConfig,
  updateAgentStudioConfig,
  validateAgentStudioConfig as validateServerAgentConfig,
} from "../../api/agentStudioApi";
import {
  createDefaultAgentStudioConfig,
  normalizeAgentStudioConfig,
  validateAgentStudioConfig,
} from "./agentStudioModel";
import {
  AdvancedSection,
  CapabilitiesSection,
  DeploySection,
  ObjectiveSection,
  PolicySection,
  TestsSection,
} from "./AgentStudioSections";

import "./agentStudio.css";

function parseLines(text) {
  return String(text || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
}

function stringifyLines(values) {
  return Array.isArray(values) ? values.join("\n") : "";
}

export default function AgentStudioPage({ accountId, accounts, onAccountChange, disabled }) {
  const [items, setItems] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [config, setConfig] = useState(createDefaultAgentStudioConfig());
  const [tab, setTab] = useState("objective");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [simulateInput, setSimulateInput] = useState("");
  const [simulateResult, setSimulateResult] = useState(null);
  const [runtimeGraph, setRuntimeGraph] = useState(null);

  const localIssues = useMemo(() => validateAgentStudioConfig(config), [config]);

  const activeItem = useMemo(
    () => items.find((x) => String(x.id) === String(activeId)) || null,
    [items, activeId]
  );

  const loadConfigs = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    setStatus("");
    try {
      const res = await listAgentStudioConfigs(accountId);
      const list = Array.isArray(res.data?.items) ? res.data.items : [];
      setItems(list);
      const picked = list.find((x) => x.is_default) || list[0] || null;
      if (picked) {
        setActiveId(picked.id);
        setConfig(normalizeAgentStudioConfig(picked.config));
      } else {
        setActiveId(null);
        setConfig(createDefaultAgentStudioConfig());
      }
    } catch (e) {
      setStatus(e?.response?.data?.detail || e?.message || "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    void loadConfigs();
  }, [loadConfigs]);

  const saveCurrent = useCallback(async () => {
    if (!accountId) return;
    setSaving(true);
    setStatus("");
    try {
      const payload = { account_id: accountId, config };
      if (activeId) {
        const res = await updateAgentStudioConfig(activeId, payload);
        const row = res.data;
        setItems((prev) => prev.map((x) => (x.id === row.id ? row : x)));
      } else {
        const res = await createAgentStudioConfig(payload);
        const row = res.data;
        setItems((prev) => [row, ...prev]);
        setActiveId(row.id);
      }
      setStatus("Brouillon enregistré.");
    } catch (e) {
      setStatus(e?.response?.data?.detail || e?.message || "Échec de sauvegarde.");
    } finally {
      setSaving(false);
    }
  }, [accountId, activeId, config]);

  const runServerValidation = useCallback(async () => {
    if (!activeId) return;
    setStatus("");
    try {
      const res = await validateServerAgentConfig(activeId);
      if (res.data?.ok) {
        setStatus("Validation backend OK.");
      } else {
        const messages = (res.data?.issues || []).map((i) => i.message).join(" | ");
        setStatus(`Validation backend: ${messages || "issues"}`);
      }
    } catch (e) {
      setStatus(e?.response?.data?.detail || e?.message || "Validation impossible.");
    }
  }, [activeId]);

  const runSimulation = useCallback(async () => {
    if (!activeId || !simulateInput.trim()) return;
    try {
      const res = await simulateAgentStudioConfig(activeId, {
        account_id: accountId,
        input_text: simulateInput,
      });
      setSimulateResult(res.data?.simulation || null);
    } catch (e) {
      setStatus(e?.response?.data?.detail || e?.message || "Simulation impossible.");
    }
  }, [activeId, simulateInput, accountId]);

  const loadRuntime = useCallback(async () => {
    if (!activeId) return;
    try {
      const res = await getAgentStudioRuntimeGraph(activeId);
      setRuntimeGraph(res.data?.graph || null);
    } catch (e) {
      setStatus(e?.response?.data?.detail || e?.message || "Preview runtime indisponible.");
    }
  }, [activeId]);

  const deployCanary = useCallback(async () => {
    if (!activeId) return;
    const canary = Number(config.deployment.canaryPercent || 10);
    await deployAgentStudioCanary(activeId, canary);
    setStatus("Canary activé.");
    await loadConfigs();
  }, [activeId, config.deployment.canaryPercent, loadConfigs]);

  const activate = useCallback(async () => {
    if (!activeId) return;
    await activateAgentStudio(activeId);
    await setAgentStudioDefault(activeId);
    setStatus("Agent activé et défini par défaut.");
    await loadConfigs();
  }, [activeId, loadConfigs]);

  const pause = useCallback(async () => {
    if (!activeId) return;
    await pauseAgentStudio(activeId);
    setStatus("Agent mis en pause.");
    await loadConfigs();
  }, [activeId, loadConfigs]);

  const patchConfig = useCallback((partial) => {
    setConfig((prev) => normalizeAgentStudioConfig({ ...prev, ...partial }));
  }, []);

  const canWrite = !disabled && Boolean(accountId);

  return (
    <div className="agent-studio">
      <header className="agent-studio__header">
        <div>
          <h2>Agent Studio</h2>
          <p>Concevoir, tester et déployer un agent robuste sans maintenir un graphe complexe à la main.</p>
        </div>
        <div className="agent-studio__header-actions">
          {accounts?.length > 0 ? (
            <select value={accountId ?? ""} onChange={(e) => onAccountChange?.(e.target.value)}>
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name}
                </option>
              ))}
            </select>
          ) : null}
          <button type="button" onClick={() => setConfig(createDefaultAgentStudioConfig())} disabled={!canWrite}>
            Nouveau
          </button>
          <button type="button" onClick={() => void saveCurrent()} disabled={!canWrite || saving}>
            {saving ? "Enregistrement..." : "Enregistrer"}
          </button>
        </div>
      </header>

      <section className="agent-studio__layout">
        <aside className="agent-studio__sidebar">
          <h3>Agents du compte</h3>
          {loading ? <p>Chargement...</p> : null}
          <ul>
            {items.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  className={String(activeId) === String(it.id) ? "is-active" : ""}
                  onClick={() => {
                    setActiveId(it.id);
                    setConfig(normalizeAgentStudioConfig(it.config));
                  }}
                >
                  {it.config?.name || "Agent"} {it.is_default ? "(défaut)" : ""}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="agent-studio__main">
          <nav className="agent-studio__tabs">
            {[
              ["objective", "Objectif"],
              ["policy", "Règles"],
              ["capabilities", "Capacités"],
              ["tests", "Tests"],
              ["deploy", "Déploiement"],
              ["advanced", "Avancé"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={tab === id ? "is-active" : ""}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </nav>

          {tab === "objective" ? (
            <ObjectiveSection
              config={config}
              patchConfig={patchConfig}
              canWrite={canWrite}
              parseLines={parseLines}
              stringifyLines={stringifyLines}
            />
          ) : null}

          {tab === "policy" ? (
            <PolicySection
              config={config}
              patchConfig={patchConfig}
              canWrite={canWrite}
              parseLines={parseLines}
              stringifyLines={stringifyLines}
            />
          ) : null}

          {tab === "capabilities" ? (
            <CapabilitiesSection
              config={config}
              patchConfig={patchConfig}
              canWrite={canWrite}
              parseLines={parseLines}
              stringifyLines={stringifyLines}
            />
          ) : null}

          {tab === "tests" ? (
            <TestsSection
              config={config}
              patchConfig={patchConfig}
              canWrite={canWrite}
              parseLines={parseLines}
              simulateInput={simulateInput}
              setSimulateInput={setSimulateInput}
              runSimulation={runSimulation}
              simulateResult={simulateResult}
              activeId={activeId}
            />
          ) : null}

          {tab === "deploy" ? (
            <DeploySection
              config={config}
              patchConfig={patchConfig}
              canWrite={canWrite}
              runServerValidation={runServerValidation}
              deployCanary={deployCanary}
              activate={activate}
              pause={pause}
              activeId={activeId}
            />
          ) : null}

          {tab === "advanced" ? (
            <AdvancedSection
              activeId={activeId}
              loadRuntime={loadRuntime}
              runtimeGraph={runtimeGraph}
            />
          ) : null}

          <footer className="agent-studio__footer">
            <div>
              {localIssues.length ? (
                <ul>
                  {localIssues.map((it, idx) => (
                    <li key={`${it.message}-${idx}`} className={`issue-${it.severity}`}>
                      {it.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <span>Aucun problème local détecté.</span>
              )}
            </div>
            <span>{status}</span>
            {activeItem?.is_default ? <span>Agent par défaut</span> : null}
          </footer>
        </main>
      </section>
    </div>
  );
}

