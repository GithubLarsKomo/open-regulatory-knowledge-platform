"""Models for auditable workflow approval decisions."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ApprovalDecisionResponse(BaseModel):
    """Persisted approval or rejection decision for one exact object version."""

    approval_uuid: str = Field(..., min_length=32, max_length=32)
    object_uuid: str = Field(..., min_length=32, max_length=32)
    version_no: int = Field(..., ge=1)
    decision: Literal["approved", "rejected"]
    approver_user_id: str = Field(..., min_length=1)
    decision_timestamp: datetime
    comments: str | None = None
    signature_data: str | None = None
