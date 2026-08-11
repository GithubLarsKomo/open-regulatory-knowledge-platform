"""Prepare frozen, deterministic coverage for the canonical ten PER sections."""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.benefit_risk_models import BenefitRiskAnalysisPayload
from orkp.domain.exceptions import BaselineValidationError, ORKPError
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_section_coverage_models import PERCanonicalSection
from orkp.domain.post_market_models import (
    PostMarketInformationPayload,
    RiskImpactAssessmentDraftPayload,
)
from orkp.domain.risk_models import VersionedObjectReference
from orkp.domain.versioned_loader import load_versioned_object


@dataclass(frozen=True)
class FrozenCrossDomainSource:
    reference: VersionedObjectReference
    payload: dict
    supporting_refs: tuple[VersionedObjectReference, ...] = ()
    supporting_payloads: tuple[dict, ...] = ()


@dataclass
class PERSectionCoverageContext:
    object_versions: dict[bytes, int] = field(default_factory=dict)
    benefit_risk: list[FrozenCrossDomainSource] = field(default_factory=list)
    pmpf: list[FrozenCrossDomainSource] = field(default_factory=list)


class PERSectionCoverageService:
    """Validate explicit cross-domain sources and build canonical section coverage."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def prepare_cross_domain_context(
        self,
        product: VersionedObjectReference,
        request: PERReportBaselineCreateRequest,
    ) -> PERSectionCoverageContext:
        context = PERSectionCoverageContext()
        for reference in request.benefit_risk_sources:
            context.benefit_risk.append(
                self._load_benefit_risk_source(product, reference, context.object_versions)
            )
        for reference in request.pmpf_assessments:
            context.pmpf.append(
                self._load_pmpf_source(product, reference, context.object_versions)
            )
        context.benefit_risk.sort(key=lambda item: self._ref_key(item.reference))
        context.pmpf.sort(key=lambda item: self._ref_key(item.reference))
        return context

    def build_sections(
        self,
        performance_report,
        gap_report,
        completeness_ref: VersionedObjectReference,
        context: PERSectionCoverageContext,
    ) -> list[PERCanonicalSection]:
        product_ref = VersionedObjectReference(
            object_uuid=performance_report.product.object_uuid,
            object_version=performance_report.product.object_version,
        )
        product_data = dict(performance_report.product.snapshot or {})
        intended_purpose = product_data.get("intended_purpose")

        performance_by_type = {
            section.section_type: section for section in performance_report.sections
        }
        scientific = self._performance_section(
            "scientific_validity",
            "PER-SECTION-SCIENTIFIC-VALIDITY-MISSING",
            performance_by_type.get("scientific_validity"),
        )
        analytical = self._performance_section(
            "analytical_performance",
            "PER-SECTION-ANALYTICAL-PERFORMANCE-MISSING",
            performance_by_type.get("analytical_performance"),
        )
        clinical = self._performance_section(
            "clinical_performance",
            "PER-SECTION-CLINICAL-PERFORMANCE-MISSING",
            performance_by_type.get("clinical_performance"),
        )

        claim_refs, evidence_refs = self._claim_evidence_refs(
            performance_report,
            gap_report,
        )
        claims_refs = self._sorted_unique_refs([*claim_refs, *evidence_refs])
        claims_section = PERCanonicalSection(
            section_id="claims_and_evidence",
            status="available" if claim_refs else "missing",
            source_refs=claims_refs,
            data={
                "claim_count": len(claim_refs),
                "evidence_count": len(evidence_refs),
            },
            gap_code=None if claim_refs else "PER-SECTION-CLAIMS-EVIDENCE-MISSING",
        )

        trace_refs = self._traceability_refs(performance_report)
        traceability = PERCanonicalSection(
            section_id="traceability_appendix",
            status="available" if trace_refs else "missing",
            source_refs=trace_refs,
            data={"source_count": len(trace_refs)},
            gap_code=(
                None if trace_refs else "PER-SECTION-TRACEABILITY-MISSING"
            ),
        )

        risk_benefit = self._cross_domain_section(
            "risk_benefit_analysis",
            "PER-SECTION-RISK-BENEFIT-MISSING",
            context.benefit_risk,
        )
        pmpf = self._cross_domain_section(
            "pmpf_summary",
            "PER-SECTION-PMPF-MISSING",
            context.pmpf,
        )

        return [
            PERCanonicalSection(
                section_id="cover_page",
                status="available",
                source_refs=[product_ref],
                data={"product": product_data},
            ),
            PERCanonicalSection(
                section_id="intended_purpose",
                status=(
                    "available"
                    if isinstance(intended_purpose, str) and intended_purpose.strip()
                    else "missing"
                ),
                source_refs=[product_ref],
                data=(
                    {"intended_purpose": intended_purpose}
                    if isinstance(intended_purpose, str) and intended_purpose.strip()
                    else {}
                ),
                gap_code=(
                    None
                    if isinstance(intended_purpose, str) and intended_purpose.strip()
                    else "PER-SECTION-INTENDED-PURPOSE-MISSING"
                ),
            ),
            scientific,
            analytical,
            clinical,
            claims_section,
            risk_benefit,
            pmpf,
            traceability,
            PERCanonicalSection(
                section_id="completeness_report",
                status="available",
                source_refs=[completeness_ref],
                data={
                    "complete": gap_report.complete,
                    "performance_claim_count": gap_report.performance_claim_count,
                    "gap_claim_count": gap_report.gap_claim_count,
                },
            ),
        ]

    def _load_benefit_risk_source(
        self,
        product: VersionedObjectReference,
        reference: VersionedObjectReference,
        object_versions: dict[bytes, int],
    ) -> FrozenCrossDomainSource:
        loaded = self._load_approved(reference, "benefit_risk", "Benefit-Risk")
        try:
            payload = BenefitRiskAnalysisPayload(**loaded.payload)
        except ValidationError as exc:
            raise BaselineValidationError(
                "Benefit-Risk source payload is invalid"
            ) from exc
        risk = self._load_exact(payload.risk_analysis, "risk_analysis", "Risk Analysis")
        self._assert_risk_product_link(risk, product)
        residual = self._load_exact(
            payload.residual_evaluation,
            "residual_risk_evaluation",
            "Residual Risk Evaluation",
        )
        policy = self._load_exact(payload.risk_policy, "risk_policy", "Risk Policy")
        refs = (
            payload.risk_analysis,
            payload.residual_evaluation,
            payload.risk_policy,
        )
        for source in (loaded, risk, residual, policy):
            self._add_object_version(
                object_versions,
                source.object.object_uuid,
                source.version.version_no,
            )
        return FrozenCrossDomainSource(
            reference=reference,
            payload=payload.model_dump(mode="json"),
            supporting_refs=refs,
            supporting_payloads=(
                dict(risk.payload),
                dict(residual.payload),
                dict(policy.payload),
            ),
        )

    def _load_pmpf_source(
        self,
        product: VersionedObjectReference,
        reference: VersionedObjectReference,
        object_versions: dict[bytes, int],
    ) -> FrozenCrossDomainSource:
        assessment = self._load_approved(
            reference,
            "risk_impact_assessment",
            "PMPF Risk Impact Assessment",
        )
        try:
            assessment_payload = RiskImpactAssessmentDraftPayload(**assessment.payload)
        except ValidationError as exc:
            raise BaselineValidationError(
                "PMPF Risk Impact Assessment payload is invalid"
            ) from exc
        if assessment_payload.outcome == "pending":
            raise BaselineValidationError(
                "PMPF Risk Impact Assessment must contain a completed outcome"
            )
        information = self._load_exact(
            assessment_payload.post_market_information,
            "post_market_information",
            "PMPF information",
        )
        try:
            information_payload = PostMarketInformationPayload(**information.payload)
        except ValidationError as exc:
            raise BaselineValidationError("PMPF information payload is invalid") from exc
        if information_payload.source_type != "pmpf":
            raise BaselineValidationError(
                "PMPF section source must reference post_market_information with source_type='pmpf'"
            )
        if information_payload.risk_analysis != assessment_payload.risk_analysis:
            raise BaselineValidationError(
                "PMPF assessment and information must reference the same Risk Analysis"
            )
        risk = self._load_exact(
            assessment_payload.risk_analysis,
            "risk_analysis",
            "Risk Analysis",
        )
        self._assert_risk_product_link(risk, product)
        for source in (assessment, information, risk):
            self._add_object_version(
                object_versions,
                source.object.object_uuid,
                source.version.version_no,
            )
        return FrozenCrossDomainSource(
            reference=reference,
            payload=assessment_payload.model_dump(mode="json"),
            supporting_refs=(
                assessment_payload.post_market_information,
                assessment_payload.risk_analysis,
            ),
            supporting_payloads=(
                information_payload.model_dump(mode="json"),
                dict(risk.payload),
            ),
        )

    def _load_approved(
        self,
        reference: VersionedObjectReference,
        object_type: str,
        label: str,
    ):
        try:
            loaded = load_versioned_object(
                self.repo,
                reference.object_uuid,
                reference.object_version,
                object_type,
                allowed_lifecycle_states=["approved", "effective"],
            )
        except ORKPError as exc:
            raise BaselineValidationError(f"{label} source is not usable: {exc}") from exc
        if loaded.version.status != "approved":
            raise BaselineValidationError(f"{label} source version is not approved")
        return loaded

    def _load_exact(
        self,
        reference: VersionedObjectReference,
        object_type: str,
        label: str,
    ):
        try:
            return load_versioned_object(
                self.repo,
                reference.object_uuid,
                reference.object_version,
                object_type,
            )
        except ORKPError as exc:
            raise BaselineValidationError(f"{label} context is invalid: {exc}") from exc

    def _assert_risk_product_link(self, risk, product: VersionedObjectReference) -> None:
        product_uuid = UUID(product.object_uuid).bytes
        exact_outgoing = any(
            relation.relation_type == "applies_to_product"
            and relation.source_version == risk.version.version_no
            and relation.target_uuid == product_uuid
            and relation.target_version == product.object_version
            for relation in self.repo.list_active_relations_for_source(
                risk.object.object_uuid
            )
        )
        exact_incoming = any(
            relation.relation_type == "has_risk"
            and relation.source_uuid == product_uuid
            and relation.source_version == product.object_version
            and relation.target_version == risk.version.version_no
            for relation in self.repo.list_active_relations_for_target(
                risk.object.object_uuid
            )
        )
        if not exact_outgoing and not exact_incoming:
            raise BaselineValidationError(
                "Cross-domain PER source Risk Analysis is not pinned to the frozen Product"
            )

    @classmethod
    def _performance_section(cls, section_id: str, gap_code: str, section):
        items = [] if section is None else list(section.items)
        refs = []
        for item in items:
            refs.extend(
                [
                    cls._snapshot_ref(item.performance_result),
                    cls._snapshot_ref(item.study),
                    *(cls._snapshot_ref(claim) for claim in item.claims),
                    *(
                        cls._snapshot_ref(source)
                        for source in item.statistical_sources
                    ),
                ]
            )
        refs = cls._sorted_unique_refs(refs)
        return PERCanonicalSection(
            section_id=section_id,
            status="available" if items else "missing",
            source_refs=refs,
            data={"performance_result_count": len(items)},
            gap_code=None if items else gap_code,
        )

    @classmethod
    def _claim_evidence_refs(cls, performance_report, gap_report):
        claims = []
        evidence = []
        for section in performance_report.sections:
            for item in section.items:
                claims.extend(cls._snapshot_ref(claim) for claim in item.claims)
                evidence.append(cls._snapshot_ref(item.performance_result))
                evidence.extend(
                    cls._snapshot_ref(source) for source in item.statistical_sources
                )
        for claim_item in gap_report.claims:
            claims.append(claim_item.claim)
            evidence.extend(
                finding.evidence
                for finding in claim_item.findings
                if finding.evidence is not None
            )
        return cls._sorted_unique_refs(claims), cls._sorted_unique_refs(evidence)

    @classmethod
    def _traceability_refs(cls, performance_report):
        refs = []
        for section in performance_report.sections:
            for item in section.items:
                refs.extend(
                    [
                        cls._snapshot_ref(item.performance_result),
                        cls._snapshot_ref(item.study),
                        *(cls._snapshot_ref(claim) for claim in item.claims),
                        *(
                            cls._snapshot_ref(source)
                            for source in item.statistical_sources
                        ),
                    ]
                )
        return cls._sorted_unique_refs(refs)

    @classmethod
    def _cross_domain_section(cls, section_id: str, gap_code: str, sources):
        refs = []
        records = []
        for source in sources:
            refs.append(source.reference)
            refs.extend(source.supporting_refs)
            records.append(
                {
                    "source_ref": source.reference.model_dump(mode="json"),
                    "payload": source.payload,
                    "supporting_refs": [
                        ref.model_dump(mode="json") for ref in source.supporting_refs
                    ],
                    "supporting_payloads": list(source.supporting_payloads),
                }
            )
        refs = cls._sorted_unique_refs(refs)
        return PERCanonicalSection(
            section_id=section_id,
            status="available" if sources else "missing",
            source_refs=refs,
            data={"sources": records},
            gap_code=None if sources else gap_code,
        )

    @staticmethod
    def _snapshot_ref(snapshot):
        return VersionedObjectReference(
            object_uuid=snapshot.object_uuid,
            object_version=snapshot.object_version,
        )

    @staticmethod
    def _ref_key(reference: VersionedObjectReference):
        return reference.object_uuid, reference.object_version

    @classmethod
    def _sorted_unique_refs(cls, references):
        unique = {
            (reference.object_uuid, reference.object_version): reference
            for reference in references
        }
        return [unique[key] for key in sorted(unique)]

    @staticmethod
    def _add_object_version(
        object_versions: dict[bytes, int],
        object_uuid: bytes,
        version: int,
    ) -> None:
        existing = object_versions.get(object_uuid)
        if existing is not None and existing != version:
            raise BaselineValidationError(
                "PER section coverage cannot freeze conflicting versions of one object"
            )
        object_versions[object_uuid] = version
