"""Regression tests for residual-risk error handling."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import InvalidObjectIdentifierError
from orkp.domain.residual_risk_evaluation_service import ResidualRiskEvaluationService
from orkp.domain.risk_models import ResidualRiskEvaluationCreateRequest


def _request() -> ResidualRiskEvaluationCreateRequest:
    return ResidualRiskEvaluationCreateRequest(
        risk_analysis_version=1,
        initial_evaluation_uuid=uuid.uuid4().hex,
        initial_evaluation_version=1,
        control_verifications=[{"object_uuid": uuid.uuid4().hex, "object_version": 1}],
        residual_severity="minor",
        residual_probability="unlikely",
        evaluator_user_id="u1",
    )


def test_service_rejects_malformed_risk_analysis_uuid_with_domain_error():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        with pytest.raises(InvalidObjectIdentifierError):
            ResidualRiskEvaluationService(repo).create_evaluation(
                "not-a-uuid", _request()
            )


def test_api_maps_malformed_risk_analysis_uuid_to_422():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    client = TestClient(create_app(session_factory_override=test_session))

    response = client.post(
        "/api/v1/risk-analyses/not-a-uuid/residual-evaluations",
        json=_request().model_dump(),
    )

    assert response.status_code == 422
    assert "Invalid UUID format" in response.json()["detail"]
