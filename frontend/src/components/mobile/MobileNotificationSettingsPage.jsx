import { FiArrowLeft } from "react-icons/fi";
import MobileNotificationSettings from "./MobileNotificationSettings";

export default function MobileNotificationSettingsPage({ onBack }) {
  return (
    <div className="mobile-settings">
      <header className="mobile-settings__header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Notifications</h1>
      </header>
      <div className="mobile-settings__content" style={{ padding: "1rem" }}>
        <MobileNotificationSettings />
      </div>
    </div>
  );
}
