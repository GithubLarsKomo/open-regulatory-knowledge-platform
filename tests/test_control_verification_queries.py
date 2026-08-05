"""Tests for risk-analysis control-verification read queries."""

from types import SimpleNamespace
from uuid import uuid4

from orkp.domain import control_verification_queries as queries


class _FakeRepo:
    def __init__(self, risk_analysis_uuid, relations):
        self.risk_analysis_uuid = risk_analysis_uuid
        self.relations = relations
        self.risk_analysis = SimpleNamespace(
            object_uuid=risk_analysis_uuid.bytes,
            object_type="risk_analysis",
            lifecycle_state="draft",
            current_version=2,
        )

    def get_by_uuid_hex(self, uuid_hex):
        if uuid_hex == self.risk_analysis_uuid.hex:
            return self.risk_analysis
        return None

    def get_version(self, object_uuid, version_no):
        if object_uuid == self.risk_analysis.object_uuid and version_no == 2:
            return SimpleNamespace(version_no=2, payload_json={})
        return None

    def list_active_relations_for_target(self, target_uuid):
        assert target_uuid == self.risk_analysis.object_uuid
        return self.relations


def _relation(source_uuid, *, target_version=2, role="verifies_control_for"):
    return SimpleNamespace(
        source_uuid=source_uuid.bytes,
        source_version=1,
        target_version=target_version,
        relation_type="derived_from",
        properties={"role": role},
    )


def test_listing_uses_current_risk_analysis_version_and_stable_order(monkeypatch):
    risk_analysis_uuid = uuid4()
    current_a = uuid4()
    current_b = uuid4()
    historical = uuid4()
    wrong_role = uuid4()

    relations = [
        _relation(current_b),
        _relation(historical, target_version=1),
        _relation(wrong_role, role="other"),
        _relation(current_a),
        _relation(current_b),
    ]
    repo = _FakeRepo(risk_analysis_uuid, relations)

    def fake_get_verification(self, object_uuid, object_version):
        return SimpleNamespace(
            object_uuid=object_uuid,
            object_version=object_version,
        )

    monkeypatch.setattr(
        queries.ControlVerificationService,
        "get_verification",
        fake_get_verification,
    )

    result = queries.list_control_verifications_for_risk_analysis(
        repo,
        risk_analysis_uuid.hex,
    )

    assert [item.object_uuid for item in result] == sorted(
        [current_a.hex, current_b.hex]
    )
