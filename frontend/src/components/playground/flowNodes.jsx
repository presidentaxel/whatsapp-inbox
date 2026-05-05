import { memo, useContext } from "react";
import { Handle, Position } from "@xyflow/react";
import { FiTrash2, FiSettings } from "react-icons/fi";
import {
  DeleteNodeContext,
  OpenNodeSettingsContext,
  DetachHandleContext,
} from "./flowContext";
import {
  summarizeStart,
  summarizeTimeWindow,
  summarizeWaitUntilCanvas,
  truncate,
  unitLabel,
} from "./nodeShared";

const handleStyle = { width: 8, height: 8 };

const DetachableHandle = memo(function DetachableHandle({ nodeId, type, id, onDoubleClick, title, ...rest }) {
  const detachAt = useContext(DetachHandleContext);
  return (
    <Handle
      type={type}
      id={id}
      {...rest}
      title={
        title ??
        "Double-clic pour décrocher les liaisons sur ce point"
      }
      onDoubleClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
        detachAt({
          nodeId,
          handleId: id ?? null,
          handleType: type,
        });
        onDoubleClick?.(e);
      }}
    />
  );
});

function NodeDeleteBtn({ id }) {
  const del = useContext(DeleteNodeContext);
  return (
    <button
      type="button"
      className="pg-node__iconbtn pg-node__iconbtn--danger"
      aria-label="Supprimer"
      onClick={(e) => {
        e.stopPropagation();
        del(id);
      }}
    >
      <FiTrash2 />
    </button>
  );
}

const NodeCompactChrome = memo(function NodeCompactChrome({
  id,
  selected,
  className,
  badge,
  title,
  subtitle,
  codeShort,
  deleteDisabled,
  top,
  bottom,
  footer,
}) {
  const openSettings = useContext(OpenNodeSettingsContext);
  return (
    <div
      className={`pg-node pg-node--compact ${className || ""} ${
        selected ? "is-selected" : ""
      }`}
    >
      {top}
      <div className="pg-node__compact-toolbar">
        <span className="pg-node__compact-badge">{badge}</span>
        <div className="pg-node__compact-actions">
          <button
            type="button"
            className="pg-node__iconbtn"
            aria-label="Paramètres"
            onClick={(e) => {
              e.stopPropagation();
              openSettings(id);
            }}
          >
            <FiSettings />
          </button>
          {!deleteDisabled && <NodeDeleteBtn id={id} />}
        </div>
      </div>
      <div className="pg-node__compact-main">
        <div className="pg-node__compact-title">{title}</div>
        {subtitle ? (
          <div className="pg-node__compact-sub" title={subtitle}>
            {subtitle}
          </div>
        ) : null}
        {codeShort ? (
          <code className="pg-node__compact-token">{codeShort}</code>
        ) : null}
      </div>
      {footer}
      {bottom}
    </div>
  );
});

