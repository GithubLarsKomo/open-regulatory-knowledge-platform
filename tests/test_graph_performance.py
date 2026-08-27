"""Deterministic query-budget guards for exact-version graph projection."""

from sqlalchemy import event

from orkp.domain.graph_service import GraphProjectionService


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


def _create_evidence(repo, title: str):
    obj, _ = repo.create_object(
        "evidence",
        {"title": title},
        "graph-performance",
        "graph-performance",
    )
    return obj


def test_traceability_depth_zero_uses_one_statement(repo, engine):
    root = _create_evidence(repo, "root")
    repo.session.commit()
    repo.session.expunge_all()

    graph, statements = _count_sql(
        engine,
        lambda: GraphProjectionService(repo).traceability(root.uuid_hex, 1, depth=0),
    )

    assert len(graph.nodes) == 1
    assert graph.edges == []
    assert statements == 1


def test_traceability_depth_one_51_nodes_uses_three_statements(repo, engine):
    root = _create_evidence(repo, "root")
    for index in range(50):
        child = _create_evidence(repo, f"child {index}")
        repo.create_relation(
            root.object_uuid,
            1,
            child.object_uuid,
            1,
            "supersedes",
            "graph-performance",
        )
    repo.session.commit()
    root_hex = root.uuid_hex
    repo.session.expunge_all()

    graph, statements = _count_sql(
        engine,
        lambda: GraphProjectionService(repo).traceability(root_hex, 1, depth=1),
    )

    assert len(graph.nodes) == 51
    assert len(graph.edges) == 50
    assert statements <= 3


def test_traceability_depth_two_51_nodes_scales_with_depth(repo, engine):
    root = _create_evidence(repo, "root")
    intermediates = []
    for index in range(10):
        child = _create_evidence(repo, f"intermediate {index}")
        intermediates.append(child)
        repo.create_relation(
            root.object_uuid,
            1,
            child.object_uuid,
            1,
            "supersedes",
            "graph-performance",
        )

    for index in range(40):
        leaf = _create_evidence(repo, f"leaf {index}")
        parent = intermediates[index % len(intermediates)]
        repo.create_relation(
            parent.object_uuid,
            1,
            leaf.object_uuid,
            1,
            "supersedes",
            "graph-performance",
        )

    repo.session.commit()
    root_hex = root.uuid_hex
    repo.session.expunge_all()

    graph, statements = _count_sql(
        engine,
        lambda: GraphProjectionService(repo).traceability(root_hex, 1, depth=2),
    )

    assert len(graph.nodes) == 51
    assert len(graph.edges) == 50
    assert statements <= 4
