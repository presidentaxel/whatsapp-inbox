import { useEffect, useRef, useState, useMemo } from "react";
import * as pdfjsLib from "pdfjs-dist";

// Configuration du worker PDF.js - utiliser le worker local depuis public
if (typeof window !== "undefined" && "Worker" in window) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";
}

export default function PDFThumbnail({ url, width = 200, height = 200, onError }) {
  const canvasRef = useRef(null);
  const renderTaskRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [hasRendered, setHasRendered] = useState(false);
  
  // Mémoriser l'URL pour éviter les re-renders inutiles
  const memoizedUrl = useMemo(() => url, [url]);

  useEffect(() => {
    if (!memoizedUrl || !canvasRef.current) return;

    let cancelled = false;

    const renderPDF = async () => {
      try {
        setLoading(true);
        setError(false);
        setHasRendered(false);

        // Annuler toute opération de rendu précédente
        if (renderTaskRef.current) {
          try {
            renderTaskRef.current.cancel();
          } catch (e) {
            // Ignorer les erreurs de cancellation
          }
          renderTaskRef.current = null;
        }

        console.log("[PDF Thumbnail] Loading PDF from:", memoizedUrl);

        // Charger le PDF avec gestion CORS
        const loadingTask = pdfjsLib.getDocument({
          url: memoizedUrl,
          withCredentials: false,
          httpHeaders: {},
        });
        
        const pdf = await loadingTask.promise;
        
        if (cancelled) return;

        // Récupérer la première page
        const page = await pdf.getPage(1);
        
        if (cancelled) return;

        // Calculer l'échelle pour s'adapter au canvas
        const viewport = page.getViewport({ scale: 1.0 });
        const scale = Math.min(width / viewport.width, height / viewport.height) * 2; // x2 pour meilleure qualité
        const scaledViewport = page.getViewport({ scale });

        // Configurer le canvas avec les dimensions réelles
        const canvas = canvasRef.current;
        if (!canvas || cancelled) return;

        // Nettoyer le canvas avant de rendre
        const context = canvas.getContext("2d");
        context.clearRect(0, 0, canvas.width, canvas.height);
        
        canvas.width = scaledViewport.width;
        canvas.height = scaledViewport.height;

        // Render la page et stocker la tâche de rendu
        const renderContext = {
          canvasContext: context,
          viewport: scaledViewport,
        };

        const renderTask = page.render(renderContext);
        renderTaskRef.current = renderTask;
        
        await renderTask.promise;
        
        if (cancelled) return;

        // Nettoyer la référence après le rendu réussi
        renderTaskRef.current = null;
        
        setHasRendered(true);
        setLoading(false);
        console.log("[PDF Thumbnail] PDF rendered successfully");
      } catch (err) {
        if (cancelled) return;
        
        // Si l'erreur est due à une cancellation, ne pas la traiter comme une erreur
        if (err.name === 'RenderingCancelledException' || err.message?.includes('cancelled')) {
          console.log("[PDF Thumbnail] Rendering cancelled");
          return;
        }
        
        console.error("[PDF Thumbnail] Error rendering PDF:", err);
        setError(true);
        setLoading(false);
        renderTaskRef.current = null;
        if (onError) {
          onError(err);
        }
      }
    };

    renderPDF();

    return () => {
      cancelled = true;
      // Annuler la tâche de rendu en cours lors du démontage
      if (renderTaskRef.current) {
        try {
          renderTaskRef.current.cancel();
        } catch (e) {
          // Ignorer les erreurs de cancellation
        }
        renderTaskRef.current = null;
      }
    };
  }, [memoizedUrl, width, height]); // Retirer onError des dépendances pour éviter les re-renders

  // Si erreur ou pas encore rendu, retourner null pour afficher le fallback
  if (error || (!hasRendered && !loading)) {
    return null;
  }

  return (
    <>
      {loading && (
        <div style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f5f5f5",
          color: "#999",
          fontSize: "12px"
        }}>
          Chargement...
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: hasRendered ? "block" : "none",
          position: "relative",
        }}
      />
    </>
  );
}

