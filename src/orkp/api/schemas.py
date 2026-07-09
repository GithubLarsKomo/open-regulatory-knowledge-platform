"""
Pydantic schemas (request/response models) for the ORKP REST API.

Implements API-REST-0001 (all core objects accessible through REST),
API-REST-0003 (pagination, filtering, sorting) and API-REST-0004 (version history).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class PaginationParams(BaseModel):
    """Pagination query parameters."""
    limit: int = Field(default=100, ge=1, le=1000, description="Maximum items per page")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class PaginatedResponse(BaseModel):
    """Paginated list response wrapper."""
    items: List[Any]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Regulatory Object
# ---------------------------------------------------------------------------

class RegulatoryObjectCreate(BaseModel):
    """Request body for creating a new regulatory object."""
    object_type: str = Field(..., description="Domain type (claim, risk, product, ...)")
    payload: Dict[str, Any] = Field(..., description="Object payload data")
    owner_user_id: str = Field(..., description="Responsible person identifier")


class RegulatoryObjectResponse(BaseModel):
    """Response body for a regulatory object."""
    object_uuid: str = Field(..., description="UUID in hex format")
    object_type: str
    current_version: int
    lifecycle_state: str
    owner_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegulatoryObjectDetail(BaseModel):
    """Detailed object response including current version payload."""
    object_uuid: str
    object_type: str
    current_version: int
    lifecycle_state: str
    owner_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    payload: Dict[str, Any]


class ObjectVersionCreate(BaseModel):
    """Request body for creating a new version."""
    payload: Dict[str, Any] = Field(..., description="New version payload data")
    created_by: str = Field(..., description="User creating the version")


class ObjectVersionResponse(BaseModel):
    """Response body for an object version."""
    object_uuid: str
    version_no: int
    payload: Dict[str, Any]
    status: str
    created_at: datetime
    created_by: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class StateTransitionRequest(BaseModel):
    """Request body for lifecycle state transition."""
    new_state: str = Field(..., description="Target lifecycle state")
    actor_user_id: str = Field(..., description="User performing the transition")
    comments: Optional[str] = Field(None, description="Reviewer comments")


# ---------------------------------------------------------------------------
# Event Log
# ---------------------------------------------------------------------------

class EventLogResponse(BaseModel):
    """Response body for an event log entry."""
    event_id: int
    object_uuid: str
    object_type: str
    event_type: str
    event_data: Optional[Dict[str, Any]] = None
    event_timestamp: datetime
    actor_user_id: str

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None