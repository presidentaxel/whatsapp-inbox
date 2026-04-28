import { Link } from "react-router-dom";

const COPY = {
  404: {
    title: "Page introuvable",
    description:
      "Ce lien ne correspond à aucune page de l’application. Vérifie l’URL ou reviens aux discussions.",
  },
  500: {
    title: "Erreur serveur",
    description:
      "Une erreur inattendue s’est produite sur le serveur. Réessaie dans quelques instants.",
  },
  502: {
    title: "Passerelle invalide",
    description:
      "Le serveur n’a pas reçu de réponse valide en amont. Le service peut être momentanément indisponible.",
  },
  503: {
    title: "Service indisponible",
    description:
      "L’application ou l’API est temporairement indisponible (maintenance ou surcharge). Réessaie bientôt.",
  },
};

export default function HttpErrorPage({ code = 404 }) {
  const meta = COPY[code] ?? COPY[404];

  return (
    <main className="http-error-page" role="alert">
      <div className="http-error-page__card">
        <p className="http-error-page__code" aria-hidden="true">
          {code}
        </p>
        <h1 className="http-error-page__title">{meta.title}</h1>
        <p className="http-error-page__desc">{meta.description}</p>
        <div className="http-error-page__actions">
          <Link to="/discussions" className="http-error-page__btn http-error-page__btn--primary">
            Retour aux discussions
          </Link>
          <button
            type="button"
            className="http-error-page__btn http-error-page__btn--ghost"
            onClick={() => window.history.back()}
          >
            Page précédente
          </button>
        </div>
      </div>
    </main>
  );
}