function StartNode({ id, data, selected }) {
  const sub = summarizeStart(data);
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--start"
      badge="Entrée"
      title="Déclencheur"
      subtitle={sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      bottom={
        <DetachableHandle
          nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

function SendTextNode({ id, data, selected }) {
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--send"
      badge="Msg"
      title="Texte"
      subtitle={truncate(data.body, 48)}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      bottom={
        <DetachableHandle
          nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

const TEMPLATE_META_LABELS = {
  unknown: "État Meta ?",
  missing: "Absent sur Meta",
  pending_review: "En revue Meta",
  approved: "Approuvé",
  rejected: "Rejeté",
};

function SendTemplateNode({ id, data, selected }) {
  const name =
    data.templateName ||
    (data.selectedTemplateKey || "").split("||")[0] ||
    "-";
  const nBtn = data.quickReplyButtons?.length || 0;
  const hasQR = nBtn > 0;
  const sub = hasQR ? `${truncate(name, 28)} · ${nBtn} btn` : truncate(name, 36);
  const tStatus = data.templateStatus || "unknown";
  const metaClass = `pg-node__tpl-meta pg-node__tpl-meta--${tStatus}`;
  const metaText = TEMPLATE_META_LABELS[tStatus] || tStatus;
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--template"
      badge="Tpl"
      title="Template"
      subtitle={sub}
      footer={
        <div className="pg-node__tpl-footer">
          <span
            className={metaClass}
            title="Statut côté WhatsApp / Meta (éditable dans les paramètres du nœud)"
          >
            {metaText}
          </span>
          {hasQR ? (
            <div className="pg-node__compact-handles-hint pg-node__compact-handles-hint--split">
              <span>◀ après réponse</span>
              <span title="Branche si aucune réponse avant le délai configuré">
                timeout ▶
              </span>
            </div>
          ) : null}
        </div>
      }
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      bottom={
        hasQR ? (
          <>
            <DetachableHandle
              nodeId={id}
              type="source"
              position={Position.Bottom}
              style={{ ...handleStyle, left: "32%" }}
              isConnectable
            />
            <DetachableHandle
              nodeId={id}
              type="source"
              position={Position.Bottom}
              id="timeout"
              style={{ ...handleStyle, left: "68%" }}
              title="Relance si pas de réponse (délai dans les paramètres)"
              isConnectable
            />
          </>
        ) : (
          <DetachableHandle
            nodeId={id}
            type="source"
            position={Position.Bottom}
            style={handleStyle}
            isConnectable
          />
        )
      }
    />
  );
}

function GeminiNode({ id, data, selected }) {
  const intents = Array.isArray(data.intents) ? data.intents : [];
  const intentRows = intents.filter((x) => (x?.keyword || "").trim());
  const hasIntentOut = intentRows.length > 0;
  let sub = truncate(data.hint, 36) || "Gemini dans le scénario";
  if (hasIntentOut) {
    sub = `${intentRows.length} intention(s) · ${sub}`;
  }
  const nOut = intentRows.length + 1;
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--gemini"
      badge="IA"
      title="Bloc IA"
      subtitle={sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      footer={
        hasIntentOut ? (
          <div className="pg-node__compact-handles-hint pg-node__compact-handles-hint--split">
            <span>◀ mots-clés</span>
            <span>inconnu ▶</span>
          </div>
        ) : null
      }
      bottom={
        hasIntentOut ? (
          <>
            {intentRows.map((row, i) => (
              <DetachableHandle
                key={`${row.keyword}-${i}`}
                nodeId={id}
                type="source"
                position={Position.Bottom}
                id={`intent-${i}`}
                style={{
                  ...handleStyle,
                  left: `${((i + 1) / (nOut + 1)) * 100}%`,
                }}
                isConnectable
              />
            ))}
            <DetachableHandle
              nodeId={id}
              type="source"
              position={Position.Bottom}
              id="intent-unknown"
              style={{
                ...handleStyle,
                left: `${(nOut / (nOut + 1)) * 100}%`,
              }}
              isConnectable
            />
          </>
        ) : (
          <DetachableHandle
            nodeId={id}
            type="source"
            position={Position.Bottom}
            style={handleStyle}
            isConnectable
          />
        )
      }
    />
  );
}

function DelayNode({ id, data, selected }) {
  const u = unitLabel(data.unit || "s");
  const sub = `${data.duration ?? "?"} ${u}`;
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--delay"
      badge="⏱"
      title="Délai"
      subtitle={sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      bottom={
        <DetachableHandle nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

function WaitUntilNode({ id, data, selected }) {
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--waituntil"
      badge="📅"
      title="Jusqu’à"
      subtitle={summarizeWaitUntilCanvas(data)}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      bottom={
        <DetachableHandle nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

function TimeWindowNode({ id, data, selected }) {
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--timewindow"
      badge="🕐"
      title="Plage"
      subtitle={summarizeTimeWindow(data)}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      footer={
        <div className="pg-node__compact-handles-hint">
          <span>◀ dans</span>
          <span>hors ▶</span>
        </div>
      }
      bottom={
        <>
          <DetachableHandle nodeId={id}
            type="source"
            position={Position.Left}
            id="inside"
            style={{ ...handleStyle, top: "auto", bottom: 6, left: 8 }}
            isConnectable
          />
          <DetachableHandle nodeId={id}
            type="source"
            position={Position.Right}
            id="outside"
            style={{ ...handleStyle, top: "auto", bottom: 6, right: 8 }}
            isConnectable
          />
        </>
      }
    />
  );
}

function LogicNode({ id, data, selected }) {
  const mode = data.logicMode || "si";
  const modeLbl = mode.toUpperCase();
  let sub = "";
  if (mode === "si") sub = truncate(data.condition, 42) || "Expr…";
  else if (mode === "ou") sub = "2 branches";
  else sub = "2 entrées → 1 sortie";

  if (mode === "si") {
    return (
      <NodeCompactChrome
        id={id}
        selected={selected}
        className="pg-node--logic pg-node--logic-si"
        badge={modeLbl}
        title="Condition"
        subtitle={sub}
        codeShort={data.varKey ? `{{${data.varKey}}}` : null}
        top={
          <DetachableHandle nodeId={id}
            type="target"
            position={Position.Top}
            style={handleStyle}
            isConnectable
          />
        }
        footer={
          <div className="pg-node__compact-handles-hint">
            <span>◀ VRAI</span>
            <span>FAUX ▶</span>
          </div>
        }
        bottom={
          <>
            <DetachableHandle nodeId={id}
              type="source"
              position={Position.Left}
              id="true"
              style={{ ...handleStyle, top: "auto", bottom: 6, left: 8 }}
              isConnectable
            />
            <DetachableHandle nodeId={id}
              type="source"
              position={Position.Right}
              id="false"
              style={{ ...handleStyle, top: "auto", bottom: 6, right: 8 }}
              isConnectable
            />
          </>
        }
      />
    );
  }

  if (mode === "ou") {
    return (
      <NodeCompactChrome
        id={id}
        selected={selected}
        className="pg-node--logic pg-node--logic-ou"
        badge={modeLbl}
        title="Condition"
        subtitle={sub}
        codeShort={data.varKey ? `{{${data.varKey}}}` : null}
        top={
          <DetachableHandle nodeId={id}
            type="target"
            position={Position.Top}
            style={handleStyle}
            isConnectable
          />
        }
        footer={
          <div className="pg-node__compact-handles-hint pg-node__compact-handles-hint--split">
            <span>A</span>
            <span>B</span>
          </div>
        }
        bottom={
          <>
            <DetachableHandle nodeId={id}
              type="source"
              position={Position.Bottom}
              id="a"
              style={{ ...handleStyle, left: "30%" }}
              isConnectable
            />
            <DetachableHandle nodeId={id}
              type="source"
              position={Position.Bottom}
              id="b"
              style={{ ...handleStyle, left: "70%" }}
              isConnectable
            />
          </>
        }
      />
    );
  }

  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--logic pg-node--logic-et"
      badge={modeLbl}
      title="Condition"
      subtitle={sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      footer={
        <div className="pg-node__compact-handles-hint">
          <span>A · B</span>
        </div>
      }
      top={
        <>
          <DetachableHandle nodeId={id}
            type="target"
            position={Position.Top}
            id="inA"
            style={{ ...handleStyle, left: "25%" }}
            isConnectable
          />
          <DetachableHandle nodeId={id}
            type="target"
            position={Position.Top}
            id="inB"
            style={{ ...handleStyle, left: "75%" }}
            isConnectable
          />
        </>
      }
      bottom={
        <DetachableHandle nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

function InteractiveNode({ id, data, selected }) {
  const kind = data.uiKind === "list" ? "list" : "buttons";
  const choices = Array.isArray(data.choices) ? data.choices : [];
  const n = kind === "buttons" ? Math.min(choices.length, 3) : choices.length;
  const baseSub =
    kind === "buttons"
      ? `${n} bouton(s) · fenêtre 24h`
      : `${n} ligne(s) · liste`;
  const td = data.timeoutDuration != null && String(data.timeoutDuration).trim() !== "";
  const tu = (data.timeoutUnit || "h").trim();
  const timeoutLbl = td ? ` · relance ${data.timeoutDuration}${tu}` : "";
  const sub = `${baseSub}${timeoutLbl}`;
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--interactive"
      badge={kind === "list" ? "Lst" : "Int"}
      title="Interactif"
      subtitle={truncate(data.body, 42) || sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      footer={
        <div className="pg-node__compact-handles-hint pg-node__compact-handles-hint--split">
          <span>◀ après réponse</span>
          <span title="Branche si aucune réponse avant le délai configuré">
            timeout ▶
          </span>
        </div>
      }
      bottom={
        <>
          <DetachableHandle
            nodeId={id}
            type="source"
            position={Position.Bottom}
            style={{ ...handleStyle, left: "32%" }}
            isConnectable
          />
          <DetachableHandle
            nodeId={id}
            type="source"
            position={Position.Bottom}
            id="timeout"
            style={{ ...handleStyle, left: "68%" }}
            title="Relance si pas de réponse (délai dans les paramètres)"
            isConnectable
          />
        </>
      }
    />
  );
}

function RouterNode({ id, data, selected }) {
  const routes =
    Array.isArray(data.routes) && data.routes.length
      ? data.routes
      : [{ label: "A", match: "A" }];
  const n = routes.length;
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--router"
      badge="Rtg"
      title="Routeur"
      subtitle={`${n} branche(s) · échap. = texte libre`}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      footer={
        <div className="pg-node__compact-handles-hint">
          <span>1 sortie / réponse attendue</span>
        </div>
      }
      bottom={
        <>
          {routes.map((r, i) => (
            <DetachableHandle
              key={i}
              nodeId={id}
              type="source"
              position={Position.Bottom}
              id={`route-${i}`}
              style={{
                ...handleStyle,
                left: `${((i + 1) / (n + 2)) * 100}%`,
              }}
              title={r.label || `Voie ${i + 1}`}
              isConnectable
            />
          ))}
          <DetachableHandle
            nodeId={id}
            type="source"
            position={Position.Bottom}
            id="escape"
            style={{
              ...handleStyle,
              left: `${((n + 1) / (n + 2)) * 100}%`,
            }}
            title="Texte libre / fallback (ex. Gemini)"
            isConnectable
          />
        </>
      }
    />
  );
}

function HandoffNode({ id, data, selected }) {
  const tags = (data.tagsText || "").trim();
  const sub = tags
    ? truncate(tags, 44)
    : truncate(data.internalMessage, 44) || "Stop bot · notifier";
  return (
    <NodeCompactChrome
      id={id}
      selected={selected}
      className="pg-node--handoff"
      badge="H"
      title="Handoff"
      subtitle={sub}
      codeShort={data.varKey ? `{{${data.varKey}}}` : null}
      top={
        <DetachableHandle
          nodeId={id}
          type="target"
          position={Position.Top}
          style={handleStyle}
          isConnectable
        />
      }
      footer={
        <div className="pg-node__compact-handles-hint">
          <span>Suite (optionnel)</span>
        </div>
      }
      bottom={
        <DetachableHandle
          nodeId={id}
          type="source"
          position={Position.Bottom}
          style={handleStyle}
          isConnectable
        />
      }
    />
  );
}

export const playgroundNodeTypes = {
  start: memo(StartNode),
  sendText: memo(SendTextNode),
  sendTemplate: memo(SendTemplateNode),
  gemini: memo(GeminiNode),
  interactiveNode: memo(InteractiveNode),
  routerNode: memo(RouterNode),
  handoffNode: memo(HandoffNode),
  delayNode: memo(DelayNode),
  waitUntilNode: memo(WaitUntilNode),
  timeWindowNode: memo(TimeWindowNode),
  logicNode: memo(LogicNode),
};
