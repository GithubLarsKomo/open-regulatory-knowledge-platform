"""Governed persistence service for provider-neutral grounded AI draft records."""

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_draft_models import (
    AIDraftCreateRequest,
    AIDraftPayload,
    AIDraftRegenerateRequest,
    AIDraftResponse,
)
from orkp.domain.exceptions import (
    InvalidLifecycleStateError,
    InvalidPersistedPayloadError,
    ObjectNotFoundError,
    ObjectTypeMismatchError,
)
from orkp.domain.risk_ai_policy import validate_ai_risk_draft


class AIDraftService:
    """Create/read/version AI drafts without granting AI approval authority."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def create_draft(self, request: AIDraftCreateRequest) -> AIDraftResponse:
        payload = self._build_payload(request)
        try:
            draft, version = self.repo.create_object(
                object_type="ai_draft",
                payload=payload.model_dump(mode="json"),
                owner_user_id=request.initiated_by_user_id,
                created_by=request.initiated_by_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise
        return self._response(draft, version.version_no, payload)

    def get_draft(self, draft_hex: str) -> AIDraftResponse:
        draft, payload = self._load_current_draft(draft_hex)
        return self._response(draft, draft.current_version, payload)

    def regenerate_draft(
        self,
        draft_hex: str,
        request: AIDraftRegenerateRequest,
    ) -> AIDraftResponse:
        draft, _ = self._load_current_draft(draft_hex)
        payload = self._build_payload(request)
        try:
            version = self.repo.create_version(
                draft.object_uuid,
                payload.model_dump(mode="json"),
                request.actor_user_id,
            )
            self.repo.session.commit()
        except Exception:
            self.repo.session.rollback()
            raise
        return self._response(draft, version.version_no, payload)

    def _build_payload(
        self,
        request: AIDraftCreateRequest | AIDraftRegenerateRequest,
    ) -> AIDraftPayload:
        self._validate_context_references(request)
        risk_support = None
        if request.risk_support is not None:
            risk_support = validate_ai_risk_draft(request.risk_support)
        return AIDraftPayload(
            prompt_text=request.prompt_text,
            model_id=request.model_id,
            context_refs=request.context_refs,
            blocks=request.blocks,
            confidence_score=request.confidence_score,
            initiated_by_user_id=request.initiated_by_user_id,
            target_domain=request.target_domain,
            risk_support=risk_support,
        )

    def _validate_context_references(
        self,
        request: AIDraftCreateRequest | AIDraftRegenerateRequest,
    ) -> None:
        for reference in request.context_refs:
            obj = self.repo.get_by_uuid_hex(reference.object_uuid)
            if obj is None:
                raise ObjectNotFoundError(
                    f"AI grounding source {reference.object_uuid} not found"
                )
            if obj.object_type == "ai_draft":
                raise ObjectTypeMismatchError(
                    "AI drafts cannot be used as grounding sources for another AI draft"
                )
            version = self.repo.get_version(obj.object_uuid, reference.object_version)
            if version is None:
                raise ObjectNotFoundError(
                    "AI grounding source "
                    f"{reference.object_uuid} v{reference.object_version} not found"
                )

    def _load_current_draft(self, draft_hex: str):
        draft = self.repo.get_by_uuid_hex(draft_hex)
        if draft is None:
            raise ObjectNotFoundError(f"AI draft {draft_hex} not found")
        if draft.object_type != "ai_draft":
            raise ObjectTypeMismatchError(
                f"Expected ai_draft, got '{draft.object_type}'"
            )
        if draft.lifecycle_state != "draft":
            raise InvalidLifecycleStateError(
                "AI-generated content must remain draft until human workflow takes ownership"
            )
        version = self.repo.get_version(draft.object_uuid, draft.current_version)
        if version is None:
            raise ObjectNotFoundError(
                f"AI draft {draft.uuid_hex} version {draft.current_version} not found"
            )
        try:
            payload = AIDraftPayload(**dict(version.payload_json or {}))
        except ValidationError as exc:
            raise InvalidPersistedPayloadError(
                f"Persisted AI draft {draft.uuid_hex} payload is invalid"
            ) from exc
        return draft, payload

    @staticmethod
    def _response(draft, version_no: int, payload: AIDraftPayload) -> AIDraftResponse:
        return AIDraftResponse(
            draft_uuid=draft.uuid_hex,
            object_version=version_no,
            lifecycle_state="draft",
            owner_user_id=draft.owner_user_id,
            payload=payload,
        )
