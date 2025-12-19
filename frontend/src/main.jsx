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
import "./styles/permissions-table.css";
import { registerServiceWorker, setupInstallPrompt } from "./registerSW";
import { initNotifications } from "./utils/notifications";
import { getDeviceType } from "./utils/deviceDetection";

// Changer le theme-color en noir uniquement sur PC (pour la barre de titre Windows)
if (typeof window !== "undefined") {
  const deviceType = getDeviceType();
  if (deviceType === "desktop") {
    // Trouver ou créer la meta tag theme-color
    let themeColorMeta = document.querySelector('meta[name="theme-color"]');
    if (!themeColorMeta) {
      themeColorMeta = document.createElement("meta");
      themeColorMeta.setAttribute("name", "theme-color");
      document.head.appendChild(themeColorMeta);
    }
    themeColorMeta.setAttribute("content", "#000");
  }
}

// Enregistrer le Service Worker pour la PWA
registerServiceWorker();

// Configurer le prompt d'installation
setupInstallPrompt();

// Initialiser les notifications push
initNotifications();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);