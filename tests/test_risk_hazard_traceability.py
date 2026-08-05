"""Regression tests for per-Hazard Risk approval traceability."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.risk_service import RiskService


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield RegulatoryObjectRepository(session)


def _object(repo, object_type: str, suffix: str):
    obj, _ = repo.create_object(
        object_type,
        {"id": f"{object_type}-{suffix}"},
        "owner",
        "owner",
    )
    return obj


def _relation(repo, source, target, relation_type: str):
    repo.create_relation(
        source_uuid=source.object_uuid,
        source_version=source.current_version,
        target_uuid=target.object_uuid,
        target_version=target.current_version,
        relation_type=relation_type,
        created_by="owner",
    )


def _risk(repo):
    return _object(repo, "risk_analysis", "RA")


def _add_chain(
    repo,
    risk,
    suffix: str,
    *,
    omit: str | None = None,
):
    hazard = _object(repo, "hazard", suffix)
    sequence = _object(repo, "sequence_of_events", suffix)
    situation = _object(repo, "hazardous_situation", suffix)
    harm = _object(repo, "harm", suffix)

    _relation(repo, risk, hazard, "has_hazard")
    if omit == "sequence":
        return hazard, sequence, situation, harm

    _relation(repo, hazard, sequence, "followed_by")
    if omit == "situation":
        return hazard, sequence, situation, harm

    _relation(repo, sequence, situation, "creates_situation")
    if omit != "harm":
        _relation(repo, situation, harm, "may_cause")
    if omit != "estimation":
        _relation(repo, risk, situation, "estimated_for")
    return hazard, sequence, situation, harm


def _chain_codes(result):
    return [
        issue
        for issue in result["blocking_issues"]
        if issue.startswith("[RISK-CHAIN-")
    ]


def test_second_incomplete_hazard_cannot_be_masked_by_complete_chain(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "COMPLETE")
    _add_chain(repo, risk, "INCOMPLETE", omit="sequence")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-SEQUENCE-001" in issue for issue in _chain_codes(result))
    assert "followed_by" in result["missing_relations"]


def test_missing_situation_on_any_hazard_is_blocking(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "COMPLETE")
    _add_chain(repo, risk, "NO-SITUATION", omit="situation")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-SITUATION-001" in issue for issue in _chain_codes(result))
    assert "creates_situation" in result["missing_relations"]


def test_missing_harm_on_any_hazard_is_blocking(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "COMPLETE")
    _add_chain(repo, risk, "NO-HARM", omit="harm")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-HARM-001" in issue for issue in _chain_codes(result))
    assert "may_cause" in result["missing_relations"]


def test_missing_estimated_for_relation_is_a_distinct_blocker(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "NO-ESTIMATION", omit="estimation")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-ESTIMATION-001" in issue for issue in _chain_codes(result))
    assert "estimated_for" in result["missing_relations"]


def test_historical_risk_chain_does_not_satisfy_current_risk_version(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "HISTORICAL")
    repo.create_version(
        risk.object_uuid,
        {"id": "risk_analysis-RA-v2"},
        "owner",
    )
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-HAZARD-001" in issue for issue in _chain_codes(result))


def test_stale_sequence_target_version_is_blocking(repo):
    risk = _risk(repo)
    _, sequence, _, _ = _add_chain(repo, risk, "STALE-SEQUENCE")
    repo.create_version(
        sequence.object_uuid,
        {"id": "sequence_of_events-STALE-SEQUENCE-v2"},
        "owner",
    )
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert any("RISK-CHAIN-SEQUENCE-001" in issue for issue in _chain_codes(result))


def test_complete_multi_hazard_graph_passes_traceability_portion(repo):
    risk = _risk(repo)
    _add_chain(repo, risk, "ONE")
    _add_chain(repo, risk, "TWO")
    repo.session.commit()

    result = RiskService(repo).evaluate_risk_completeness(risk.uuid_hex)

    assert _chain_codes(result) == []
