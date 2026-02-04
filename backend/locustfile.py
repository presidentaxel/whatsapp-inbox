"""
Tests de performance pour WhatsApp Inbox API.

Usage:
  # Installer locust
  pip install locust

  # Tests basiques (health check uniquement, pas d'auth)
  locust -f locustfile.py --host=http://localhost:8000

  # Tests avec auth (endpoints protégés)
  # Récupérer un token Supabase depuis le navigateur (DevTools > Application > localStorage)
  set LOCUST_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIs...
  locust -f locustfile.py --host=http://localhost:8000

  # Lancer en mode headless (sans UI)
  locust -f locustfile.py --host=http://localhost:8000 --headless -u 10 -r 2 -t 60s

  # Lancer avec l'interface web sur http://localhost:8089
  locust -f locustfile.py --host=http://localhost:8000
"""
import os
from locust import HttpUser, task, between


class WhatsAppInboxUser(HttpUser):
    """Utilisateur simulé pour les tests de charge."""

    wait_time = between(1, 3)

    def on_start(self):
        """Configure les headers d'auth si un token est fourni."""
        self.auth_token = os.environ.get("LOCUST_AUTH_TOKEN")
        self.account_id = os.environ.get("LOCUST_ACCOUNT_ID", "")
        self.conversation_id = os.environ.get("LOCUST_CONVERSATION_ID", "")
        if self.auth_token:
            self.client.headers["Authorization"] = f"Bearer {self.auth_token}"

    @task(5)
    def health_check(self):
        """Health check - endpoint léger, pas d'auth."""
        self.client.get("/health")

    @task(3)
    def health_live(self):
        """Liveness probe - très rapide."""
        self.client.get("/health/live")

    @task(2)
    def list_conversations(self):
        """Liste les conversations - requiert auth et account_id."""
        if not self.auth_token or not self.account_id:
            return
        self.client.get(
            "/conversations",
            params={"account_id": self.account_id, "limit": 50},
        )

    @task(2)
    def get_messages(self):
        """Récupère les messages d'une conversation - requiert auth."""
        if not self.auth_token or not self.conversation_id:
            return
        self.client.get(
            f"/messages/{self.conversation_id}",
            params={"limit": 50},
        )

    @task(1)
    def check_media(self):
        """Check-media - endpoint à benchmarker (debounce/cache)."""
        if not self.auth_token or not self.conversation_id:
            return
        self.client.post(f"/messages/check-media/{self.conversation_id}")
