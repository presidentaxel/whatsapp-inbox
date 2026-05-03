"""
Shim de rétrocompatibilité.

Le code historique (>2300 lignes) a été découpé dans le package `app.api.messages`.
Ce fichier ré-exporte le router agrégateur pour ne pas casser :
  - `main.py` (`from app.api.routes_messages import router`)
  - les imports tiers éventuels.

Tout nouveau code doit importer depuis `app.api.messages` directement.
"""
from app.api.messages import router  # noqa: F401

__all__ = ["router"]
