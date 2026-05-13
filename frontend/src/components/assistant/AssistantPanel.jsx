import { useEffect, useState } from "react";
import GeminiPanel from "../bot/GeminiPanel";
import PlaygroundPanel from "../playground/PlaygroundPanel";

const ASSISTANT_TAB_KEY = "whatsapp-inbox.assistant-tab";

function readStoredAssistantTab() {
  try {
    const v = localStorage.getItem(ASSISTANT_TAB_KEY);
    if (v === "playground" || v === "gemini") return v;
  } catch {
    /* private mode / indisponible */
  }
  return "gemini";
}

export default function AssistantPanel({
  accountId,
  accounts,
  onAccountChange,
}) {
  const [tab, setTab] = useState(readStoredAssistantTab);
  const playground = tab === "playground";

  useEffect(() => {
    try {
      localStorage.setItem(ASSISTANT_TAB_KEY, tab);
    } catch {
      /* ignore */
    }
  }, [tab]);

  return (
    <div
      className={`assistant-hub ${playground ? "assistant-hub--playground-active" : ""}`}
    >
      <div
        className="assistant-hub__tabs"
        role="tablist"
        aria-label="Mode assistant"
      >
        <div className="assistant-hub__tabs-main">
          <button
            type="button"
            role="tab"
            aria-selected={!playground}
            className={`assistant-hub__tab ${!playground ? "is-active" : ""}`}
            onClick={() => setTab("gemini")}
          >
            Gemini
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={playground}
            className={`assistant-hub__tab ${playground ? "is-active" : ""}`}
            onClick={() => setTab("playground")}
          >
            Playground
          </button>
        </div>
        {accounts?.length > 0 && (
          <div className="assistant-hub__account">
            <label htmlFor="assistant-hub-account">Compte</label>
            <select
              id="assistant-hub-account"
              value={accountId ?? ""}
              onChange={(e) => onAccountChange?.(e.target.value)}
            >
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div
        className="assistant-hub__body"
        role="tabpanel"
        hidden={tab !== "gemini"}
      >
        <GeminiPanel
          accountId={accountId}
          accounts={accounts}
          onAccountChange={onAccountChange}
          hideAccountSelector
        />
      </div>

      <div
        className="assistant-hub__body assistant-hub__body--playground"
        role="tabpanel"
        hidden={tab !== "playground"}
      >
        <PlaygroundPanel accountId={accountId} />
      </div>
    </div>
  );
}
