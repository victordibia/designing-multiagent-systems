"""Tests for FastAPI server functionality."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from picoagents.webui._server import PicoAgentsWebUIServer


class MockAgent:
    """Mock agent for testing."""

    def __init__(self, name: str = "TestAgent") -> None:
        self.name = name
        self.description = "Test agent"
        self.tools = []
        self.model_client = Mock()
        self.model_client.model = "gpt-4.1-mini"
        self.memory = None

    async def run(self, messages):
        """Mock run method."""
        return Mock()


@pytest.fixture
def test_server():
    """Create test server without directory scanning."""
    server = PicoAgentsWebUIServer()
    return server


@pytest.fixture
def test_client(test_server):
    """Create test client."""
    app = test_server.create_app()
    return TestClient(app)


def test_health_endpoint(test_client):
    """Test health check endpoint."""
    response = test_client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "entities_count" in data


def test_list_entities_empty(test_client):
    """Test listing entities when none exist."""
    response = test_client.get("/api/entities")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_list_entities_with_registered(test_server, test_client):
    """Test listing entities after registering some."""
    # Register an entity
    agent = MockAgent("TestAgent")
    test_server.registry.register_entity("test_agent", agent)

    response = test_client.get("/api/entities")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "test_agent"
    assert data[0]["type"] == "agent"


def test_get_entity_info(test_server, test_client):
    """Test getting specific entity info."""
    # Register an entity
    agent = MockAgent("TestAgent")
    test_server.registry.register_entity("test_agent", agent)

    response = test_client.get("/api/entities/test_agent")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test_agent"
    assert data["name"] == "TestAgent"
    assert data["type"] == "agent"


def test_get_nonexistent_entity(test_client):
    """Test getting info for nonexistent entity."""
    response = test_client.get("/api/entities/nonexistent")

    assert response.status_code == 404


def test_non_streaming_run_endpoint_removed(test_server, test_client):
    """The non-streaming /run endpoint was removed (its execute_agent backend
    was deleted in 0.3.0); only /run/stream exists."""
    agent = MockAgent("TestAgent")
    test_server.registry.register_entity("test_agent", agent)

    response = test_client.post("/api/entities/test_agent/run", json={})

    assert response.status_code == 405


def test_list_sessions_empty(test_client):
    """Test listing sessions when none exist."""
    response = test_client.get("/api/sessions")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_nonexistent_session(test_client):
    """Test getting nonexistent session."""
    response = test_client.get("/api/sessions/nonexistent")

    assert response.status_code == 404


def test_delete_nonexistent_session(test_client):
    """Test deleting nonexistent session."""
    response = test_client.delete("/api/sessions/nonexistent")

    assert response.status_code == 404


def test_clear_cache(test_client):
    """Test clearing entity cache."""
    response = test_client.post("/api/cache/clear")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cache_cleared"


def test_get_stats(test_server, test_client):
    """Test getting system statistics."""
    # Register some entities
    agent = MockAgent("TestAgent")
    test_server.registry.register_entity("test_agent", agent)

    response = test_client.get("/api/stats")

    assert response.status_code == 200
    data = response.json()
    assert "entities" in data
    assert "sessions" in data
    assert data["entities"]["total"] == 1
    assert data["entities"]["by_type"]["agents"] == 1


def test_cors_enabled():
    """Test that CORS is properly configured."""
    server = PicoAgentsWebUIServer(enable_cors=True, cors_origins=["*"])
    app = server.create_app()
    client = TestClient(app)

    # Make a preflight request
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    # Should not fail (CORS should handle it)
    assert response.status_code in [200, 404]  # Depends on FastAPI version


def test_cors_disabled():
    """Test server with CORS disabled."""
    server = PicoAgentsWebUIServer(enable_cors=False)
    app = server.create_app()

    # Should create app without error
    assert app is not None
