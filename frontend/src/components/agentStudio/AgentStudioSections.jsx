import { useMemo } from "react";

function parseIntents(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, idx) => {
      const [key, handler, description] = line.split("|").map((x) => String(x || "").trim());
      return {
        key: key || `intent_${idx + 1}`,
        handler: handler || "GenericAgent",
        description: description || "",
      };
    });
}

function stringifyIntents(intents) {
  return (Array.isArray(intents) ? intents : [])
    .map((it) => `${it.key || ""} | ${it.handler || ""} | ${it.description || ""}`)
    .join("\n");
}

export function ObjectiveSection({ config, patchConfig, canWrite, parseLines, stringifyLines }) {
  return (
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
      <label>
        Audience (optionnel)
        <input
          value={config.objective.audience || ""}
          onChange={(e) =>
            patchConfig({
              objective: { ...config.objective, audience: e.target.value },
            })
          }
          disabled={!canWrite}
        />
      </label>
    </section>
  );
}

export function PolicySection({ config, patchConfig, canWrite, parseLines, stringifyLines }) {
  return (
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
        Intentions (1 ligne = key | handler | description)
        <textarea
          rows={6}
          value={stringifyIntents(config.routing.intents)}
          onChange={(e) =>
            patchConfig({
              routing: { ...config.routing, intents: parseIntents(e.target.value) },
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
  );
}

export function CapabilitiesSection({ config, patchConfig, canWrite, parseLines, stringifyLines }) {
  return (
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
  );
}

export function TestsSection({
  config,
  patchConfig,
  canWrite,
  parseLines,
  simulateInput,
  setSimulateInput,
  runSimulation,
  simulateResult,
  activeId,
}) {
  const testText = useMemo(
    () =>
      (config.tests || [])
        .map((t) => `${t.input || ""} => ${t.expectedBehavior || ""}`)
        .join("\n"),
    [config.tests]
  );

  return (
    <section className="agent-studio__panel">
      <label>
        Cas de tests (format: input =&gt; expected_behavior)
        <textarea
          rows={8}
          value={testText}
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
      <p className="agent-studio__help-text">
        La simulation applique une <strong>règle simple</strong> (pas le LLM) : pour chaque ligne dans
        « Intentions » (onglet Règles), soit la <strong>clé</strong> apparaît dans le message du client
        (texte en minuscules), soit un <strong>mot de la description</strong> (plus de 3 lettres) est
        trouvé dans le message. Si <strong>aucune intention</strong> ne correspond - ou si la liste est
        vide - le résultat est toujours <code>fallback</code> avec la stratégie configurée (ex.{' '}
        <code>human</code>). « Bonjour » sans intention qui matche retombe donc sur le fallback : ce n'est
        pas une panne du simulateur.
      </p>
      {simulateResult ? (
        <pre className="agent-studio__pre">{JSON.stringify(simulateResult, null, 2)}</pre>
      ) : null}
    </section>
  );
}

export function DeploySection({
  config,
  patchConfig,
  canWrite,
  runServerValidation,
  deployCanary,
  activate,
  pause,
  activeId,
}) {
  return (
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
      <p className="agent-studio__help-text">
        <strong>Canary %</strong> : pourcentage cible pour une mise en production progressive (« canary »).
        Très utilisé en ingénierie pour router une <strong>fraction du trafic</strong> vers une nouvelle
        version avant généralisation. Ici la valeur est stockée dans la config et utilisée lors du déploiement
        canary ; le routage réel côté WhatsApp peut encore dépendre de l'intégration runtime du compte.
      </p>
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
      <p className="agent-studio__help-text">
        <strong>Valider (backend)</strong> : vérifie la config sur le serveur (schéma / cohérence) sans la
        déployer. <strong>Déployer canary</strong> : enregistre une release « canary » avec le % ci-dessus si
        la config est déployable. <strong>Activer</strong> : passage en production (release activate, agent
        défaut). <strong>Pause</strong> : met l'agent en pause (release pause).
      </p>
    </section>
  );
}

export function AdvancedSection({ activeId, loadRuntime, runtimeGraph }) {
  return (
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
  );
}

