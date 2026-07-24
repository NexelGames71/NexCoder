"""AppwriteClient — Appwrite SDK wrapper for NexCoder cloud features."""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AppwriteClient:
    """Appwrite Python SDK client for NexCoder cloud sync.

    Handles auth, database CRUD for NexCoder-specific collections,
    and offline-first queuing.
    """

    # NexCoder collection IDs
    COLLECTIONS = {
        "projects": "nexcoder_projects",
        "sessions": "nexcoder_sessions",
        "messages": "nexcoder_messages",
        "tasks": "nexcoder_tasks",
        "rules": "nexcoder_rules",
        "usage": "nexcoder_usage",
    }

    def __init__(self) -> None:
        self._client = None
        self._databases = None
        self._account = None
        self._initialized = False
        self._offline_queue: list[dict[str, Any]] = []

        self._endpoint = os.getenv("APPWRITE_ENDPOINT", "")
        self._project_id = os.getenv("APPWRITE_PROJECT_ID", "")
        self._database_id = os.getenv("APPWRITE_DATABASE_ID", "")

        if self._endpoint and self._project_id:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize the Appwrite client."""
        try:
            from appwrite.client import Client
            from appwrite.services.databases import Databases
            from appwrite.services.account import Account

            self._client = Client()
            self._client.set_endpoint(self._endpoint)
            self._client.set_project(self._project_id)

            # This is a distributed desktop client. Never attach an Appwrite
            # server API key here; authorization must come from the signed-in
            # user's session and collection permissions. Privileged work
            # belongs behind a Nexa service endpoint.

            self._databases = Databases(self._client)
            self._account = Account(self._client)
            self._initialized = True

            logger.info("Appwrite client initialized")
        except ImportError:
            logger.warning("Appwrite SDK not installed, cloud features disabled")
        except Exception as e:
            logger.error(f"Failed to initialize Appwrite: {e}")

    @property
    def is_available(self) -> bool:
        """Check if Appwrite is configured and available."""
        return self._initialized

    # ── Auth ──────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> dict[str, Any]:
        """Login with email and password."""
        if not self._initialized:
            return {"success": False, "error": "Appwrite not configured"}

        try:
            session = self._account.create_email_password_session(email, password)
            return {"success": True, "session": session}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def register(self, email: str, password: str, name: str = "") -> dict[str, Any]:
        """Register a new account."""
        if not self._initialized:
            return {"success": False, "error": "Appwrite not configured"}

        try:
            from appwrite.id import ID
            user = self._account.create(ID.unique(), email, password, name or email.split("@")[0])
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def logout(self) -> dict[str, Any]:
        """Delete current session."""
        if not self._initialized:
            return {"success": False, "error": "Appwrite not configured"}

        try:
            self._account.delete_session("current")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_current_user(self) -> dict[str, Any]:
        """Get the current logged-in user."""
        if not self._initialized:
            return {"success": False, "error": "Appwrite not configured"}

        try:
            user = self._account.get()
            return {"success": True, "user": user}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Database CRUD ─────────────────────────────────────────────────

    def create_document(
        self, collection_key: str, data: dict[str, Any], document_id: str | None = None
    ) -> str:
        """Create a document in a NexCoder collection."""
        if not self._initialized:
            self._offline_queue.append({
                "action": "create",
                "collection": collection_key,
                "data": data,
            })
            return "queued"

        try:
            from appwrite.id import ID

            collection_id = self.COLLECTIONS.get(collection_key, collection_key)
            doc_id = document_id or ID.unique()

            result = self._databases.create_document(
                database_id=self._database_id,
                collection_id=collection_id,
                document_id=doc_id,
                data=data,
            )
            return result["$id"]
        except Exception as e:
            logger.error(f"Appwrite create error: {e}")
            self._offline_queue.append({
                "action": "create",
                "collection": collection_key,
                "data": data,
            })
            return "queued"

    def get_document(self, collection_key: str, document_id: str) -> dict[str, Any] | None:
        """Get a document from a NexCoder collection."""
        if not self._initialized:
            return None

        try:
            collection_id = self.COLLECTIONS.get(collection_key, collection_key)
            return self._databases.get_document(
                database_id=self._database_id,
                collection_id=collection_id,
                document_id=document_id,
            )
        except Exception as e:
            logger.error(f"Appwrite get error: {e}")
            return None

    def list_documents(
        self, collection_key: str, queries: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """List documents from a NexCoder collection."""
        if not self._initialized:
            return []

        try:
            collection_id = self.COLLECTIONS.get(collection_key, collection_key)
            result = self._databases.list_documents(
                database_id=self._database_id,
                collection_id=collection_id,
                queries=queries or [],
            )
            return result.get("documents", [])
        except Exception as e:
            logger.error(f"Appwrite list error: {e}")
            return []

    def update_document(
        self, collection_key: str, document_id: str, data: dict[str, Any]
    ) -> bool:
        """Update a document in a NexCoder collection."""
        if not self._initialized:
            self._offline_queue.append({
                "action": "update",
                "collection": collection_key,
                "document_id": document_id,
                "data": data,
            })
            return False

        try:
            collection_id = self.COLLECTIONS.get(collection_key, collection_key)
            self._databases.update_document(
                database_id=self._database_id,
                collection_id=collection_id,
                document_id=document_id,
                data=data,
            )
            return True
        except Exception as e:
            logger.error(f"Appwrite update error: {e}")
            return False

    def delete_document(self, collection_key: str, document_id: str) -> bool:
        """Delete a document from a NexCoder collection."""
        if not self._initialized:
            return False

        try:
            collection_id = self.COLLECTIONS.get(collection_key, collection_key)
            self._databases.delete_document(
                database_id=self._database_id,
                collection_id=collection_id,
                document_id=document_id,
            )
            return True
        except Exception as e:
            logger.error(f"Appwrite delete error: {e}")
            return False

    # ── Offline Sync ──────────────────────────────────────────────────

    def sync_offline_queue(self) -> int:
        """Process queued operations from offline mode. Returns count synced."""
        if not self._initialized or not self._offline_queue:
            return 0

        synced = 0
        remaining: list[dict[str, Any]] = []

        for item in self._offline_queue:
            try:
                if item["action"] == "create":
                    self.create_document(item["collection"], item["data"])
                    synced += 1
                elif item["action"] == "update":
                    self.update_document(item["collection"], item["document_id"], item["data"])
                    synced += 1
            except Exception:
                remaining.append(item)

        self._offline_queue = remaining
        if synced:
            logger.info(f"Synced {synced} offline operations")
        return synced
