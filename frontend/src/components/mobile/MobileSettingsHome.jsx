import { FiArrowLeft, FiSearch } from "react-icons/fi";

export default function MobileSettingsHome({
  onBack,
  searchTerm,
  onSearchChange,
  categories,
}) {
  return (
    <div className="mobile-settings">
      <header className="mobile-settings__header">
        <button className="icon-btn" onClick={onBack} title="Retour">
          <FiArrowLeft />
        </button>
        <h1>Paramètres</h1>
      </header>

      <div className="mobile-settings__search">
        <div className="search-box">
          <FiSearch />
          <input
            type="text"
            placeholder="Rechercher dans les paramètres..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      <div className="mobile-settings__content">
        {categories.map((category, index) => (
          <div
            key={`${category.title}-${index}`}
            className="mobile-settings__item"
            onClick={category.onClick}
          >
            <div className="mobile-settings__item-icon">{category.icon}</div>
            <div className="mobile-settings__item-content">
              <div className="mobile-settings__item-title">{category.title}</div>
              {category.subtitle && (
                <div className="mobile-settings__item-subtitle">{category.subtitle}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
