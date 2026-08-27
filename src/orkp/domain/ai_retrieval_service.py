"""Deterministic provider-neutral hybrid retrieval for grounded AI context."""

import json
import re
from typing import Protocol
from uuid import UUID

from orkp.db.read_queries import (
    get_object_version_validation_contexts,
    list_current_object_versions,
)
from orkp.db.repository import RegulatoryObjectRepository
from orkp.domain.ai_retrieval_models import (
    HybridRetrievalCandidate,
    HybridRetrievalRequest,
    HybridRetrievalResponse,
    RetrievalHit,
)
from orkp.domain.exceptions import (
    ObjectNotFoundError,
    ObjectTypeMismatchError,
    ObjectVersionNotFoundError,
)
from orkp.domain.graph_service import GraphProjectionService
from orkp.domain.risk_models import VersionedObjectReference


class VectorRetrievalAdapter(Protocol):
    """Provider-neutral semantic-search boundary.

    Implementations must return normalized scores in (0, 1] and exact ORKP
    UUID/version references. The hybrid service revalidates every hit against the
    Object Store before it can become grounding context.
    """

    def search(self, query_text: str, limit: int) -> list[RetrievalHit]: ...


class ObjectStoreKeywordRetrievalAdapter:
    """Simple deterministic keyword search over current Object Store payloads."""

    def __init__(self, repo: RegulatoryObjectRepository, scan_limit: int = 5000):
        self.repo = repo
        self.scan_limit = scan_limit

    def search(self, query_text: str, limit: int) -> list[RetrievalHit]:
        tokens = self._tokens(query_text)
        if not tokens:
            return []
        query_normalized = " ".join(tokens)
        hits: list[RetrievalHit] = []
        for obj, version in list_current_object_versions(
            self.repo.session,
            limit=self.scan_limit,
        ):
            if obj.object_type == "ai_draft":
                continue
            searchable = self._searchable_text(version.payload_json)
            matched = sum(1 for token in tokens if token in searchable)
            if matched == 0:
                continue
            coverage = matched / len(tokens)
            phrase_bonus = 0.15 if query_normalized in searchable else 0.0
            score = min(1.0, 0.85 * coverage + phrase_bonus)
            hits.append(
                RetrievalHit(
                    reference=VersionedObjectReference(
                        object_uuid=UUID(bytes=obj.object_uuid).hex,
                        object_version=obj.current_version,
                    ),
                    object_type=obj.object_type,
                    channel="keyword",
                    score=score,
                )
            )
        hits.sort(
            key=lambda hit: (
                -hit.score,
                hit.object_type,
                hit.reference.object_uuid,
                hit.reference.object_version,
            )
        )
        return hits[:limit]

    @staticmethod
    def _tokens(value: str) -> list[str]:
        return sorted(set(re.findall(r"[\w-]+", value.lower(), flags=re.UNICODE)))

    @classmethod
    def _searchable_text(cls, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).lower()
        return " ".join(cls._tokens(canonical))


class GraphRetrievalAdapter:
    """Exact-version graph retrieval from explicit seed references."""

    def __init__(self, repo: RegulatoryObjectRepository):
        self.repo = repo

    def search(
        self,
        seed_refs: list[VersionedObjectReference],
        depth: int,
        limit: int,
    ) -> list[RetrievalHit]:
        if not seed_refs:
            return []
        best: dict[tuple[str, int], RetrievalHit] = {}
        projection = GraphProjectionService(self.repo)
        for seed in seed_refs:
            impact = projection.impact_analysis(
                seed.object_uuid,
                seed.object_version,
                depth=depth,
            )
            for item in impact.impacted:
                if item.node.object_type == "ai_draft":
                    continue
                score = 1.0 / item.distance
                key = (item.node.object_uuid, item.node.object_version)
                hit = RetrievalHit(
                    reference=VersionedObjectReference(
                        object_uuid=item.node.object_uuid,
                        object_version=item.node.object_version,
                    ),
                    object_type=item.node.object_type,
                    channel="graph",
                    score=score,
                )
                previous = best.get(key)
                if previous is None or hit.score > previous.score:
                    best[key] = hit
        hits = sorted(
            best.values(),
            key=lambda hit: (
                -hit.score,
                hit.object_type,
                hit.reference.object_uuid,
                hit.reference.object_version,
            ),
        )
        return hits[:limit]


