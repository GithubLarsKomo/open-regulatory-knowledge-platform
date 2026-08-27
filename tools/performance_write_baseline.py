"""Targeted ORKP write-path performance measurements.

This supplements the read baseline with deterministic SQL-statement counts for
object and relation creation. It does not impose timing thresholds.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter_ns

from sqlalchemy.orm import Session

from orkp.db.repository import RegulatoryObjectRepository
from performance_baseline import QueryCounter, _make_engine, _p95

DEFAULT_REPETITIONS = 7
DEFAULT_WARMUPS = 2


def _summary(name: str, samples_ms: list[float], queries: list[int]) -> dict:
    return {
        "name": name,
        "timing_ms": {
            "median": round(statistics.median(samples_ms), 3),
            "p95": round(_p95(samples_ms), 3),
            "min": round(min(samples_ms), 3),
            "max": round(max(samples_ms), 3),
            "samples": [round(value, 3) for value in samples_ms],
        },
        "sql_queries": {
            "median": statistics.median(queries),
            "min": min(queries),
            "max": max(queries),
            "samples": queries,
        },
    }


def _object_create(repetitions: int, warmups: int) -> dict:
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    counter = QueryCounter(engine)
    samples_ms: list[float] = []
    queries: list[int] = []

    try:
        for index in range(warmups + repetitions):
            counter.reset()
            started = perf_counter_ns()
            obj, version = repo.create_object(
                object_type="claim",
                payload={"index": index, "text": f"write-baseline-{index}"},
                owner_user_id="performance-baseline",
                created_by="performance-baseline",
            )
            session.flush()
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000

            if obj.current_version != 1 or version.version_no != 1:
                raise RuntimeError("object_create returned an invalid initial version")

            if index >= warmups:
                samples_ms.append(elapsed_ms)
                queries.append(counter.count)

        session.rollback()
        result = _summary("repository_create_object", samples_ms, queries)
        result["workload"] = {"objects_per_sample": 1}
        result["expected_semantics"] = "object + v1 + created event flushed"
        return result
    finally:
        counter.close()
        session.close()
        engine.dispose()


def _relation_create(repetitions: int, warmups: int) -> dict:
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    counter = QueryCounter(engine)
    sample_count = warmups + repetitions

    try:
        product, _ = repo.create_object(
            object_type="product",
            payload={"name": "write-baseline-product"},
            owner_user_id="performance-baseline",
            created_by="performance-baseline",
        )
        claims: list[bytes] = []
        for index in range(sample_count):
            claim, _ = repo.create_object(
                object_type="claim",
                payload={"index": index},
                owner_user_id="performance-baseline",
                created_by="performance-baseline",
            )
            claims.append(claim.object_uuid)
        session.commit()
        session.expunge_all()

        samples_ms: list[float] = []
        queries: list[int] = []
        for index, claim_uuid in enumerate(claims):
            counter.reset()
            started = perf_counter_ns()
            relation = repo.create_relation(
                source_uuid=product.object_uuid,
                source_version=1,
                target_uuid=claim_uuid,
                target_version=1,
                relation_type="has_claim",
                created_by="performance-baseline",
            )
            session.flush()
            elapsed_ms = (perf_counter_ns() - started) / 1_000_000

            if relation.relation_type != "has_claim":
                raise RuntimeError("relation_create returned the wrong relation type")

            if index >= warmups:
                samples_ms.append(elapsed_ms)
                queries.append(counter.count)

        session.rollback()
        result = _summary("repository_create_relation", samples_ms, queries)
        result["workload"] = {"relations_per_sample": 1}
        result["expected_semantics"] = (
            "source/target versions and object types validated before insert"
        )
        return result
    finally:
        counter.close()
        session.close()
        engine.dispose()


def run(repetitions: int, warmups: int) -> dict:
    return {
        "schema_version": 1,
        "measurement_policy": {
            "timing_gate": False,
            "query_count_recorded": True,
            "warmups": warmups,
            "repetitions": repetitions,
        },
        "scenarios": [
            _object_create(repetitions, warmups),
            _relation_create(repetitions, warmups),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    args = parser.parse_args()

    if args.repetitions < 1 or args.warmups < 0:
        parser.error("--repetitions must be >=1 and --warmups must be >=0")

    payload = json.dumps(run(args.repetitions, args.warmups), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
