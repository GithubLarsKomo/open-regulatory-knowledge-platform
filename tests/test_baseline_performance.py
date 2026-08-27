"""Functional and deterministic query-budget guards for baseline freezing."""

from sqlalchemy import event


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


def _seed_refs(repo, count: int):
    refs = []
    for index in range(count):
        obj, _ = repo.create_object(
            "claim",
            {"index": index, "wording": f"baseline performance claim {index}"},
            "baseline-performance",
            "baseline-performance",
        )
        refs.append((obj.object_uuid, 1))
    repo.session.commit()
    repo.session.expunge_all()
    return refs


def test_baseline_freeze_100_items_has_constant_query_budget(repo, engine):
    refs = _seed_refs(repo, 100)

    def freeze_and_verify():
        baseline = repo.create_baseline(
            "performance baseline",
            None,
            refs,
            "baseline-performance",
        )
        baseline_uuid = baseline.baseline_uuid
        repo.session.commit()
        return repo.list_baseline_items(baseline_uuid)

    items, statements = _count_sql(engine, freeze_and_verify)

    assert len(items) == 100
    assert statements == 5
    assert {item.version_no for item in items} == {1}
    assert {item.object_type for item in items} == {"claim"}


def test_baseline_freeze_preserves_deleted_object_snapshot(repo):
    obj, _ = repo.create_object(
        "claim",
        {"wording": "frozen before deletion"},
        "baseline-performance",
        "baseline-performance",
    )
    repo.session.commit()
    repo.soft_delete(obj.object_uuid, "baseline-performance")
    repo.session.commit()

    baseline = repo.create_baseline(
        "deleted object baseline",
        None,
        [(obj.object_uuid, 1)],
        "baseline-performance",
    )
    baseline_uuid = baseline.baseline_uuid
    repo.session.commit()

    [item] = repo.list_baseline_items(baseline_uuid)
    assert item.object_type == "claim"
    assert item.version_no == 1
    assert item.snapshot_json == {"wording": "frozen before deletion"}


def test_baseline_freeze_event_keeps_original_item_count(repo):
    refs = _seed_refs(repo, 3)
    baseline = repo.create_baseline(
        "event count baseline",
        None,
        refs,
        "baseline-performance",
    )
    baseline_uuid = baseline.baseline_uuid
    repo.session.commit()

    events = repo.get_event_history(baseline_uuid)
    frozen = [event for event in events if event.event_type == "baseline_frozen"]

    assert len(frozen) == 1
    assert frozen[0].event_data == {"name": "event count baseline", "item_count": 3}
