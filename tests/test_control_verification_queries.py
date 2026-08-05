"""Tests for version-pinned control-verification read paths."""

from types import SimpleNamespace
from uuid import uuid4

from orkp.domain import control_verification_queries as queries
from orkp.domain.control_verification_service import ControlVerificationService


class _FakeVersionedRepo:
    def __init__(self, object_uuid, object_type, relations):
        self.object_uuid = object_uuid
        self.relations = relations
        self.object = SimpleNamespace(
            object_uuid=object_uuid.bytes,
            object_type=object_type,
            lifecycle_state="draft",
            current_version=2,
        )

    def get_by_uuid_hex(self, uuid_hex):
        if uuid_hex == self.object_uuid.hex:
            return self.object
        return None

    def get_version(self, object_uuid, version_no):
        if object_uuid == self.object.object_uuid and version_no == 2:
            return SimpleNamespace(version_no=2, payload_json={})
        return None

    def list_active_relations_for_target(self, target_uuid):
        assert target_uuid == self.object.object_uuid
        return self.relations


def _relation(
    source_uuid,
    *,
    relation_type,
    target_version=2,
    role=None,
):
    properties = None if role is None else {"role": role}
    return SimpleNamespace(
        source_uuid=source_uuid.bytes,
        source_version=1,
        target_version=target_version,
        relation_type=relation_type,
        properties=properties,
    )


def _fake_response(object_uuid, object_version):
    return SimpleNamespace(
        object_uuid=object_uuid,
        object_version=object_version,
    )


def test_risk_analysis_listing_uses_current_version_and_stable_order(monkeypatch):
    risk_analysis_uuid = uuid4()
    current_a = uuid4()
    current_b = uuid4()
    historical = uuid4()
    wrong_role = uuid4()

    relations = [
        _relation(
            current_b,
            relation_type="derived_from",
            role="verifies_control_for",
        ),
        _relation(
            historical,
            relation_type="derived_from",
            target_version=1,
            role="verifies_control_for",
        ),
        _relation(
            wrong_role,
            relation_type="derived_from",
            role="other",
        ),
        _relation(
            current_a,
            relation_type="derived_from",
            role="verifies_control_for",
        ),
        _relation(
            current_b,
            relation_type="derived_from",
            role="verifies_control_for",
        ),
    ]
    repo = _FakeVersionedRepo(risk_analysis_uuid, "risk_analysis", relations)

    def fake_get_verification(self, object_uuid, object_version):
        return _fake_response(object_uuid, object_version)

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


def test_risk_control_listing_uses_current_version_and_stable_order(monkeypatch):
    risk_control_uuid = uuid4()
    current_a = uuid4()
    current_b = uuid4()
    historical = uuid4()
    wrong_type = uuid4()

    relations = [
        _relation(current_b, relation_type="verifies_control"),
        _relation(
            historical,
            relation_type="verifies_control",
            target_version=1,
        ),
        _relation(wrong_type, relation_type="derived_from"),
        _relation(current_a, relation_type="verifies_control"),
        _relation(current_b, relation_type="verifies_control"),
    ]
    repo = _FakeVersionedRepo(risk_control_uuid, "risk_control", relations)
    service = ControlVerificationService(repo)

    monkeypatch.setattr(
        service,
        "_response",
        _fake_response,
    )

    result = service.list_for_risk_control(risk_control_uuid.hex)

    assert [item.object_uuid for item in result] == sorted(
        [current_a.hex, current_b.hex]
    )
