"""Read-only workflow approval history queries."""

from sqlalchemy import select

from orkp.db.models import ApprovalRecord, _bin_to_str
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import ObjectNotFoundError
from orkp.domain.workflow_models import ApprovalDecisionResponse


class WorkflowService:
    """Workflow audit queries backed by persisted approval decisions."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def list_approval_history(self, object_uuid: str) -> list[ApprovalDecisionResponse]:
        """Return deterministic approval/rejection history for a regulatory object."""
        obj = self.repo.get_by_uuid_hex(object_uuid)
        if obj is None:
            raise ObjectNotFoundError(f"Object {object_uuid} not found")

        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.object_uuid == obj.object_uuid)
            .order_by(
                ApprovalRecord.decision_timestamp.asc(),
                ApprovalRecord.approval_uuid.asc(),
            )
        )
        records = self.repo.session.execute(stmt).scalars().all()
        return [
            ApprovalDecisionResponse(
                approval_uuid=_bin_to_str(record.approval_uuid),
                object_uuid=_bin_to_str(record.object_uuid),
                version_no=record.version_no,
                decision=record.decision,
                approver_user_id=record.approver_user_id,
                decision_timestamp=record.decision_timestamp,
                comments=record.comments,
                signature_data=record.signature_data,
            )
            for record in records
        ]
