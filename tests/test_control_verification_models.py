"""Focused validation tests for Epic 007 control verification models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from orkp.domain.risk_models import (
    ControlVerificationCreateRequest,
    ResidualRiskEvaluationCreateRequest,
    VersionedObjectReference,
)


def ref():
    return {"object_uuid": uuid4().hex, "object_version": 1}


def valid_request(**overrides):
    data = {
        "risk_analysis": ref(),
        "risk_control": ref(),
        "initial_evaluation": ref(),
        "risk_policy": ref(),
        "evidence": [ref()],
        "verification_method": "test",
        "verification_scope": "Implementation and effectiveness",
        "implementation_verified": True,
        "effectiveness_verified": True,
        "no_new_uncontrolled_risks": True,
        "effectiveness_result": "effective",
        "conclusion": "passed",
        "verified_by_user_id": "reviewer-1",
    }
    data.update(overrides)
    return data


def test_valid_control_verification_request():
    request = ControlVerificationCreateRequest(**valid_request())
    assert request.conclusion == "passed"
    assert request.risk_control.object_version == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("verification_method", "unknown"),
        ("effectiveness_result", "unknown"),
        ("conclusion", "unknown"),
        ("verification_scope", "   "),
    ],
)
def test_rejects_invalid_control_verification_values(field, value):
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(**valid_request(**{field: value}))


def test_rejects_client_derived_fields():
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(
            **valid_request(verification_id="client-controlled")
        )


def test_passed_requires_all_positive_flags():
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(
            **valid_request(effectiveness_verified=False)
        )


def test_passed_requires_effective_result():
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(
            **valid_request(effectiveness_result="partially_effective")
        )


def test_passed_with_limitations_requires_limitations():
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(
            **valid_request(conclusion="passed_with_limitations")
        )


def test_rejects_duplicate_evidence():
    evidence = ref()
    with pytest.raises(ValidationError):
        ControlVerificationCreateRequest(
            **valid_request(evidence=[evidence, evidence])
        )


def test_versioned_reference_requires_uuid_and_positive_version():
    with pytest.raises(ValidationError):
        VersionedObjectReference(object_uuid="not-a-uuid", object_version=1)
    with pytest.raises(ValidationError):
        VersionedObjectReference(object_uuid=uuid4().hex, object_version=0)


def test_residual_request_requires_explicit_unique_verifications():
    verification = ref()
    base = {
        "risk_analysis_version": 1,
        "initial_evaluation_uuid": uuid4().hex,
        "initial_evaluation_version": 1,
        "residual_severity": "minor",
        "residual_probability": "unlikely",
        "evaluator_user_id": "reviewer-1",
    }
    with pytest.raises(ValidationError):
        ResidualRiskEvaluationCreateRequest(**base)
    with pytest.raises(ValidationError):
        ResidualRiskEvaluationCreateRequest(
            **base,
            control_verifications=[verification, verification],
        )
