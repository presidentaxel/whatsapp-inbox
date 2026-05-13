import FlowEditor from "./FlowEditor";

export default function PlaygroundPanel({ accountId }) {
  if (!accountId) {
    return (
      <div className="playground-root playground-root--empty muted">
        Sélectionne un compte dans la barre du haut.
      </div>
    );
  }

  return (
    <div className="playground-root">
      <FlowEditor key={accountId} accountId={accountId} />
    </div>
  );
}
