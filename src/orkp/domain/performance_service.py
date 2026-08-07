"""Performance Study domain service."""

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidPersistedPayloadError, InvalidRelationError
from orkp.domain.performance_models import (
    PerformanceStudyCreateRequest,
    PerformanceStudyPayload,
    PerformanceStudyResponse,
)
from orkp.domain.versioned_loader import load_versioned_object


class PerformanceStudyService:
    """Create and read structured Performance Studies."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_study(
        self,
        product_hex: str,
        request: PerformanceStudyCreateRequest,
    ) -> PerformanceStudyResponse:
        product = load_versioned_object(
            self.repo,
            product_hex,
            request.product.object_version,
            "product",
        )
        if product.object.uuid_hex != request.product.object_uuid:
            raise InvalidRelationError("Path Product UUID does not match request reference")
        if product.object.current_version != request.product.object_version:
            raise InvalidRelationError(
                "Performance Study must reference the current Product version"
            )

        payload = PerformanceStudyPayload(**request.model_dump())
        try:
            study, _ = self.repo.create_object(
                object_type="study",
                payload=payload.model_dump(),
                owner_user_id=request.owner_user_id,
                created_by=request.owner_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise

        return PerformanceStudyResponse(
            object_uuid=study.uuid_hex,
            object_version=study.current_version,
            lifecycle_state=study.lifecycle_state,
            payload=payload,
        )

    def get_study(self, study_hex: str, version: int) -> PerformanceStudyResponse:
        loaded = load_versioned_object(
            self.repo,
            study_hex,
            version,
            "study",
        )
        try:
            payload = PerformanceStudyPayload(**loaded.payload)
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                "Stored Performance Study payload is invalid"
            ) from exc

        return PerformanceStudyResponse(
            object_uuid=loaded.object.uuid_hex,
            object_version=version,
            lifecycle_state=loaded.object.lifecycle_state,
            payload=payload,
        )
