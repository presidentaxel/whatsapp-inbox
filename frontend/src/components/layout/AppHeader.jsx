import { SiWhatsapp } from "react-icons/si";

export default function AppHeader() {
  return (
    <header className="top-bar">
      <div className="top-bar__brand">
        <SiWhatsapp size={20} />
        <span>WHATSAPP LMDCVTC</span>
      </div>
    </header>
  );
}

