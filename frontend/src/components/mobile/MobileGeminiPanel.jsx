export default function MobileGeminiPanel({ accounts, activeAccount }) {
  const currentAccount = accounts.find(a => a.id === activeAccount);

  return (
    <div className="mobile-gemini">
      <header className="mobile-panel-header">
        <h1>Assistant Gemini</h1>
      </header>

      <div className="mobile-panel-content">
        <div className="mobile-panel-card">
          <h3>Configuration de l'assistant IA</h3>
          <p>Compte : {currentAccount?.name || "Aucun compte"}</p>
        </div>

        <div className="mobile-panel-card">
          <h3>Accès complet</h3>
          <p>Pour configurer l'assistant Gemini et ses paramètres, veuillez utiliser la version web sur ordinateur.</p>
        </div>
      </div>
    </div>
  );
}

