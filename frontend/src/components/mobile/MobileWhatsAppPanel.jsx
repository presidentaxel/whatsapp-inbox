export default function MobileWhatsAppPanel({ accounts, activeAccount }) {
  const currentAccount = accounts.find(a => a.id === activeAccount);

  return (
    <div className="mobile-whatsapp">
      <header className="mobile-panel-header">
        <h1>WhatsApp Business</h1>
      </header>

      <div className="mobile-panel-content">
        <div className="mobile-panel-card">
          <h3>Compte actif</h3>
          <p>{currentAccount?.name || "Aucun compte"}</p>
        </div>

        <div className="mobile-panel-card">
          <h3>Accès complet</h3>
          <p>Pour gérer vos templates, profil et paramètres WhatsApp Business, veuillez utiliser la version web sur ordinateur.</p>
        </div>
      </div>
    </div>
  );
}

