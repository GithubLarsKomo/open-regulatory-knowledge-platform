"""Regression test for one-version-per-object Risk Report baselines."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.exceptions import BaselineValidationError
from orkp.domain.risk_report_models import RiskReportBaselineCreateRequest
from orkp.domain.risk_report_service import RiskReportService


def test_baseline_rejects_multiple_versions_of_same_supporting_object():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RegulatoryObjectRepository(session)
        risk, _ = repo.create_object(
            "risk_analysis",
            {"risk_id": "R-UNIQUE"},
            "risk-author",
            "risk-author",
        )
        repo.transition_state(risk.object_uuid, "in_review", "risk-author")
        repo.transition_state(risk.object_uuid, "approved", "risk-approver")
        hazard, _ = repo.create_object(
            "hazard",
            {"hazard_id": "H-UNIQUE", "description": "v1"},
            "risk-author",
            "risk-author",
        )
        repo.create_version(
            hazard.object_uuid,
            {"hazard_id": "H-UNIQUE", "description": "v2"},
            "risk-author",
        )
        session.commit()

        request = RiskReportBaselineCreateRequest(
            name="Ambiguous baseline",
            objects=[
                {"object_uuid": risk.uuid_hex, "object_version": 1},
                {"object_uuid": hazard.uuid_hex, "object_version": 1},
                {"object_uuid": hazard.uuid_hex, "object_version": 2},
            ],
            created_by_user_id="report-author",
        )

        with pytest.raises(BaselineValidationError, match="exactly one version per object"):
            RiskReportService(repo).create_baseline(request)
