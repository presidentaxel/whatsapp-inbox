"""
Circuit breaker pattern pour protéger l'application des dépendances défaillantes.

Le circuit breaker a 3 états:
- CLOSED: Normal, les requêtes passent
- OPEN: Trop d'erreurs, les requêtes échouent rapidement sans appeler la dépendance
- HALF_OPEN: Test si la dépendance est revenue, quelques requêtes passent

Cela évite l'effet "cascade failure" où une dépendance lente/down ralentit tout le système.
"""
import logging
from typing import Optional, Callable, Any
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal
    OPEN = "open"          # Trop d'erreurs, circuit ouvert
    HALF_OPEN = "half_open"  # Test de récupération


class CircuitBreaker:
    """
    Circuit breaker simple en mémoire.
    
    Pour une solution production multi-instances, utiliser Redis.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2
    ):
        """
        Args:
            name: Nom du circuit (pour logging/monitoring)
            failure_threshold: Nombre d'échecs avant d'ouvrir le circuit
            recovery_timeout: Temps d'attente avant de tester la récupération (secondes)
            success_threshold: Nombre de succès en HALF_OPEN avant de fermer le circuit
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.success_threshold = success_threshold
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.opened_at: Optional[datetime] = None
    
    def _should_attempt_reset(self) -> bool:
        """Vérifie si on doit passer en HALF_OPEN."""
        if self.state != CircuitBreakerState.OPEN:
            return False
        if self.opened_at is None:
            return False
        return datetime.now() - self.opened_at >= self.recovery_timeout
    
    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute une fonction protégée par le circuit breaker.
        
        Raises:
            CircuitBreakerOpenError: Si le circuit est ouvert
        """
        # Transition OPEN -> HALF_OPEN si timeout écoulé
        if self._should_attempt_reset():
            logger.info(f"Circuit breaker '{self.name}': tentative de récupération (HALF_OPEN)")
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
        
        # Si circuit ouvert, échec rapide
        if self.state == CircuitBreakerState.OPEN:
            logger.warning(f"Circuit breaker '{self.name}' est OPEN, appel bloqué")
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is open. "
                f"Dependency is unavailable. "
                f"Retry after {self.recovery_timeout.total_seconds()}s"
            )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    async def call_async(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Version async de call()."""
        # Transition OPEN -> HALF_OPEN si timeout écoulé
        if self._should_attempt_reset():
            logger.info(f"Circuit breaker '{self.name}': tentative de récupération (HALF_OPEN)")
            self.state = CircuitBreakerState.HALF_OPEN
            self.success_count = 0
        
        # Si circuit ouvert, échec rapide
        if self.state == CircuitBreakerState.OPEN:
            logger.warning(f"Circuit breaker '{self.name}' est OPEN, appel bloqué")
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.name}' is open. "
                f"Dependency is unavailable. "
                f"Retry after {self.recovery_timeout.total_seconds()}s"
            )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Appelé après un appel réussi."""
        self.failure_count = 0
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                logger.info(f"Circuit breaker '{self.name}': récupération réussie (CLOSED)")
                self.state = CircuitBreakerState.CLOSED
                self.success_count = 0
    
    def _on_failure(self):
        """Appelé après un appel échoué."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            # En HALF_OPEN, un seul échec rouvre le circuit
            logger.warning(f"Circuit breaker '{self.name}': échec en HALF_OPEN, retour à OPEN")
            self.state = CircuitBreakerState.OPEN
            self.opened_at = datetime.now()
            self.success_count = 0
        
        elif self.failure_count >= self.failure_threshold:
            # Trop d'échecs, on ouvre le circuit
            logger.error(
                f"Circuit breaker '{self.name}': seuil d'échecs atteint "
                f"({self.failure_count}/{self.failure_threshold}), ouverture du circuit"
            )
            self.state = CircuitBreakerState.OPEN
            self.opened_at = datetime.now()
    
    def reset(self):
        """Reset manuel du circuit breaker."""
        logger.info(f"Circuit breaker '{self.name}': reset manuel")
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.opened_at = None
    
    def get_status(self) -> dict:
        """Retourne le status du circuit breaker pour monitoring."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
        }


class CircuitBreakerOpenError(Exception):
    """Exception levée quand le circuit breaker est ouvert."""
    pass


# Instances globales pour les dépendances principales
gemini_circuit_breaker = CircuitBreaker(
    name="gemini_api",
    failure_threshold=5,      # 5 échecs avant ouverture
    recovery_timeout=60.0,    # Attendre 60s avant de réessayer
    success_threshold=2       # 2 succès pour fermer le circuit
)

whatsapp_circuit_breaker = CircuitBreaker(
    name="whatsapp_api",
    failure_threshold=3,      # 3 échecs avant ouverture
    recovery_timeout=30.0,    # Attendre 30s avant de réessayer
    success_threshold=2
)

supabase_circuit_breaker = CircuitBreaker(
    name="supabase",
    failure_threshold=5,
    recovery_timeout=30.0,
    success_threshold=2
)


def get_all_circuit_breakers() -> dict:
    """Retourne le status de tous les circuit breakers."""
    return {
        "gemini": gemini_circuit_breaker.get_status(),
        "whatsapp": whatsapp_circuit_breaker.get_status(),
        "supabase": supabase_circuit_breaker.get_status(),
    }