class HybridRetrievalService:
    """Fuse keyword, vector and graph retrieval into exact grounding refs."""

    def __init__(
        self,
        repo: RegulatoryObjectRepository,
        vector_adapter: VectorRetrievalAdapter,
        keyword_adapter: ObjectStoreKeywordRetrievalAdapter | None = None,
        graph_adapter: GraphRetrievalAdapter | None = None,
    ):
        self.repo = repo
        self.vector_adapter = vector_adapter
        self.keyword_adapter = keyword_adapter or ObjectStoreKeywordRetrievalAdapter(
            repo
        )
        self.graph_adapter = graph_adapter or GraphRetrievalAdapter(repo)

    def retrieve(self, request: HybridRetrievalRequest) -> HybridRetrievalResponse:
        for seed in request.graph_seed_refs:
            seed_type = self._validate_reference(seed, "Graph retrieval seed")
            if seed_type == "ai_draft":
                raise ObjectTypeMismatchError(
                    "AI draft cannot be used as a graph retrieval seed"
                )

        keyword_hits = self.keyword_adapter.search(
            request.query_text,
            request.keyword_limit,
        )
        vector_hits = self.vector_adapter.search(
            request.query_text,
            request.vector_limit,
        )
        graph_hits = self.graph_adapter.search(
            request.graph_seed_refs,
            request.graph_depth,
            request.max_results,
        )

        prepared_hits: list[
            tuple[str, RetrievalHit, bytes | None, Exception | None]
        ] = []
        validation_keys: list[tuple[bytes, int]] = []
        for expected_channel, hits in (
            ("keyword", keyword_hits),
            ("vector", vector_hits),
            ("graph", graph_hits),
        ):
            for hit in hits:
                object_uuid: bytes | None = None
                validation_error: Exception | None = None
                if hit.channel != expected_channel:
                    validation_error = ObjectTypeMismatchError(
                        f"{expected_channel} retrieval adapter returned {hit.channel} hit"
                    )
                else:
                    try:
                        object_uuid = UUID(hit.reference.object_uuid).bytes
                    except (ValueError, AttributeError, TypeError):
                        validation_error = ObjectNotFoundError(
                            "Retrieval hit has invalid object UUID "
                            f"{hit.reference.object_uuid}"
                        )
                    else:
                        validation_keys.append(
                            (object_uuid, hit.reference.object_version)
                        )
                prepared_hits.append(
                    (expected_channel, hit, object_uuid, validation_error)
                )

        validation_contexts = get_object_version_validation_contexts(
            self.repo.session,
            validation_keys,
        )

        merged: dict[tuple[str, int], dict] = {}
        for expected_channel, hit, object_uuid, validation_error in prepared_hits:
            if validation_error is not None:
                raise validation_error
            assert object_uuid is not None
            context = validation_contexts.get(object_uuid)
            if context is None:
                raise ObjectNotFoundError(
                    f"Retrieval hit object {hit.reference.object_uuid} not found"
                )
            obj, versions = context
            if hit.reference.object_version not in versions:
                raise ObjectVersionNotFoundError(
                    "Retrieval hit "
                    f"{hit.reference.object_uuid} v{hit.reference.object_version} not found"
                )
            validated_type = obj.object_type
            if validated_type != hit.object_type:
                raise ObjectTypeMismatchError(
                    f"Retrieval hit type {hit.object_type} does not match Object Store type {validated_type}"
                )
            if validated_type == "ai_draft":
                continue

            key = (hit.reference.object_uuid, hit.reference.object_version)
            entry = merged.setdefault(
                key,
                {
                    "reference": hit.reference,
                    "object_type": validated_type,
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "graph_score": 0.0,
                },
            )
            score_field = f"{expected_channel}_score"
            entry[score_field] = max(entry[score_field], hit.score)

        weights = request.weights
        total_weight = weights.keyword + weights.vector + weights.graph
        results: list[HybridRetrievalCandidate] = []
        for entry in merged.values():
            fused = (
                entry["keyword_score"] * weights.keyword
                + entry["vector_score"] * weights.vector
                + entry["graph_score"] * weights.graph
            ) / total_weight
            if fused <= 0:
                continue
            channels = [
                channel
                for channel in ("keyword", "vector", "graph")
                if entry[f"{channel}_score"] > 0
            ]
            results.append(
                HybridRetrievalCandidate(
                    **entry,
                    fused_score=round(fused, 12),
                    channels=channels,
                )
            )

        results.sort(
            key=lambda item: (
                -item.fused_score,
                item.object_type,
                item.reference.object_uuid,
                item.reference.object_version,
            )
        )
        return HybridRetrievalResponse(
            query_text=request.query_text,
            results=results[: request.max_results],
        )

    def _validate_reference(
        self,
        reference: VersionedObjectReference,
        label: str,
    ) -> str:
        try:
            object_uuid = UUID(reference.object_uuid).bytes
        except (ValueError, AttributeError, TypeError) as exc:
            raise ObjectNotFoundError(
                f"{label} has invalid object UUID {reference.object_uuid}"
            ) from exc
        obj = self.repo.get_by_uuid(object_uuid)
        if obj is None:
            raise ObjectNotFoundError(
                f"{label} object {reference.object_uuid} not found"
            )
        version = self.repo.get_version(object_uuid, reference.object_version)
        if version is None:
            raise ObjectVersionNotFoundError(
                f"{label} {reference.object_uuid} v{reference.object_version} not found"
            )
        return obj.object_type
