import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/globals.css";
import "./styles/whatsapp-business.css";
import "./styles/advanced-message-input.css";
import "./styles/mobile.css";
import "./styles/mobile-login.css";
import "./styles/mobile-inbox.css";
import "./styles/mobile-bubbles.css";
import "./styles/mobile-simple-input.css";
import { registerServiceWorker, setupInstallPrompt } from "./registerSW";

// Enregistrer le Service Worker pour la PWA
registerServiceWorker();

// Configurer le prompt d'installation
setupInstallPrompt();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);