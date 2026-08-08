"""
Session storage abstraction for PicoAgents WebUI.

Provides pluggable storage backends for conversation sessions.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..context import AgentContext

logger: logging.Logger = logging.getLogger(__name__)


class SessionStore(ABC):
    """Abstract base for session storage backends."""

    @abstractmethod
    async def get(self, session_id: str) -> Optional[AgentContext]:
        """Retrieve session context by ID."""
        pass

    @abstractmethod
    async def save(self, session_id: str, context: AgentContext) -> None:
        """Persist session context."""
        pass

    @abstractmethod
    async def list(self, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List sessions with metadata, optionally filtered by entity."""
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete a session."""
        pass

    @abstractmethod
    async def clear_all(self) -> int:
        """Clear all sessions. Returns count of deleted sessions."""
        pass


class InMemorySessionStore(SessionStore):
    """Fast in-memory storage - lost on server restart."""

    def __init__(self) -> None:
        self._sessions: Dict[str, AgentContext] = {}

    async def get(self, session_id: str) -> Optional[AgentContext]:
        return self._sessions.get(session_id)

    async def save(self, session_id: str, context: AgentContext) -> None:
        self._sessions[session_id] = context

    async def list(self, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sessions = []
        for sid, ctx in self._sessions.items():
            # Filter by entity_id if provided
            if entity_id and ctx.metadata.get("entity_id") != entity_id:
                continue

            sessions.append(
                {
                    "id": sid,
                    "entity_id": ctx.metadata.get("entity_id", "unknown"),
                    "entity_type": ctx.metadata.get("entity_type", "agent"),
                    "created_at": ctx.created_at.isoformat(),
                    "message_count": len(ctx.messages),
                    "last_activity": ctx.metadata.get(
                        "last_activity", ctx.created_at
                    ).isoformat(),
                }
            )

        # Sort by last_activity (most recent first)
        sessions.sort(
            key=lambda s: s.get("last_activity", s["created_at"]), reverse=True
        )
        return sessions

    async def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Deleted session {session_id}")
            return True
        return False

    async def clear_all(self) -> int:
        count = len(self._sessions)
        self._sessions.clear()
        logger.info(f"Cleared {count} sessions")
        return count


class FileSessionStore(SessionStore):
    """Persistent file-based storage."""

    def __init__(self, storage_dir: str = ".picoagents_sessions") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.json"

    async def get(self, session_id: str) -> Optional[AgentContext]:
        path = self._get_path(session_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AgentContext(**data)
        except Exception as e:
            logger.error(f"Error loading session {session_id}: {e}")
            return None

    async def save(self, session_id: str, context: AgentContext) -> None:
        path = self._get_path(session_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(context.model_dump(), f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving session {session_id}: {e}")

    async def list(self, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sessions = []
        for path in self.storage_dir.glob("*.json"):
            session_id = path.stem
            context = await self.get(session_id)
            if context is None:
                continue

            # Filter by entity_id if provided
            if entity_id and context.metadata.get("entity_id") != entity_id:
                continue

            sessions.append(
                {
                    "id": session_id,
                    "entity_id": context.metadata.get("entity_id", "unknown"),
                    "entity_type": context.metadata.get("entity_type", "agent"),
                    "created_at": context.created_at.isoformat(),
                    "message_count": len(context.messages),
                    "last_activity": context.metadata.get(
                        "last_activity", context.created_at
                    ).isoformat(),
                }
            )

        # Sort by last_activity (most recent first)
        sessions.sort(
            key=lambda s: s.get("last_activity", s["created_at"]), reverse=True
        )
        return sessions

    async def delete(self, session_id: str) -> bool:
        path = self._get_path(session_id)
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted session {session_id}")
                return True
            except Exception as e:
                logger.error(f"Error deleting session {session_id}: {e}")
        return False

    async def clear_all(self) -> int:
        count = 0
        for path in self.storage_dir.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Error deleting {path}: {e}")
        logger.info(f"Cleared {count} sessions")
        return count


class CachedFileSessionStore(SessionStore):
    """In-memory cache with file persistence - best of both worlds."""

    def __init__(self, storage_dir: str = ".picoagents_sessions") -> None:
        self._cache: Dict[str, AgentContext] = {}
        self._file_store = FileSessionStore(storage_dir)

    async def get(self, session_id: str) -> Optional[AgentContext]:
        # Check cache first
        if session_id in self._cache:
            return self._cache[session_id]

        # Load from file
        context = await self._file_store.get(session_id)
        if context:
            self._cache[session_id] = context
        return context

    async def save(self, session_id: str, context: AgentContext) -> None:
        # Update cache
        self._cache[session_id] = context
        # Persist to file
        await self._file_store.save(session_id, context)

    async def list(self, entity_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self._file_store.list(entity_id)

    async def delete(self, session_id: str) -> bool:
        if session_id in self._cache:
            del self._cache[session_id]
        return await self._file_store.delete(session_id)

    async def clear_all(self) -> int:
        self._cache.clear()
        return await self._file_store.clear_all()
