"""Tests for the ORKP REST API endpoints."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from orkp.api.main import create_app
from orkp.api.schemas import RegulatoryObjectCreate
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository


@pytest.fixture(scope="function")
def client():
    """Create a test client with in-memory SQLite."""
    # Use sqlite:// (not :memory:) to ensure connections share the same DB
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app(session_factory_override=TestSession)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db(client):
    """Clean the database between tests by wrapping in a transaction."""
    yield


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestCreateObject:
    """Tests for creating regulatory objects via API."""

    def test_create_object(self, client):
        response = client.post(
            "/api/v1/objects",
            json={
                "object_type": "claim",
                "payload": {"wording": "Test claim", "type": "performance"},
                "owner_user_id": "user-001",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["object_type"] == "claim"
        assert data["lifecycle_state"] == "draft"
        assert data["current_version"] == 1
        assert data["owner_user_id"] == "user-001"
        assert "object_uuid" in data

    def test_create_object_invalid_payload(self, client):
        """Missing required fields returns 422."""
        response = client.post(
            "/api/v1/objects",
            json={"object_type": "claim"},  # missing payload and owner
        )
        assert response.status_code == 422


class TestGetObject:
    """Tests for retrieving objects via API."""

    def test_get_object(self, client):
        # Create first
        create_resp = client.post(
            "/api/v1/objects",
            json={
                "object_type": "risk",
                "payload": {"hazard": "Electrical shock"},
                "owner_user_id": "user-001",
            },
        )
        obj_uuid = create_resp.json()["object_uuid"]

        # Get by UUID
        response = client.get(f"/api/v1/objects/{obj_uuid}")
        assert response.status_code == 200
        data = response.json()
        assert data["object_uuid"] == obj_uuid
        assert data["object_type"] == "risk"
        assert data["payload"] == {"hazard": "Electrical shock"}

    def test_get_nonexistent_object(self, client):
        response = client.get(
            f"/api/v1/objects/{uuid.uuid4().hex}"
        )
        assert response.status_code == 404

    def test_get_object_invalid_uuid(self, client):
        response = client.get("/api/v1/objects/not-a-uuid")
        assert response.status_code == 404


class TestListObjects:
    """Tests for listing objects via API."""

    def test_list_objects(self, client):
        # Create two objects
        client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {"wording": "C1"}, "owner_user_id": "u1",
        })
        client.post("/api/v1/objects", json={
            "object_type": "risk", "payload": {"hazard": "H1"}, "owner_user_id": "u2",
        })

        response = client.get("/api/v1/objects")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_objects_filter_by_type(self, client):
        client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        client.post("/api/v1/objects", json={
            "object_type": "risk", "payload": {}, "owner_user_id": "u2",
        })

        response = client.get("/api/v1/objects?object_type=claim")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["object_type"] == "claim"


class TestVersionHistory:
    """Tests for version history API."""

    def test_list_versions(self, client):
        # Create object
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {"wording": "v1"}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        # Create second version
        client.post(
            f"/api/v1/objects/{obj_uuid}/versions",
            json={"payload": {"wording": "v2"}, "created_by": "u1"},
        )

        # List versions
        response = client.get(f"/api/v1/objects/{obj_uuid}/versions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["version_no"] == 2  # newest first
        assert data[1]["version_no"] == 1

    def test_create_version(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {"wording": "v1"}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        response = client.post(
            f"/api/v1/objects/{obj_uuid}/versions",
            json={"payload": {"wording": "v2"}, "created_by": "u1"},
        )
        assert response.status_code == 201
        assert response.json()["version_no"] == 2


class TestLifecycleTransitions:
    """Tests for lifecycle state transitions via API."""

    def test_submit_for_review(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        response = client.post(
            f"/api/v1/objects/{obj_uuid}/transitions",
            json={"new_state": "in_review", "actor_user_id": "u1"},
        )
        assert response.status_code == 200
        assert response.json()["lifecycle_state"] == "in_review"

    def test_approve_object(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        # Submit for review
        client.post(
            f"/api/v1/objects/{obj_uuid}/transitions",
            json={"new_state": "in_review", "actor_user_id": "u1"},
        )
        # Approve
        response = client.post(
            f"/api/v1/objects/{obj_uuid}/transitions",
            json={"new_state": "approved", "actor_user_id": "u2", "comments": "OK"},
        )
        assert response.status_code == 200
        assert response.json()["lifecycle_state"] == "approved"

    def test_invalid_transition(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        # Try to approve directly from draft (invalid)
        response = client.post(
            f"/api/v1/objects/{obj_uuid}/transitions",
            json={"new_state": "approved", "actor_user_id": "u1"},
        )
        assert response.status_code == 409


class TestEventHistory:
    """Tests for event history API."""

    def test_get_event_history(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        # Perform some transitions
        client.post(
            f"/api/v1/objects/{obj_uuid}/transitions",
            json={"new_state": "in_review", "actor_user_id": "u1"},
        )

        response = client.get(f"/api/v1/objects/{obj_uuid}/events")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["event_type"] == "submitted_for_review"
        assert data[1]["event_type"] == "created"


class TestDeleteObject:
    """Tests for soft-deleting objects via API."""

    def test_soft_delete(self, client):
        create_resp = client.post("/api/v1/objects", json={
            "object_type": "claim", "payload": {}, "owner_user_id": "u1",
        })
        obj_uuid = create_resp.json()["object_uuid"]

        response = client.delete(f"/api/v1/objects/{obj_uuid}?actor_user_id=u1")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = client.get(f"/api/v1/objects/{obj_uuid}")
        assert get_resp.status_code == 404

    def test_delete_nonexistent(self, client):
        response = client.delete(
            f"/api/v1/objects/{uuid.uuid4().hex}?actor_user_id=u1"
        )
        assert response.status_code == 404