"""Deterministic query-budget regressions for hybrid keyword retrieval."""

from sqlalchemy import event

from orkp.domain.ai_retrieval_models import HybridRetrievalRequest
from orkp.domain.ai_retrieval_service import (
    HybridRetrievalService,
    ObjectStoreKeywordRetrievalAdapter,
)


class EmptyVectorAdapter:
    def search(self, query_text: str, limit: int):
        return []


def _seed_claims(repo, count: int = 100) -> None:
    for index in range(count):
        wording = (
            f"performance evidence marker {index}"
            if index % 10 == 0
            else f"other material {index}"
        )
        repo.create_object(
            "claim",
            {"wording": wording},
            "performance-test",
            "performance-test",
        )
    repo.session.commit()
    repo.session.expunge_all()


def _count_sql(engine, operation):
    statements = 0

    def count_statement(*args, **kwargs):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        result = operation()
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
    return result, statements


def test_keyword_scan_loads_current_versions_in_one_statement(repo, engine):
    _seed_claims(repo)
    adapter = ObjectStoreKeywordRetrievalAdapter(repo)

    hits, statements = _count_sql(
        engine,
        lambda: adapter.search("performance evidence", limit=10),
    )

    assert len(hits) == 10
    assert all(hit.channel == "keyword" for hit in hits)
    assert statements == 1


def test_hybrid_keyword_retrieval_batches_exact_hit_validation(repo, engine):
    _seed_claims(repo)
    service = HybridRetrievalService(repo, EmptyVectorAdapter())
    request = HybridRetrievalRequest(
        query_text="performance evidence",
        keyword_limit=10,
        vector_limit=10,
        max_results=10,
    )

    response, statements = _count_sql(engine, lambda: service.retrieve(request))

    assert len(response.results) == 10
    assert all(result.channels == ["keyword"] for result in response.results)
    assert statements == 2
