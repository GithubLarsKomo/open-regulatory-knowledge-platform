"""Deterministic ORKP performance baseline harness.

The harness records timing and SQL query counts for representative core paths.
Timing values are observational only; no hard millisecond threshold is enforced.
Run comparisons on the same runtime/runner before drawing performance conclusions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from typing import Callable

import fastapi
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orkp.api.main import create_app
from orkp.db.models import Base
from orkp.db.repository import RegulatoryObjectRepository

DEFAULT_REPETITIONS = 7
DEFAULT_WARMUPS = 2


class QueryCounter:
    """Count SQL statements executed by one SQLAlchemy engine."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.count = 0
        event.listen(engine, "before_cursor_execute", self._before_cursor_execute)

    def _before_cursor_execute(self, *args, **kwargs) -> None:
        self.count += 1

    def reset(self) -> None:
        self.count = 0

    def close(self) -> None:
        event.remove(
            self.engine,
            "before_cursor_execute",
            self._before_cursor_execute,
        )


def _make_engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def _measure(
    name: str,
    operation: Callable[[], int],
    counter: QueryCounter,
    expected_rows: int,
    repetitions: int,
    warmups: int,
    workload: dict[str, int | str],
) -> dict:
    for _ in range(warmups):
        observed_rows = operation()
        if observed_rows != expected_rows:
            raise RuntimeError(
                f"{name}: warmup returned {observed_rows} rows; "
                f"expected {expected_rows}"
            )

    samples_ms: list[float] = []
    query_counts: list[int] = []

    for _ in range(repetitions):
        counter.reset()
        started = perf_counter_ns()
        observed_rows = operation()
        elapsed_ms = (perf_counter_ns() - started) / 1_000_000

        if observed_rows != expected_rows:
            raise RuntimeError(
                f"{name}: measured run returned {observed_rows} rows; "
                f"expected {expected_rows}"
            )

        samples_ms.append(elapsed_ms)
        query_counts.append(counter.count)

    return {
        "name": name,
        "workload": workload,
        "expected_rows": expected_rows,
        "timing_ms": {
            "median": round(statistics.median(samples_ms), 3),
            "p95": round(_p95(samples_ms), 3),
            "min": round(min(samples_ms), 3),
            "max": round(max(samples_ms), 3),
            "samples": [round(value, 3) for value in samples_ms],
        },
        "sql_queries": {
            "median": statistics.median(query_counts),
            "min": min(query_counts),
            "max": max(query_counts),
            "samples": query_counts,
        },
    }


def _seed_objects(session: Session, count: int, object_type: str = "claim") -> list[bytes]:
    repo = RegulatoryObjectRepository(session)
    uuids: list[bytes] = []
    for index in range(count):
        obj, _ = repo.create_object(
            object_type=object_type,
            payload={"index": index, "text": f"baseline-{index}"},
            owner_user_id="performance-baseline",
            created_by="performance-baseline",
        )
        uuids.append(obj.object_uuid)
    session.commit()
    session.expunge_all()
    return uuids


def _benchmark_repository_list(
    object_count: int,
    repetitions: int,
    warmups: int,
) -> dict:
    engine = _make_engine()
    session = Session(engine)
    try:
        _seed_objects(session, object_count)
        repo = RegulatoryObjectRepository(session)
        counter = QueryCounter(engine)
        try:
            return _measure(
                name=f"repository_list_{object_count}",
                operation=lambda: len(repo.list_objects(limit=object_count)),
                counter=counter,
                expected_rows=object_count,
                repetitions=repetitions,
                warmups=warmups,
                workload={"objects": object_count, "limit": object_count},
            )
        finally:
            counter.close()
    finally:
        session.close()
        engine.dispose()


