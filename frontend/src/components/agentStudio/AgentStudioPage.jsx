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

const ERROR_DETAIL_FR = {
  permission_denied: "Acces refuse.",
  invalid_release_mode: "Mode de deploiement invalide.",
  config_not_found: "Configuration introuvable.",
  account_required_for_approve: "Compte requis pour valider cette action.",
  user_required_for_approve_block: "Validation utilisateur requise pour cette action sensible.",
  primary_goal_required: "Objectif principal requis.",
  confidence_threshold_invalid: "Le seuil de confiance doit etre entre 0 et 1.",
  unknown_allowed_tools: "Certains outils autorises sont inconnus.",
  unknown_require_approval_tools: "Certains outils a approbation obligatoire sont inconnus.",
  require_approval_not_in_allowed_tools: "Les outils a approuver doivent aussi etre dans la liste des outils autorises.",
  sensitive_tools_must_require_approval: "Les outils sensibles doivent obligatoirement demander une validation humaine.",
  canary_percent_required: "Le pourcentage Canary est requis pour un deploiement Canary.",
  no_tests_defined_for_active_agent: "Aucun test defini pour un agent actif.",
};

function toFrenchErrorMessage(error, fallbackMessage) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return ERROR_DETAIL_FR[detail] || detail.replaceAll("_", " ");
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return "Erreur de validation des donnees envoyees.";
  }
  const msg = String(error?.message || "").trim().toLowerCase();
  if (msg.includes("network")) return "Erreur reseau. Verifie la connexion.";
  if (msg.includes("timeout")) return "Le serveur met trop de temps a repondre.";
  return fallbackMessage;
}

