"""Exact relation gates for cross-domain PER section sources."""

from uuid import UUID

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import BenefitRiskAnalysisPayload
from orkp.domain.exceptions import BaselineValidationError, ORKPError
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.post_market_models import RiskImpactAssessmentDraftPayload
from orkp.domain.risk_models import ResidualRiskEvaluationPayload
from orkp.domain.versioned_loader import load_versioned_object


def validate_cross_domain_section_traceability(
    repo: RegulatoryObjectRepository,
    request: PERReportBaselineCreateRequest,
) -> None:
    """Reject formally shaped cross-domain objects that lack canonical provenance."""
    for reference in request.benefit_risk_sources:
        try:
            loaded = load_versioned_object(
                repo,
                reference.object_uuid,
                reference.object_version,
                "benefit_risk",
            )
            payload = BenefitRiskAnalysisPayload(**loaded.payload)
            residual = load_versioned_object(
                repo,
                payload.residual_evaluation.object_uuid,
                payload.residual_evaluation.object_version,
                "residual_risk_evaluation",
            )
            residual_payload = ResidualRiskEvaluationPayload(**residual.payload)
        except (ORKPError, ValidationError) as exc:
            raise BaselineValidationError(
                "Benefit-Risk source traceability context is invalid"
            ) from exc

        if residual_payload.acceptable or not residual_payload.benefit_risk_required:
            raise BaselineValidationError(
                "Benefit-Risk source residual evaluation does not require benefit-risk analysis"
            )
        if (
            residual_payload.risk_analysis_uuid != payload.risk_analysis.object_uuid
            or residual_payload.risk_analysis_version
            != payload.risk_analysis.object_version
        ):
            raise BaselineValidationError(
                "Benefit-Risk source and residual evaluation reference different Risk Analysis versions"
            )
        if (
            residual_payload.risk_policy_uuid != payload.risk_policy.object_uuid
            or residual_payload.risk_policy_version != payload.risk_policy.object_version
        ):
            raise BaselineValidationError(
                "Benefit-Risk source and residual evaluation reference different Risk Policy versions"
            )

        residual_uuid = residual.object.object_uuid
        risk_uuid = UUID(payload.risk_analysis.object_uuid).bytes
        policy_uuid = UUID(payload.risk_policy.object_uuid).bytes
        _require_relation(
            repo,
            loaded.object.object_uuid,
            loaded.version.version_no,
            "benefit_risk_for",
            residual_uuid,
            payload.residual_evaluation.object_version,
        )
        _require_relation(
            repo,
            loaded.object.object_uuid,
            loaded.version.version_no,
            "uses_risk_policy",
            policy_uuid,
            payload.risk_policy.object_version,
        )
        _require_relation(
            repo,
            residual_uuid,
            residual.version.version_no,
            "residual_of",
            risk_uuid,
            payload.risk_analysis.object_version,
        )
        _require_relation(
            repo,
            residual_uuid,
            residual.version.version_no,
            "uses_risk_policy",
            policy_uuid,
            payload.risk_policy.object_version,
        )

    for reference in request.pmpf_assessments:
        try:
            loaded = load_versioned_object(
                repo,
                reference.object_uuid,
                reference.object_version,
                "risk_impact_assessment",
            )
            payload = RiskImpactAssessmentDraftPayload(**loaded.payload)
        except (ORKPError, ValidationError) as exc:
            raise BaselineValidationError(
                "PMPF assessment traceability context is invalid"
            ) from exc
        information_uuid = UUID(payload.post_market_information.object_uuid).bytes
        risk_uuid = UUID(payload.risk_analysis.object_uuid).bytes
        _require_relation(
            repo,
            loaded.object.object_uuid,
            loaded.version.version_no,
            "derived_from",
            information_uuid,
            payload.post_market_information.object_version,
            role="impact_assessment_source",
        )
        _require_relation(
            repo,
            loaded.object.object_uuid,
            loaded.version.version_no,
            "derived_from",
            risk_uuid,
            payload.risk_analysis.object_version,
            role="assessed_risk",
        )
        _require_relation(
            repo,
            information_uuid,
            payload.post_market_information.object_version,
            "impacts_risk",
            risk_uuid,
            payload.risk_analysis.object_version,
        )
        _require_relation(
            repo,
            risk_uuid,
            payload.risk_analysis.object_version,
            "informed_by",
            information_uuid,
            payload.post_market_information.object_version,
        )


def _require_relation(
    repo: RegulatoryObjectRepository,
    source_uuid: bytes,
    source_version: int,
    relation_type: str,
    target_uuid: bytes,
    target_version: int,
    *,
    role: str | None = None,
) -> None:
    for relation in repo.list_active_relations_for_source(source_uuid):
        if (
            relation.relation_type == relation_type
            and relation.source_version == source_version
            and relation.target_uuid == target_uuid
            and relation.target_version == target_version
            and (
                role is None
                or (
                    relation.properties is not None
                    and relation.properties.get("role") == role
                )
            )
        ):
            return
    suffix = f" with role '{role}'" if role else ""
    raise BaselineValidationError(
        f"Cross-domain PER source lacks exact {relation_type}{suffix} relation"
    )