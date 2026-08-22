from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    preview_only: bool = False


class ChatMessage(BaseModel):
    role: str  # user / assistant
    content: str


class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: Literal["up", "down"]
    comment: Optional[str] = None


class SemanticIntent(BaseModel):
    raw_question: str
    machine_ref: Optional[str] = None
    metric: Optional[str] = None
    time_window_days: int = 7
    analysis_mode: str = "diagnostic"
    related_entities: List[str] = Field(default_factory=list)


class QueryPlan(BaseModel):
    intent: SemanticIntent
    sql: List[str]
    notes: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    intent: SemanticIntent
    plan: QueryPlan
    data: Dict[str, Any]
    answer: str


class MetadataColumn(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    comment: Optional[str] = None


class MetadataTable(BaseModel):
    name: str
    columns: List[MetadataColumn] = Field(default_factory=list)
    scan_warning: Optional[str] = None


class MetadataDatabase(BaseModel):
    name: str
    tables: List[MetadataTable] = Field(default_factory=list)
    scan_warning: Optional[str] = None


class MetadataCatalog(BaseModel):
    name: str
    type: str = "unknown"
    databases: List[MetadataDatabase] = Field(default_factory=list)
    scan_warning: Optional[str] = None


class MetadataSnapshot(BaseModel):
    source: str
    catalogs: List[MetadataCatalog] = Field(default_factory=list)


class CandidateProperty(BaseModel):
    logical_name: str
    physical_column: str
    data_type: str


class CandidateRelationship(BaseModel):
    from_entity: str
    relation: str
    to_entity: str
    on: str
    confidence: float


class CandidateMetric(BaseModel):
    name: str
    expression: str
    unit: Optional[str] = None
    confidence: float


class SemanticCandidate(BaseModel):
    id: str
    entity: str
    description: str
    confidence: float
    physical_mapping: Dict[str, str]
    properties: List[CandidateProperty] = Field(default_factory=list)
    relationships: List[CandidateRelationship] = Field(default_factory=list)
    metrics: List[CandidateMetric] = Field(default_factory=list)
    status: Literal["pending", "approved", "rejected"] = "pending"
    evidence: List[str] = Field(default_factory=list)
    review_note: Optional[str] = None


class MetadataScanRequest(BaseModel):
    catalogs: Optional[List[str]] = None
    save_candidates: bool = True


class MetadataScanResponse(BaseModel):
    snapshot: MetadataSnapshot
    candidates: List[SemanticCandidate]


class ReviewDecision(BaseModel):
    status: Literal["approved", "rejected"]
    note: Optional[str] = None


class MetricDefinition(BaseModel):
    name: str
    description: str = ""
    entity: Optional[str] = None
    expression: str
    unit: Optional[str] = None
    time_field: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    synonyms: List[str] = Field(default_factory=list)
