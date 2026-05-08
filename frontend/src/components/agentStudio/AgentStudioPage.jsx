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
            <section className="agent-studio__panel">
              <label>
                Nom agent
                <input
                  value={config.name}
                  onChange={(e) => patchConfig({ name: e.target.value })}
                  disabled={!canWrite}
                />
              </label>
              <label>
                Objectif principal
                <textarea
                  rows={3}
                  value={config.objective.primaryGoal}
                  onChange={(e) =>
                    patchConfig({
                      objective: { ...config.objective, primaryGoal: e.target.value },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
              <label>
                KPI (1 ligne = 1 KPI)
                <textarea
                  rows={4}
                  value={stringifyLines(config.objective.kpi)}
                  onChange={(e) =>
                    patchConfig({
                      objective: { ...config.objective, kpi: parseLines(e.target.value) },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
            </section>
          ) : null}

          {tab === "policy" ? (
            <section className="agent-studio__panel">
              <label>
                Fallback
                <select
                  value={config.routing.fallback}
                  onChange={(e) =>
                    patchConfig({ routing: { ...config.routing, fallback: e.target.value } })
                  }
                  disabled={!canWrite}
                >
                  <option value="human">Escalade humain</option>
                  <option value="safe_reply">Réponse sûre</option>
                  <option value="ask_clarification">Demande de clarification</option>
                </select>
              </label>
              <label>
                Seuil de confiance
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={config.routing.confidenceThreshold}
                  onChange={(e) =>
                    patchConfig({
                      routing: {
                        ...config.routing,
                        confidenceThreshold: Number(e.target.value),
                      },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
              <label>
                Actions interdites (1 ligne = 1 action)
                <textarea
                  rows={4}
                  value={stringifyLines(config.policies.forbiddenActions)}
                  onChange={(e) =>
                    patchConfig({
                      policies: {
                        ...config.policies,
                        forbiddenActions: parseLines(e.target.value),
                      },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
            </section>
          ) : null}

          {tab === "capabilities" ? (
            <section className="agent-studio__panel">
              <label>
                Tools autorisés (1 ligne = 1 tool)
                <textarea
                  rows={6}
                  value={stringifyLines(config.capabilities.allowedTools)}
                  onChange={(e) =>
                    patchConfig({
                      capabilities: {
                        ...config.capabilities,
                        allowedTools: parseLines(e.target.value),
                      },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
              <label>
                Tools avec approbation obligatoire
                <textarea
                  rows={6}
                  value={stringifyLines(config.capabilities.requireApprovalFor)}
                  onChange={(e) =>
                    patchConfig({
                      capabilities: {
                        ...config.capabilities,
                        requireApprovalFor: parseLines(e.target.value),
                      },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
            </section>
          ) : null}

          {tab === "tests" ? (
            <section className="agent-studio__panel">
              <label>
                Cas de tests (format: input => expected_behavior)
                <textarea
                  rows={8}
                  value={(config.tests || [])
                    .map((t) => `${t.input || ""} => ${t.expectedBehavior || ""}`)
                    .join("\n")}
                  onChange={(e) =>
                    patchConfig({
                      tests: parseLines(e.target.value).map((line, idx) => {
                        const [left, right] = line.split("=>");
                        return {
                          id: `t${idx + 1}`,
                          input: String(left || "").trim(),
                          expectedBehavior: String(right || "").trim(),
                          expectedRoute: null,
                        };
                      }),
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
              <div className="agent-studio__testbox">
                <input
                  value={simulateInput}
                  placeholder="Message client à simuler"
                  onChange={(e) => setSimulateInput(e.target.value)}
                />
                <button type="button" onClick={() => void runSimulation()} disabled={!activeId}>
                  Simuler
                </button>
              </div>
              {simulateResult ? (
                <pre className="agent-studio__pre">{JSON.stringify(simulateResult, null, 2)}</pre>
              ) : null}
            </section>
          ) : null}

          {tab === "deploy" ? (
            <section className="agent-studio__panel">
              <label>
                Statut
                <select
                  value={config.deployment.status}
                  onChange={(e) =>
                    patchConfig({
                      deployment: { ...config.deployment, status: e.target.value },
                    })
                  }
                  disabled={!canWrite}
                >
                  <option value="draft">Draft</option>
                  <option value="canary">Canary</option>
                  <option value="active">Active</option>
                  <option value="paused">Paused</option>
                </select>
              </label>
              <label>
                Canary %
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={config.deployment.canaryPercent || ""}
                  onChange={(e) =>
                    patchConfig({
                      deployment: {
                        ...config.deployment,
                        canaryPercent: e.target.value ? Number(e.target.value) : null,
                      },
                    })
                  }
                  disabled={!canWrite}
                />
              </label>
              <div className="agent-studio__actions-row">
                <button type="button" onClick={() => void runServerValidation()} disabled={!activeId}>
                  Valider (backend)
                </button>
                <button type="button" onClick={() => void deployCanary()} disabled={!activeId || !canWrite}>
                  Déployer canary
                </button>
                <button type="button" onClick={() => void activate()} disabled={!activeId || !canWrite}>
                  Activer
                </button>
                <button type="button" onClick={() => void pause()} disabled={!activeId || !canWrite}>
                  Pause
                </button>
              </div>
            </section>
          ) : null}

          {tab === "advanced" ? (
            <section className="agent-studio__panel">
              <div className="agent-studio__actions-row">
                <button type="button" onClick={() => void loadRuntime()} disabled={!activeId}>
                  Générer preview runtime
                </button>
              </div>
              {runtimeGraph ? (
                <pre className="agent-studio__pre">{JSON.stringify(runtimeGraph, null, 2)}</pre>
              ) : (
                <p>Aucune preview chargée.</p>
              )}
            </section>
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

