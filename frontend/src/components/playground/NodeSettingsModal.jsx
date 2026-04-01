import { useEffect } from "react";
import { createPortal } from "react-dom";
import { FiX } from "react-icons/fi";
import {
  StartSettingsForm,
  SendTextSettingsForm,
  SendTemplateSettingsForm,
  GeminiSettingsForm,
  DelaySettingsForm,
  WaitUntilSettingsForm,
  TimeWindowSettingsForm,
  LogicSettingsForm,
  InteractiveSettingsForm,
  RouterSettingsForm,
  HandoffSettingsForm,
} from "./nodeSettingsForms";

const TITLES = {
  start: "Déclencheur",
  sendText: "Message",
  sendTemplate: "Template",
  gemini: "Gemini",
  interactiveNode: "Interactif",
  routerNode: "Routeur",
  handoffNode: "Handoff",
  delayNode: "Délai",
  waitUntilNode: "Jusqu’à date",
  timeWindowNode: "Fenêtre horaire",
  logicNode: "Logique",
};

function renderForm(node, patchNode) {
  if (!node) return null;
  const { id, type, data } = node;
  const patch = (nid, partial) => patchNode(nid, partial);
  switch (type) {
    case "start":
      return <StartSettingsForm id={id} data={data} patch={patch} />;
    case "sendText":
      return <SendTextSettingsForm id={id} data={data} patch={patch} />;
    case "sendTemplate":
      return <SendTemplateSettingsForm id={id} data={data} patch={patch} />;
    case "gemini":
      return <GeminiSettingsForm id={id} data={data} patch={patch} />;
    case "interactiveNode":
      return <InteractiveSettingsForm id={id} data={data} patch={patch} />;
    case "routerNode":
      return <RouterSettingsForm id={id} data={data} patch={patch} />;
    case "handoffNode":
      return <HandoffSettingsForm id={id} data={data} patch={patch} />;
    case "delayNode":
      return <DelaySettingsForm id={id} data={data} patch={patch} />;
    case "waitUntilNode":
      return <WaitUntilSettingsForm id={id} data={data} patch={patch} />;
    case "timeWindowNode":
      return <TimeWindowSettingsForm id={id} data={data} patch={patch} />;
    case "logicNode":
      return <LogicSettingsForm id={id} data={data} patch={patch} />;
    default:
      return <p className="muted">Type non géré.</p>;
  }
}

export default function NodeSettingsModal({ node, open, onClose, patchNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !node) return null;

  const title = TITLES[node.type] || node.type;

  return createPortal(
    <div className="pg-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="pg-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pg-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="pg-modal__header">
          <h3 id="pg-modal-title">{title}</h3>
          <button
            type="button"
            className="pg-modal__close"
            aria-label="Fermer"
            onClick={onClose}
          >
            <FiX />
          </button>
        </header>
        <div className="pg-modal__body">{renderForm(node, patchNode)}</div>
      </div>
    </div>,
    document.body
  );
}
