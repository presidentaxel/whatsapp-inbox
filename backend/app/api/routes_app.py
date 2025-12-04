from fastapi import APIRouter

router = APIRouter()


@router.get("/updates")
async def get_app_updates():
    """
    Retourne l'historique des mises à jour de l'application
    Pour l'instant, retourne une liste vide - peut être alimenté manuellement
    ou via une intégration GitHub
    """
    return {
        "updates": []
    }