def _benchmark_version_history(
    version_count: int,
    repetitions: int,
    warmups: int,
) -> dict:
    engine = _make_engine()
    session = Session(engine)
    try:
        repo = RegulatoryObjectRepository(session)
        obj, _ = repo.create_object(
            object_type="claim",
            payload={"version": 1},
            owner_user_id="performance-baseline",
            created_by="performance-baseline",
        )
        session.flush()
        object_uuid = obj.object_uuid
        for version_no in range(2, version_count + 1):
            repo.create_version(
                object_uuid=object_uuid,
                payload={"version": version_no},
                created_by="performance-baseline",
            )
        session.commit()
        session.expunge_all()

        counter = QueryCounter(engine)
        try:
            return _measure(
                name=f"version_history_{version_count}",
                operation=lambda: len(repo.list_versions(object_uuid)),
                counter=counter,
                expected_rows=version_count,
                repetitions=repetitions,
                warmups=warmups,
                workload={"versions": version_count},
            )
        finally:
            counter.close()
    finally:
        session.close()
        engine.dispose()


def _benchmark_relation_list(
    relation_count: int,
    repetitions: int,
    warmups: int,
) -> dict:
    engine = _make_engine()
    session = Session(engine)
    try:
        repo = RegulatoryObjectRepository(session)
        product, _ = repo.create_object(
            object_type="product",
            payload={"name": "baseline-product"},
            owner_user_id="performance-baseline",
            created_by="performance-baseline",
        )
        session.flush()
        product_uuid = product.object_uuid

        for index in range(relation_count):
            claim, _ = repo.create_object(
                object_type="claim",
                payload={"index": index},
                owner_user_id="performance-baseline",
                created_by="performance-baseline",
            )
            session.flush()
            repo.create_relation(
                source_uuid=product_uuid,
                source_version=1,
                target_uuid=claim.object_uuid,
                target_version=1,
                relation_type="has_claim",
                created_by="performance-baseline",
            )
        session.commit()
        session.expunge_all()

        counter = QueryCounter(engine)
        try:
            return _measure(
                name=f"relation_list_{relation_count}",
                operation=lambda: len(repo.list_relations_for_source(product_uuid)),
                counter=counter,
                expected_rows=relation_count,
                repetitions=repetitions,
                warmups=warmups,
                workload={"relations": relation_count},
            )
        finally:
            counter.close()
    finally:
        session.close()
        engine.dispose()


def _benchmark_api_list(
    object_count: int,
    repetitions: int,
    warmups: int,
) -> dict:
    engine = _make_engine()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    seed_session = SessionLocal()
    try:
        _seed_objects(seed_session, object_count)
    finally:
        seed_session.close()

    app = create_app(session_factory_override=SessionLocal)
    counter = QueryCounter(engine)
    try:
        with TestClient(app) as client:

            def operation() -> int:
                response = client.get(f"/api/v1/objects?limit={object_count}")
                if response.status_code != 200:
                    raise RuntimeError(
                        f"api_list_{object_count}: HTTP {response.status_code}: "
                        f"{response.text}"
                    )
                return len(response.json())

            return _measure(
                name=f"api_list_{object_count}",
                operation=operation,
                counter=counter,
                expected_rows=object_count,
                repetitions=repetitions,
                warmups=warmups,
                workload={"objects": object_count, "limit": object_count},
            )
    finally:
        counter.close()
        engine.dispose()


def run_baseline(repetitions: int, warmups: int) -> dict:
    scenarios = [
        _benchmark_repository_list(100, repetitions, warmups),
        _benchmark_repository_list(1000, repetitions, warmups),
        _benchmark_version_history(200, repetitions, warmups),
        _benchmark_relation_list(250, repetitions, warmups),
        _benchmark_api_list(500, repetitions, warmups),
    ]

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": os.environ.get("GITHUB_SHA"),
        "measurement_policy": {
            "timing_gate": False,
            "timing_interpretation": "compare only on equivalent runner/runtime",
            "query_count_recorded": True,
            "warmups": warmups,
            "repetitions": repetitions,
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sqlalchemy": sqlalchemy.__version__,
            "fastapi": fastapi.__version__,
            "sqlite": sqlite3.sqlite_version,
        },
        "scenarios": scenarios,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path; JSON is always also written to stdout.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=DEFAULT_WARMUPS,
    )
    args = parser.parse_args()

    if args.repetitions < 1 or args.warmups < 0:
        parser.error("--repetitions must be >=1 and --warmups must be >=0")

    result = run_baseline(args.repetitions, args.warmups)
    payload = json.dumps(result, indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
