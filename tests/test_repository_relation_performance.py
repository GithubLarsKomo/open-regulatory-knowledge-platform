"""Deterministic regression tests for relation validation roundtrips."""

from sqlalchemy import event


def test_create_relation_uses_at_most_two_sql_statements(repo, session, engine):
    product, _ = repo.create_object("product", {}, "u1", "u1")
    claim, _ = repo.create_object("claim", {}, "u2", "u2")
    product_uuid = product.object_uuid
    claim_uuid = claim.object_uuid
    session.flush()

    statements = 0

    def count_statement(*args, **kwargs):
        nonlocal statements
        statements += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        relation = repo.create_relation(
            product_uuid,
            1,
            claim_uuid,
            1,
            "has_claim",
            "u1",
        )
        session.flush()
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)

    assert relation.relation_type == "has_claim"
    assert statements <= 2


def test_create_relation_handles_identical_endpoint_pair(repo, session):
    evidence, _ = repo.create_object("evidence", {}, "u1", "u1")
    evidence_uuid = evidence.object_uuid
    session.flush()

    relation = repo.create_relation(
        evidence_uuid,
        1,
        evidence_uuid,
        1,
        "supersedes",
        "u1",
    )
    session.flush()

    assert relation.source_uuid == evidence_uuid
    assert relation.target_uuid == evidence_uuid
    assert relation.relation_type == "supersedes"
