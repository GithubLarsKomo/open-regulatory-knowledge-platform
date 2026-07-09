"""
FastAPI application for the ORKP REST API.

Implements:
    - API-REST-0001: All core objects accessible through REST
    - API-REST-0002: API versioning
    - API-REST-0003: Pagination, filtering, sorting
    - API-REST-0004: Version history exposure
    - API-REST-0005: Authorization enforcement (stub)
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from orkp.api.schemas import (
    ErrorResponse,
    EventLogResponse,
    ObjectVersionCreate,
    ObjectVersionResponse,
    RegulatoryObjectCreate,
    RegulatoryObjectDetail,
    RegulatoryObjectResponse,
    StateTransitionRequest,
)
from orkp.db.repository import RegulatoryObjectRepository
from orkp.db.session import create_engine_from_config, create_session_factory, get_session
from orkp.config import load_config
from orkp.api.routers import create_product_router, create_claim_router, create_evidence_router

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(session_factory_override=None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        session_factory_override: Optional session factory for testing.
    """
    config = load_config()

    app = FastAPI(
        title="ORKP Regulatory Knowledge Platform API",
        description="REST API for regulatory object management (API-REST-0001)",
        version="0.1.0",
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
    )

    if session_factory_override:
        session_factory = session_factory_override
    else:
        engine = create_engine_from_config(config.db)
        session_factory = create_session_factory(engine)

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def get_db() -> Session:
        """Dependency that provides a database session."""
        db = get_session(session_factory)
        try:
            yield db
        finally:
            db.close()

    def get_repo(db: Session = Depends(get_db)) -> RegulatoryObjectRepository:
        """Dependency that provides a repository instance."""
        return RegulatoryObjectRepository(db)

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=exc.detail).model_dump(),
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/api/v1/health")
    async def health_check():
        return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

    # ------------------------------------------------------------------
    # Regulatory Objects
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/objects",
        response_model=RegulatoryObjectResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new regulatory object",
    )
    async def create_object(
        body: RegulatoryObjectCreate,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Create a new regulatory object with its initial version (DB-CORE-0001)."""
        obj, version = repo.create_object(
            object_type=body.object_type,
            payload=body.payload,
            owner_user_id=body.owner_user_id,
            created_by=body.owner_user_id,
        )
        repo.session.commit()

        return RegulatoryObjectResponse(
            object_uuid=obj.uuid_hex,
            object_type=obj.object_type,
            current_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @app.get(
        "/api/v1/objects",
        response_model=List[RegulatoryObjectResponse],
        summary="List regulatory objects",
    )
    async def list_objects(
        object_type: Optional[str] = Query(None, description="Filter by object type"),
        lifecycle_state: Optional[str] = Query(None, description="Filter by lifecycle state"),
        limit: int = Query(100, ge=1, le=1000, description="Max items per page"),
        offset: int = Query(0, ge=0, description="Number of items to skip"),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """List regulatory objects with optional filters and pagination (API-REST-0003)."""
        objects = repo.list_objects(
            object_type=object_type,
            lifecycle_state=lifecycle_state,
            limit=limit,
            offset=offset,
        )
        return [
            RegulatoryObjectResponse(
                object_uuid=obj.uuid_hex,
                object_type=obj.object_type,
                current_version=obj.current_version,
                lifecycle_state=obj.lifecycle_state,
                owner_user_id=obj.owner_user_id,
                created_at=obj.created_at,
                updated_at=obj.updated_at,
            )
            for obj in objects
        ]

    @app.get(
        "/api/v1/objects/{object_uuid}",
        response_model=RegulatoryObjectDetail,
        summary="Get a regulatory object by UUID",
    )
    async def get_object(
        object_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """
        Get a regulatory object by UUID with its current payload (API-REST-0001, API-REST-0004).

        Returns the object details and current version payload.
        """
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        version = repo.get_version(obj.object_uuid, obj.current_version)
        payload = version.payload_json if version else {}

        return RegulatoryObjectDetail(
            object_uuid=obj.uuid_hex,
            object_type=obj.object_type,
            current_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Object Versions
    # ------------------------------------------------------------------

    @app.get(
        "/api/v1/objects/{object_uuid}/versions",
        response_model=List[ObjectVersionResponse],
        summary="Get version history for an object",
    )
    async def list_versions(
        object_uuid: str,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Get all versions of a regulatory object (API-REST-0004)."""
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        versions = repo.list_versions(obj.object_uuid)
        return [
            ObjectVersionResponse(
                object_uuid=_bin_to_str(v.object_uuid),
                version_no=v.version_no,
                payload=v.payload_json,
                status=v.status,
                created_at=v.created_at,
                created_by=v.created_by,
            )
            for v in versions
        ]

    @app.post(
        "/api/v1/objects/{object_uuid}/versions",
        response_model=ObjectVersionResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a new version",
    )
    async def create_version(
        object_uuid: str,
        body: ObjectVersionCreate,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Create a new version of a draft or in-review object."""
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        version = repo.create_version(
            object_uuid=obj.object_uuid,
            payload=body.payload,
            created_by=body.created_by,
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot create version: object is in '{obj.lifecycle_state}' state",
            )

        repo.session.commit()
        return ObjectVersionResponse(
            object_uuid=_bin_to_str(version.object_uuid),
            version_no=version.version_no,
            payload=version.payload_json,
            status=version.status,
            created_at=version.created_at,
            created_by=version.created_by,
        )

    # ------------------------------------------------------------------
    # Lifecycle State Transitions
    # ------------------------------------------------------------------

    @app.post(
        "/api/v1/objects/{object_uuid}/transitions",
        response_model=RegulatoryObjectResponse,
        summary="Transition object lifecycle state",
    )
    async def transition_state(
        object_uuid: str,
        body: StateTransitionRequest,
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Transition a regulatory object to a new lifecycle state (WF-APP-0001)."""
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        success = repo.transition_state(
            object_uuid=obj.object_uuid,
            new_state=body.new_state,
            actor_user_id=body.actor_user_id,
            comments=body.comments,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition from '{obj.lifecycle_state}' to '{body.new_state}'",
            )

        repo.session.commit()
        obj = repo.get_by_uuid(obj.object_uuid)  # refresh
        return RegulatoryObjectResponse(
            object_uuid=obj.uuid_hex,
            object_type=obj.object_type,
            current_version=obj.current_version,
            lifecycle_state=obj.lifecycle_state,
            owner_user_id=obj.owner_user_id,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    # ------------------------------------------------------------------
    # Event Log
    # ------------------------------------------------------------------

    @app.get(
        "/api/v1/objects/{object_uuid}/events",
        response_model=List[EventLogResponse],
        summary="Get event history for an object",
    )
    async def get_event_history(
        object_uuid: str,
        limit: int = Query(100, ge=1, le=1000),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Get the event/audit history for a regulatory object."""
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        events = repo.get_event_history(obj.object_uuid, limit=limit)
        return [
            EventLogResponse(
                event_id=e.event_id,
                object_uuid=_bin_to_str(e.object_uuid),
                object_type=e.object_type,
                event_type=e.event_type,
                event_data=e.event_data,
                event_timestamp=e.event_timestamp,
                actor_user_id=e.actor_user_id,
            )
            for e in events
        ]

    # ------------------------------------------------------------------
    # Soft Delete
    # ------------------------------------------------------------------

    @app.delete(
        "/api/v1/objects/{object_uuid}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Soft-delete a regulatory object",
    )
    async def delete_object(
        object_uuid: str,
        actor_user_id: str = Query(..., description="User performing the deletion"),
        repo: RegulatoryObjectRepository = Depends(get_repo),
    ):
        """Soft-delete a regulatory object (DB-CORE-0004)."""
        obj = repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Object {object_uuid} not found",
            )

        success = repo.soft_delete(obj.object_uuid, actor_user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Could not delete object",
            )

        repo.session.commit()
        return None

    # ------------------------------------------------------------------
    # Mount domain-specific routers
    # ------------------------------------------------------------------

    app.include_router(create_product_router(get_repo))
    app.include_router(create_claim_router(get_repo))
    app.include_router(create_evidence_router(get_repo))

    return app


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _bin_to_str(b: bytes) -> str:
    """Convert binary UUID to hex string."""
    import uuid
    return uuid.UUID(bytes=b).hex


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn
    config = load_config()
    uvicorn.run(
        "orkp.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.debug,
    )