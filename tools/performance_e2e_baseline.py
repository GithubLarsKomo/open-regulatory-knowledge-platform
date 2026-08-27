"""End-to-end ORKP performance baseline for high-level workflows.

Measures representative baseline creation, PER rendering, graph traversal and
hybrid AI retrieval. Timing is observational; SQL statement counts are the
primary deterministic signal for database roundtrip hot spots.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from time import perf_counter_ns

from sqlalchemy.orm import Session

from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_models import HybridRetrievalRequest
from orkp.domain.ai_retrieval_service import HybridRetrievalService
from orkp.domain.graph_service import GraphProjectionService
from orkp.domain.per_content_models import PERReportBaselineCreateRequest
from orkp.domain.per_render_service import PERRenderService
from orkp.domain.per_report_baseline_service import PERReportBaselineService
from orkp.domain.performance_models import PerformanceStudyCreateRequest
from orkp.domain.performance_report_models import PerformanceReportBaselineCreateRequest
from orkp.domain.performance_report_service import PerformanceReportService
from orkp.domain.performance_result_models import PerformanceResultCreateRequest
from orkp.domain.performance_result_service import PerformanceResultService
from orkp.domain.performance_service import PerformanceStudyService
from performance_baseline import QueryCounter, _make_engine, _p95

DEFAULT_REPETITIONS = 5
DEFAULT_WARMUPS = 1


class _EmptyVectorAdapter:
    def search(self, query_text: str, limit: int):
        return []


def _summary(name, samples_ms, queries, workload, result_size):
    return {
        "name": name,
        "workload": workload,
        "result_size": result_size,
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


def _measure(name, operation, counter, repetitions, warmups, workload):
    for _ in range(warmups):
        operation()
    samples_ms = []
    queries = []
    result_size = None
    for _ in range(repetitions):
        counter.reset()
        started = perf_counter_ns()
        result_size = operation()
        samples_ms.append((perf_counter_ns() - started) / 1_000_000)
        queries.append(counter.count)
    return _summary(name, samples_ms, queries, workload, result_size)


def _baseline_create(repetitions, warmups, item_count=100):
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    refs = []
    for index in range(item_count):
        obj, _ = repo.create_object(
            "claim",
            {"index": index, "wording": f"baseline claim {index}"},
            "perf",
            "perf",
        )
        refs.append((obj.object_uuid, 1))
    session.commit()
    counter = QueryCounter(engine)
    sequence = 0

    def operation():
        nonlocal sequence
        sequence += 1
        baseline = repo.create_baseline(
            f"e2e-baseline-{sequence}",
            None,
            refs,
            "perf",
        )
        session.commit()
        return len(repo.list_baseline_items(baseline.baseline_uuid))

    try:
        return _measure(
            "baseline_create_100",
            operation,
            counter,
            repetitions,
            warmups,
            {"items": item_count},
        )
    finally:
        counter.close()
        session.close()
        engine.dispose()


def _approve(repo, obj):
    repo.transition_state(obj.object_uuid, "in_review", "author")
    repo.transition_state(obj.object_uuid, "approved", "approver")
    repo.session.commit()


def _prepare_per(repo):
    product, _ = repo.create_object(
        "product", {"product_id": "P-E2E", "name": "E2E Product"}, "owner", "owner"
    )
    _approve(repo, product)
    claim, _ = repo.create_object(
        "claim",
        {
            "claim_type": "clinical",
            "claim_category": "clinical",
            "confidence": "high",
            "severity": "medium",
            "jurisdiction": "EU",
            "language": "en",
            "wording": "Clinical performance claim",
            "regulatory_scope": [],
        },
        "owner",
        "owner",
    )
    _approve(repo, claim)
    repo.create_relation(product.object_uuid, 1, claim.object_uuid, 1, "has_claim", "owner")
    repo.session.commit()
    study = PerformanceStudyService(repo).create_study(
        product.uuid_hex,
        PerformanceStudyCreateRequest(
            study_id="ST-E2E",
            study_type="clinical",
            title="Clinical E2E study",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            study_status="completed",
            owner_user_id="study-owner",
        ),
    )
    result = PerformanceResultService(repo).create_result(
        study.object_uuid,
        PerformanceResultCreateRequest(
            result_id="R-E2E",
            study={"object_uuid": study.object_uuid, "object_version": 1},
            claims=[{"object_uuid": claim.uuid_hex, "object_version": 1}],
            parameter="clinical sensitivity",
            result_value="99.3",
            interpretation="Approved clinical interpretation.",
            quality_rating="high",
            owner_user_id="result-owner",
        ),
    )
    _approve(repo, repo.get_by_uuid_hex(result.object_uuid))
    source = PerformanceReportService(repo).create_baseline(
        PerformanceReportBaselineCreateRequest(
            name="E2E source baseline",
            product={"object_uuid": product.uuid_hex, "object_version": 1},
            evidence=[{"object_uuid": result.object_uuid, "object_version": 1}],
            created_by_user_id="per-author",
        )
    )
    report = PERReportBaselineService(repo).create_baseline(
        PERReportBaselineCreateRequest(
            name="E2E report baseline",
            performance_baseline_uuid=source.baseline_uuid,
            ai_draft_blocks=[
                {
                    "block_id": "e2e-summary",
                    "section_type": "clinical_performance",
                    "text": "AI clinical summary.",
                    "model_id": "e2e-model",
                    "source_refs": [
                        {"object_uuid": result.object_uuid, "object_version": 1}
                    ],
                }
            ],
            created_by_user_id="report-author",
        )
    )
    return report.baseline_uuid


def _per_render(repetitions, warmups):
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    baseline_uuid = _prepare_per(repo)
    counter = QueryCounter(engine)

    def operation():
        rendered = PERRenderService(repo).render(baseline_uuid, "docx", "perf")
        return len(rendered.content)

    try:
        return _measure(
            "per_render_docx",
            operation,
            counter,
            repetitions,
            warmups,
            {"format": "docx"},
        )
    finally:
        counter.close()
        session.close()
        engine.dispose()


def _graph_traceability(repetitions, warmups, node_count=51):
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    root, _ = repo.create_object("evidence", {"title": "root"}, "perf", "perf")
    for index in range(node_count - 1):
        child, _ = repo.create_object(
            "evidence", {"title": f"child {index}"}, "perf", "perf"
        )
        repo.create_relation(root.object_uuid, 1, child.object_uuid, 1, "supersedes", "perf")
    session.commit()
    root_hex = root.uuid_hex
    counter = QueryCounter(engine)

    def operation():
        graph = GraphProjectionService(repo).traceability(root_hex, 1, depth=1)
        return len(graph.nodes)

    try:
        return _measure(
            "graph_traceability_depth1_51",
            operation,
            counter,
            repetitions,
            warmups,
            {"nodes": node_count, "depth": 1},
        )
    finally:
        counter.close()
        session.close()
        engine.dispose()


def _hybrid_keyword(repetitions, warmups, object_count=1000):
    engine = _make_engine()
    session = Session(engine)
    repo = RegulatoryObjectRepository(session)
    for index in range(object_count):
        text = f"performance evidence marker {index}" if index % 10 == 0 else f"other {index}"
        repo.create_object("claim", {"wording": text}, "perf", "perf")
    session.commit()
    session.expunge_all()
    service = HybridRetrievalService(repo, _EmptyVectorAdapter())
    request = HybridRetrievalRequest(
        query_text="performance evidence",
        keyword_limit=20,
        vector_limit=20,
        max_results=20,
    )
    counter = QueryCounter(engine)

    def operation():
        return len(service.retrieve(request).results)

    try:
        return _measure(
            "hybrid_keyword_1000",
            operation,
            counter,
            repetitions,
            warmups,
            {"objects": object_count, "keyword_limit": 20},
        )
    finally:
        counter.close()
        session.close()
        engine.dispose()


def run(repetitions, warmups):
    return {
        "schema_version": 1,
        "measurement_policy": {
            "timing_gate": False,
            "query_count_recorded": True,
            "repetitions": repetitions,
            "warmups": warmups,
        },
        "scenarios": [
            _baseline_create(repetitions, warmups),
            _per_render(repetitions, warmups),
            _graph_traceability(repetitions, warmups),
            _hybrid_keyword(repetitions, warmups),
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    args = parser.parse_args()
    payload = json.dumps(run(args.repetitions, args.warmups), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