function translateIssueMessage(issue) {
  const code = String(issue?.message || "").trim();
  if (!code) return "Erreur de validation.";
  if (ERROR_DETAIL_FR[code]) {
    const details = String(issue?.details || "").trim();
    return details ? `${ERROR_DETAIL_FR[code]} (${details})` : ERROR_DETAIL_FR[code];
  }
  if (code.startsWith("intent_")) return "Une regle d intention est invalide ou incomplete.";
  if (code.startsWith("test_")) return "Un cas de test est invalide ou incomplet.";
  return code.replaceAll("_", " ");
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
  const [tourStep, setTourStep] = useState(-1);
  const [tourPosition, setTourPosition] = useState(null);

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
      setStatus(toFrenchErrorMessage(e, "Chargement impossible."));
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
      setStatus(toFrenchErrorMessage(e, "Echec de sauvegarde."));
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
        const messages = (res.data?.issues || []).map((i) => translateIssueMessage(i)).join(" | ");
        setStatus(`Validation backend: ${messages || "Aucune information supplementaire."}`);
      }
    } catch (e) {
      setStatus(toFrenchErrorMessage(e, "Validation impossible."));
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
      setStatus(toFrenchErrorMessage(e, "Simulation impossible."));
    }
  }, [activeId, simulateInput, accountId]);

  const loadRuntime = useCallback(async () => {
    if (!activeId) return;
    try {
      const res = await getAgentStudioRuntimeGraph(activeId);
      setRuntimeGraph(res.data?.graph || null);
    } catch (e) {
      setStatus(toFrenchErrorMessage(e, "Preview runtime indisponible."));
    }
  }, [activeId]);

  const deployCanary = useCallback(async () => {
    if (!activeId) return;
    const canary = Number(config.deployment.canaryPercent || 10);
    try {
      await deployAgentStudioCanary(activeId, canary);
      setStatus("Canary active.");
      await loadConfigs();
    } catch (e) {
      setStatus(toFrenchErrorMessage(e, "Impossible de deployer le canary."));
    }
  }, [activeId, config.deployment.canaryPercent, loadConfigs]);

  const activate = useCallback(async () => {
    if (!activeId) return;
    try {
      await activateAgentStudio(activeId);
      await setAgentStudioDefault(activeId);
      setStatus("Agent active et defini par defaut.");
      await loadConfigs();
    } catch (e) {
      setStatus(toFrenchErrorMessage(e, "Impossible d activer cet agent."));
    }
  }, [activeId, loadConfigs]);

  const pause = useCallback(async () => {
    if (!activeId) return;
    try {
      await pauseAgentStudio(activeId);
      setStatus("Agent mis en pause.");
      await loadConfigs();
    } catch (e) {
      setStatus(toFrenchErrorMessage(e, "Impossible de mettre cet agent en pause."));
    }
  }, [activeId, loadConfigs]);

  const patchConfig = useCallback((partial) => {
    setConfig((prev) => normalizeAgentStudioConfig({ ...prev, ...partial }));
  }, []);

  const canWrite = !disabled && Boolean(accountId);
  const isTourOpen = tourStep >= 0;
  const tourSteps = useMemo(
    () => [
      {
        selector: ".agent-studio__header",
        title: "En-tete",
        body: "Choisis le compte, cree un nouvel agent et enregistre les brouillons ici.",
      },
      {
        selector: ".agent-studio__sidebar",
        title: "Liste des agents",
        body: "Retrouve les agents du compte et charge leur configuration existante.",
      },
      {
        selector: ".agent-studio__tabs",
        title: "Onglets de configuration",
        body: "Objectif, regles, capacites, tests, deploiement et vue avancee.",
      },
      {
        selector: ".agent-studio__footer",
        title: "Validation rapide",
        body: "Les erreurs locales s affichent ici avant de lancer la validation backend.",
      },
    ],
    []
  );

  useEffect(() => {
    if (!isTourOpen) {
      setTourPosition(null);
      return;
    }
    const step = tourSteps[tourStep];
    if (!step) {
      setTourPosition(null);
      return;
    }

    let currentTarget = null;
    const updateTourPosition = () => {
      const el = document.querySelector(step.selector);
      if (!el) return;
      if (currentTarget && currentTarget !== el) {
        currentTarget.classList.remove("agent-studio__tour-target");
      }
      currentTarget = el;
      currentTarget.classList.add("agent-studio__tour-target");
      const rect = el.getBoundingClientRect();
      setTourPosition({
        top: Math.min(rect.bottom + 12, window.innerHeight - 180),
        left: Math.max(12, Math.min(rect.left, window.innerWidth - 360)),
      });
    };

    updateTourPosition();
    window.addEventListener("resize", updateTourPosition);
    window.addEventListener("scroll", updateTourPosition, true);
    return () => {
      if (currentTarget) {
        currentTarget.classList.remove("agent-studio__tour-target");
      }
      window.removeEventListener("resize", updateTourPosition);
      window.removeEventListener("scroll", updateTourPosition, true);
    };
  }, [isTourOpen, tourStep, tourSteps]);

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
          <button
            type="button"
            onClick={() => {
              setTourStep(0);
            }}
          >
            Parcours
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
      {isTourOpen ? (
        <>
          <div className="agent-studio__tour-backdrop" />
          <div
            className="agent-studio__tour-popover"
            style={{
              top: `${tourPosition?.top ?? 24}px`,
              left: `${tourPosition?.left ?? 24}px`,
            }}
          >
            <p className="agent-studio__tour-kicker">
              Etape {tourStep + 1}/{tourSteps.length}
            </p>
            <h4>{tourSteps[tourStep]?.title}</h4>
            <p>{tourSteps[tourStep]?.body}</p>
            <div className="agent-studio__tour-actions">
              <button
                type="button"
                onClick={() => setTourStep((prev) => Math.max(0, prev - 1))}
                disabled={tourStep <= 0}
              >
                Precedent
              </button>
              {tourStep < tourSteps.length - 1 ? (
                <button type="button" onClick={() => setTourStep((prev) => prev + 1)}>
                  Suivant
                </button>
              ) : (
                <button type="button" onClick={() => setTourStep(-1)}>
                  Terminer
                </button>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

