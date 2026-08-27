"""Deterministic guards for SQL-prefiltered Object Store keyword retrieval."""

from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_service import ObjectStoreKeywordRetrievalAdapter


def _repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    return engine, session, RegulatoryObjectRepository(session)


def _object(repo, wording: str, updated_at: datetime, object_type: str = "claim"):
    obj, _ = repo.create_object(
        object_type,
        {"wording": wording},
        "keyword-prefilter",
        "keyword-prefilter",
    )
    repo.session.flush()
    obj.updated_at = updated_at
    repo.session.commit()
    return obj


def test_keyword_prefilter_preserves_existing_scan_limit_window():
    engine, session, repo = _repo()
    try:
        old_match = _object(repo, "needle", datetime(2026, 1, 1))
        _object(repo, "new nonmatch one", datetime(2026, 1, 3))
        _object(repo, "new nonmatch two", datetime(2026, 1, 4))

        hits = ObjectStoreKeywordRetrievalAdapter(repo, scan_limit=2).search(
            "needle", limit=10
        )

        assert hits == []
        assert all(hit.reference.object_uuid != old_match.uuid_hex for hit in hits)
    finally:
        session.close()
        engine.dispose()


def test_keyword_prefilter_only_canonicalizes_sql_candidates():
    engine, session, repo = _repo()
    try:
        for index in range(100):
            wording = (
                f"performance marker {index}" if index % 10 == 0 else f"other {index}"
            )
            repo.create_object(
                "claim",
                {"wording": wording},
                "keyword-prefilter",
                "keyword-prefilter",
            )
        repo.session.commit()

        adapter = ObjectStoreKeywordRetrievalAdapter(repo, scan_limit=100)
        original = adapter._searchable_text
        canonicalized = 0

        def counted(payload):
            nonlocal canonicalized
            canonicalized += 1
            return original(payload)

        adapter._searchable_text = counted
        hits = adapter.search("performance marker", limit=20)

        assert len(hits) == 10
        assert canonicalized == 10
        assert all(hit.score == 1.0 for hit in hits)
    finally:
        session.close()
        engine.dispose()


def test_keyword_prefilter_keeps_single_query_adapter_budget():
    engine, session, repo = _repo()
    try:
        for index in range(20):
            wording = (
                f"clinical evidence {index}" if index % 2 == 0 else f"other {index}"
            )
            repo.create_object(
                "evidence",
                {"title": wording},
                "keyword-prefilter",
                "keyword-prefilter",
            )
        repo.session.commit()

        statements = 0

        def count_statement(*args, **kwargs):
            nonlocal statements
            statements += 1

        event.listen(engine, "before_cursor_execute", count_statement)
        try:
            hits = ObjectStoreKeywordRetrievalAdapter(repo, scan_limit=20).search(
                "clinical evidence", limit=5
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)

        assert len(hits) == 5
        assert statements == 1
    finally:
        session.close()
        engine.dispose()


def test_keyword_retrieval_preserves_unicode_matching_without_sql_prefilter():
    engine, session, repo = _repo()
    try:
        expected = _object(
            repo,
            "Überprüfung der klinischen Sensitivität",
            datetime(2026, 1, 5),
        )
        _object(repo, "other", datetime(2026, 1, 4))

        hits = ObjectStoreKeywordRetrievalAdapter(repo, scan_limit=10).search(
            "überprüfung", limit=10
        )

        assert len(hits) == 1
        assert hits[0].reference.object_uuid == expected.uuid_hex
        assert hits[0].score == 1.0
    finally:
        session.close()
        engine.dispose()
