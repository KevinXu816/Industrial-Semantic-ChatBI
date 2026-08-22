from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    preview_only: bool = False


class ChatMessage(BaseModel):
    role: str
    content: str


class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: Literal["up", "down"]
    comment: Optional[str] = None


class SemanticSubject(BaseModel):
    entity: str = "Machine"
    reference: Optional[str] = None
    key: Optional[str] = None


class SemanticFilter(BaseModel):
    entity: Optional[str] = None
    property: str
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in", "contains"] = "="
    value: Any


class SemanticTimeRange(BaseModel):
    type: Literal["relative", "absolute"] = "relative"
    value: int = 7
    unit: Literal["hour", "day", "week", "month"] = "day"
    start: Optional[str] = None
    end: Optional[str] = None

    def normalized_days(self) -> int:
        if self.type == "absolute":
            return max(1, min(int(self.value or 7), 365))
        multipliers = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30}
        days = max(1, round(float(self.value) * multipliers[self.unit]))
        return min(days, 365)


class ComparisonSpec(BaseModel):
    type: Literal["none", "previous_period", "baseline"] = "none"


class SemanticIntent(BaseModel):
    raw_question: str

    # V0.5 generic semantic contract
    subject: Optional[SemanticSubject] = None
    metrics: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    filters: List[SemanticFilter] = Field(default_factory=list)
    time_range: Optional[SemanticTimeRange] = None
    time_grain: Optional[Literal["hour", "day", "week", "month"]] = None
    comparison: ComparisonSpec = Field(default_factory=ComparisonSpec)
    analysis_mode: str = "diagnostic"
    related_entities: List[str] = Field(default_factory=list)

    # Backward-compatible V0.4 fields. They are synchronized automatically.
    machine_ref: Optional[str] = None
    metric: Optional[str] = None
    time_window_days: int = 7

    @model_validator(mode="after")
    def synchronize_legacy_fields(self):
        if self.subject is None:
            self.subject = SemanticSubject(entity="Machine", reference=self.machine_ref)
        elif self.machine_ref is None and self.subject.entity == "Machine":
            self.machine_ref = self.subject.reference

        if not self.metrics and self.metric:
            self.metrics = [self.metric]
        elif self.metrics and not self.metric:
            self.metric = self.metrics[0]

        if self.time_range is None:
            self.time_range = SemanticTimeRange(value=max(1, self.time_window_days), unit="day")
        else:
            self.time_window_days = self.time_range.normalized_days()
        return self


class QueryPlan(BaseModel):
    intent: SemanticIntent
    sql: List[str]
    notes: List[str] = Field(default_factory=list)
    metric_dependencies: List[str] = Field(default_factory=list)
    required_entities: List[str] = Field(default_factory=list)
    join_paths: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    subject_entity: Optional[str] = None
    logical_plan: Dict[str, Any] = Field(default_factory=dict)


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
