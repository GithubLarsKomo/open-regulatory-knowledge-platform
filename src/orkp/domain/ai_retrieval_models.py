"""Provider-neutral models for deterministic hybrid AI retrieval."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from orkp.domain.risk_models import VersionedObjectReference


RetrievalChannel = Literal["keyword", "vector", "graph"]


class HybridRetrievalWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keyword: float = Field(0.35, ge=0.0, le=1.0)
    vector: float = Field(0.45, ge=0.0, le=1.0)
    graph: float = Field(0.20, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_positive_total(self):
        if self.keyword + self.vector + self.graph <= 0:
            raise ValueError("hybrid retrieval weights must have a positive total")
        return self


class HybridRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(..., min_length=1)
    graph_seed_refs: list[VersionedObjectReference] = Field(default_factory=list)
    keyword_limit: int = Field(20, ge=1, le=200)
    vector_limit: int = Field(20, ge=1, le=200)
    graph_depth: int = Field(2, ge=1, le=10)
    max_results: int = Field(20, ge=1, le=200)
    weights: HybridRetrievalWeights = Field(default_factory=HybridRetrievalWeights)

    @field_validator("query_text")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query_text must not be blank")
        return value

    @model_validator(mode="after")
    def reject_duplicate_graph_seeds(self):
        keys = [(ref.object_uuid, ref.object_version) for ref in self.graph_seed_refs]
        if len(keys) != len(set(keys)):
            raise ValueError("graph_seed_refs must not contain duplicate exact references")
        return self


class RetrievalHit(BaseModel):
    """One normalized exact-version hit returned by a retrieval channel."""

    model_config = ConfigDict(extra="forbid")

    reference: VersionedObjectReference
    object_type: str = Field(..., min_length=1)
    channel: RetrievalChannel
    score: float = Field(..., gt=0.0, le=1.0)


class HybridRetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: VersionedObjectReference
    object_type: str
    keyword_score: float = Field(0.0, ge=0.0, le=1.0)
    vector_score: float = Field(0.0, ge=0.0, le=1.0)
    graph_score: float = Field(0.0, ge=0.0, le=1.0)
    fused_score: float = Field(..., gt=0.0, le=1.0)
    channels: list[RetrievalChannel] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_channels(self):
        expected: list[RetrievalChannel] = []
        if self.keyword_score > 0:
            expected.append("keyword")
        if self.vector_score > 0:
            expected.append("vector")
        if self.graph_score > 0:
            expected.append("graph")
        if self.channels != expected:
            raise ValueError("channels must match non-zero channel scores in canonical order")
        return self


class HybridRetrievalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_text: str
    fusion_policy: Literal["weighted_exact_version"] = "weighted_exact_version"
    results: list[HybridRetrievalCandidate]
