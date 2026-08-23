from typing import Dict, List
from pathlib import Path
import threading
from contextlib import asynccontextmanager
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import ValidationError
from .models import ChatRequest, ChatResponse, QueryPlan, MetadataScanRequest, MetadataScanResponse, ReviewDecision, MetricDefinition, SemanticCandidate, FeedbackRequest, SemanticIntent
from .semantic import SemanticRegistry
from .planner import QueryPlanner
from .rca import RCAEngine
from .guardrail import SQLGuardrail
from .executor import get_executor
from .answer import AnswerComposer
from .metadata import get_metadata_scanner
from .candidate_generator import generate_candidates
from .review_store import ReviewStore
from .datasource import DataSourceStore, DataSourceConfig
from .llm_service import LLMService, LLMConfig
from .chat_session import ChatSessionStore, FeedbackStore
from .observability import QueryStats
from .config_manager import export_config, import_config
from .field_aliases import FieldAliasStore
from .template_apply import TemplateApplier, TemplateApplyError
from .template_models import TemplateUploadRequest
from .template_store import (
    TemplateConflictError,
    TemplateNotFoundError,
    TemplateOperationError,
    TemplateStore,
    TemplateStoreError,
    TemplateValidationError,
)
from .join_path import JoinPathFinder
from .cache_audit import QueryCache, AuditLog
from .governance import PolicyEngine, PolicyStore, GovernanceError
from .lineage import SemanticVersionStore, QueryLineageStore
from .evidence_graph import EvidenceGraphBuilder
from .timeseries_analytics import TimeSeriesAnalyticsEngine
from .knowledge import KnowledgeRetriever, HybridKnowledgeRetriever
from .knowledge_store import KnowledgeStore
from .knowledge_backends import get_knowledge_backend
from .knowledge_ingestion import KnowledgeIngestionPipeline
from .historical_rca import HistoricalRCARetriever
from .doris_explain import DorisExplainCostAdapter
from .temporal_causality import TemporalCausalityEngine
from .sensor_correlation import SensorCorrelationEngine
from .operating_baseline import OperatingBaselineEngine
from .rca_feedback import RCAFeedbackStore
from .persistence import get_repository
from .rca_cases import RCACaseStore
from .runtime_stats import RuntimeQueryStore
from .knowledge_workflow import KnowledgeWorkflow
from .retrieval_quality import RetrievalEvaluator, RCARankingCalibrator
from .rca_similarity import RCASimilaritySearch
from .industrial_knowledge_graph import IndustrialKnowledgeGraph
from .causal_model import CausalGraphReasoner
from .graph_ingestion import GraphIngestionService
from .graph_bootstrap import bootstrap_graph
from .fmea import FMEAStore
from .failure_model import FailureModelIngestion
from .reliability_intelligence import FailureSensorMappingStore, ReliabilityIntelligenceService
from .condition_analytics import ConditionIndicatorDefinitionStore, ConditionBaselineStore, ConditionAnalyticsService, TimeSeriesFeatureEngine
from .predictive_maintenance import TrendRULAdapter, MaintenanceDecisionService, CMMSWorkOrderCandidateStore
from .condition_models import ConditionModelTemplateStore
from .feature_pipeline import FeaturePipelineStore
from .model_registry import PredictiveModelRegistry
from .model_monitoring import ModelDatasetRegistry, ModelEvaluationService, ModelDeploymentManager, ModelMonitoringService
from .asset_reliability import AssetRegistry, AssetReliabilityCockpitService
from .product_workspace import ProductWorkspaceService
from .reliability_workflow import RCAWorkflowService
from .data_binding import DataBindingStore
from .integration_runtime import IntegrationRuntimeService
from .connector_sdk import ConnectorRegistry, ConnectorBatchProcessor
from .edge_agent import EdgeAgentRegistry
from .enterprise_identity import EnterpriseIdentityStore, EnterpriseScopeEngine, AccessDenied, IdentityError, default_tenant_id
from .authentication import AuthenticationService, AuthenticationError
from .secrets import SecretRegistry, SecretManager, reject_inline_secrets
from .audit_center import AuditCenter
from .sre_observability import TelemetryStore, DependencyHealthService, parse_traceparent, traceparent, new_trace_id, new_span_id
from .version import APP_VERSION, APP_NAME
from .production_runtime import ProductionLifecycle, BackupManager, UpgradeAdvisor
from .pilot_pack import PilotPackService
from .pilot_delivery import PilotDeliveryService
from .pilot_validation import PilotCustomerDataValidator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # production_lifecycle is initialized below during module construction.
    production_lifecycle.startup()
    try:
        yield
    finally:
        production_lifecycle.shutdown()

app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")
registry = SemanticRegistry()
planner = QueryPlanner(registry)
rca_engine = RCAEngine()
guardrail = SQLGuardrail(registry)
policy_store = PolicyStore()
policy_engine = PolicyEngine(registry, policy_store)
semantic_versions = SemanticVersionStore()
query_lineage = QueryLineageStore()
evidence_graph_builder = EvidenceGraphBuilder()
timeseries_engine = TimeSeriesAnalyticsEngine()
knowledge_retriever = KnowledgeRetriever()
doris_cost_adapter = DorisExplainCostAdapter()
temporal_engine = TemporalCausalityEngine()
sensor_correlation_engine = SensorCorrelationEngine()
operating_baseline_engine = OperatingBaselineEngine()
rca_feedback_store = RCAFeedbackStore()
rca_calibrator = RCARankingCalibrator(rca_feedback_store)
repository = get_repository()
audit_center = AuditCenter(repository)
telemetry = TelemetryStore(repository)
dependency_health = DependencyHealthService(telemetry)
secret_registry = SecretRegistry(repository)
secret_manager = SecretManager(secret_registry)
rca_case_store = RCACaseStore(repository)
runtime_query_store = RuntimeQueryStore(repository)
knowledge_store = KnowledgeStore(repository)
knowledge_backend = get_knowledge_backend(knowledge_store)
knowledge_ingestion = KnowledgeIngestionPipeline(knowledge_store, knowledge_backend)
historical_rca_retriever = HistoricalRCARetriever(repository)
knowledge_retriever = HybridKnowledgeRetriever(knowledge_backend, historical_rca_retriever)
knowledge_workflow = KnowledgeWorkflow(knowledge_store, repository, knowledge_ingestion)
retrieval_evaluator = RetrievalEvaluator(knowledge_retriever)
rca_similarity = RCASimilaritySearch(repository)
industrial_graph = IndustrialKnowledgeGraph(repository)
bootstrap_graph(industrial_graph)
causal_reasoner = CausalGraphReasoner(industrial_graph)
graph_ingestion = GraphIngestionService(industrial_graph)
fmea_store = FMEAStore(repository)
failure_model_ingestion = FailureModelIngestion(industrial_graph)
failure_sensor_mappings = FailureSensorMappingStore(repository)
reliability_service = ReliabilityIntelligenceService(repository, fmea_store, failure_sensor_mappings)
condition_definitions = ConditionIndicatorDefinitionStore(repository)
condition_baselines = ConditionBaselineStore(repository)
condition_service = ConditionAnalyticsService(condition_definitions, condition_baselines)
rul_adapter = TrendRULAdapter()
maintenance_decision = MaintenanceDecisionService()
cmms_candidates = CMMSWorkOrderCandidateStore(repository)
condition_models = ConditionModelTemplateStore(repository)
condition_models.bootstrap()
feature_pipelines = FeaturePipelineStore(repository)
model_registry = PredictiveModelRegistry(repository)
model_datasets = ModelDatasetRegistry(repository)
model_evaluator = ModelEvaluationService(repository, model_registry, model_datasets)
model_deployments = ModelDeploymentManager(repository, model_registry)
model_monitoring = ModelMonitoringService(repository)
asset_registry = AssetRegistry(repository)
pilot_pack = PilotPackService(repository, asset_registry, fmea_store, failure_sensor_mappings, reliability_service, rca_case_store)
asset_cockpit = AssetReliabilityCockpitService(asset_registry, reliability_service, fmea_store, rca_case_store, cmms_candidates, model_deployments, model_registry, rul_adapter)
product_workspace = ProductWorkspaceService(asset_cockpit, rca_case_store, cmms_candidates)
rca_workflow = RCAWorkflowService(rca_case_store, cmms_candidates, asset_registry)
data_bindings = DataBindingStore(repository)
integration_runtime = IntegrationRuntimeService(repository, data_bindings)
pilot_delivery = PilotDeliveryService(repository, data_bindings, integration_runtime, rca_case_store)
pilot_customer_validator = PilotCustomerDataValidator(repository, data_bindings, integration_runtime)
edge_agents = EdgeAgentRegistry(repository)
connectors = ConnectorRegistry(repository, data_bindings)
connector_batches = ConnectorBatchProcessor(connectors, integration_runtime, edge_agents)
enterprise_identity = EnterpriseIdentityStore(repository)
enterprise_scope = EnterpriseScopeEngine(enterprise_identity)
auth_service = AuthenticationService(enterprise_identity)

def _production_dependency_probe():
    def doris_probe():
        import os, time
        if os.getenv("EXECUTION_MODE", "mock").lower() != "doris":
            return {"status":"disabled","mode":"mock"}
        executor=get_executor(); started=time.perf_counter(); conn=executor.pymysql.connect(**executor.cfg)
        try:
            with conn.cursor() as cur: cur.execute("SELECT 1"); cur.fetchone()
            return {"status":"ok","mode":"doris","latency_ms":round((time.perf_counter()-started)*1000,2)}
        finally: conn.close()
    probes={
        "persistence": repository.health, "knowledge": knowledge_retriever.health, "doris": doris_probe,
        "authentication": auth_service.health, "secrets": secret_manager.health,
        "edge_agents": lambda: {"status":"ok", **edge_agents.health()},
        "connectors": lambda: {"status":"ok", **connectors.summary()},
        "integration_runtime": lambda: {"status":"ok", **integration_runtime.monitoring()},
    }
    return dependency_health.check(probes)

production_lifecycle = ProductionLifecycle(repository, _production_dependency_probe, secret_manager, auth_service)
backup_manager = BackupManager(repository)
upgrade_advisor = UpgradeAdvisor(production_lifecycle.migrations, production_lifecycle.validator)
# Normalize existing V2.x audit/history stores into the unified V2.8 view.
# Import is idempotent and legacy stores remain intact for backward compatibility.
try:
    audit_center.import_legacy(limit_each=1000)
except Exception:
    pass
# Bootstrap the bundled governed knowledge only when the persistent store is empty.
_seed_knowledge = Path(__file__).resolve().parents[1] / "data" / "knowledge_base.json"
if knowledge_store.stats()["documents"] == 0 and _seed_knowledge.exists():
    knowledge_ingestion.ingest_json_file(_seed_knowledge, actor="bootstrap")
# Derive graph relations only from governed, approved knowledge.
for _doc in knowledge_store.list_documents(limit=1000, status="approved"):
    try:
        graph_ingestion.ingest_knowledge(_doc)
    except Exception:
        # Knowledge retrieval must remain available even if one document lacks graph metadata.
        pass
# Derive the reliability/failure graph from approved FMEA records as well.
for _fmea in fmea_store.list(limit=1000, status="approved"):
    try:
        failure_model_ingestion.ingest_fmea(_fmea)
    except Exception:
        pass
# RCA consumes the same governed retrieval service exposed through the API.
rca_engine = RCAEngine(knowledge=knowledge_retriever, calibrator=rca_calibrator, graph_reasoner=causal_reasoner)
answer_composer = AnswerComposer()
review_store = ReviewStore()
datasource_store = DataSourceStore(secret_manager)
llm_service = LLMService(secret_manager)
session_store = ChatSessionStore()
feedback_store = FeedbackStore()
query_stats = QueryStats()
alias_store = FieldAliasStore()
semantic_write_lock = threading.RLock()
template_store = TemplateStore()
template_applier = TemplateApplier(
    registry,
    alias_store,
    write_lock=semantic_write_lock,
)
query_cache = QueryCache(ttl_seconds=300)
audit_log = AuditLog()
semantic_versions.snapshot(registry, "startup", actor="system")


def _compile_governed_plan(intent: SemanticIntent, roles=None, attributes=None, user: str = "anonymous"):
    governed_intent, pre = policy_engine.apply_intent(intent, roles=roles, attributes=attributes)
    plan = planner.build(governed_intent)
    decision = policy_engine.evaluate_plan(
        governed_intent, plan.required_entities, plan.physical_plan,
        roles=pre["roles"], applied_row_filters=pre["applied_row_filters"],
    )
    ast = guardrail.validate_plan(plan)
    decision["sql_validation"] = ast
    plan.governance = decision
    plan.lineage = query_lineage.record(plan, governance=decision, user=user)
    return plan

def _snapshot_semantic(action: str, actor: str = "system", detail: str = ""):
    return semantic_versions.snapshot(registry, action, actor=actor, detail=detail)



# --- V2.6 Authentication / SSO middleware ---
_AUTH_PUBLIC_PREFIXES = ("/static/",)
_AUTH_PUBLIC_PATHS = {"/", "/health", "/health/live", "/health/ready", "/health/startup", "/auth/config", "/auth/dev/token", "/docs", "/redoc", "/openapi.json"}

@app.middleware("http")
async def enterprise_authentication_middleware(request: Request, call_next):
    import time, uuid
    path = request.url.path
    correlation_id = request.headers.get("x-correlation-id") or "COR-" + uuid.uuid4().hex[:20].upper()
    incoming_trace = parse_traceparent(request.headers.get("traceparent", ""))
    trace_id = incoming_trace.get("trace_id") or new_trace_id()
    parent_span_id = incoming_trace.get("parent_span_id") or ""
    span_id = new_span_id()
    request.state.correlation_id = correlation_id
    request.state.trace_id = trace_id
    request.state.span_id = span_id
    started = time.perf_counter()
    started_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    if auth_service.config.mode == "disabled" or path in _AUTH_PUBLIC_PATHS or any(path.startswith(x) for x in _AUTH_PUBLIC_PREFIXES):
        request.state.auth = {"authenticated": False, "mode": auth_service.config.mode, "principal": None, "claims": {}}
        response = await call_next(request)
    else:
        try:
            auth = auth_service.authenticate(request.headers.get("authorization", ""))
            request.state.auth = auth
            response = await call_next(request)
        except AuthenticationError as exc:
            auth_service._audit("", False, str(exc), {})
            audit_center.emit(category="authentication", action="authenticate", actor="anonymous", decision="deny", status="failure",
                              correlation_id=correlation_id, resource_type="api", resource_id=path, detail={"reason":str(exc)}, source="auth_middleware")
            response = JSONResponse(status_code=401, content={"detail": str(exc)})
    duration_ms = round((time.perf_counter()-started)*1000,2)
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Trace-ID"] = trace_id
    response.headers["traceparent"] = traceparent(trace_id, span_id)
    status_code = int(getattr(response, "status_code", 200))
    auth = getattr(request.state, "auth", None) or {}
    principal = auth.get("principal") or {}
    telemetry.record_span({
        "trace_id": trace_id, "span_id": span_id, "parent_span_id": parent_span_id, "correlation_id": correlation_id,
        "name": f"{request.method} {path}", "service": "industrial-semantic-api", "kind": "server",
        "status": "error" if status_code >= 500 else "ok", "started_at": started_at,
        "ended_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "duration_ms": duration_ms,
        "attributes": {"http.method": request.method, "http.route": path, "http.target": str(request.url.path),
                       "http.status_code": status_code, "actor": str(principal.get("principal_id") or "anonymous"),
                       "tenant_id": str(principal.get("tenant_id") or default_tenant_id())}
    })
    if not any(path.startswith(x) for x in _AUTH_PUBLIC_PREFIXES) and path not in {"/health"}:
        audit_center.emit(category="api", action=request.method, actor=str(principal.get("principal_id") or "anonymous"),
                          tenant_id=str(principal.get("tenant_id") or default_tenant_id()), org_id=str(principal.get("org_id") or ""),
                          resource_type="http_endpoint", resource_id=path, decision="deny" if status_code in {401,403} else "allow",
                          status="failure" if status_code >= 400 else "success", correlation_id=correlation_id,
                          detail={"status_code":status_code,"duration_ms":duration_ms,"trace_id":trace_id,"span_id":span_id}, source="http_middleware")
    return response

@app.get("/health/live")
def health_live():
    return production_lifecycle.live()

@app.get("/health/startup")
def health_startup():
    result=production_lifecycle.startup_probe()
    if result.get("status") != "ok": return JSONResponse(status_code=503, content=result)
    return result

@app.get("/health/ready")
def health_ready():
    result=production_lifecycle.ready()
    if result.get("status") != "ok": return JSONResponse(status_code=503, content=result)
    return result

@app.get("/")
def root():
    return FileResponse(_static / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION, "persistence": repository.health(), "knowledge": knowledge_retriever.health(), "knowledge_graph": {"nodes": len(industrial_graph.nodes()), "edges": len(industrial_graph.edges())}, "assets": asset_registry.stats(), "authentication": auth_service.health(), "secrets": secret_manager.health(), "observability": {"status": "ok", "trace_context": "w3c", "slo": telemetry.evaluate_slos()}, "production": {"configuration": production_lifecycle.validator.validate(), "migrations": production_lifecycle.migrations.status()}}


# --- LLM configuration ---

@app.get("/llm/config")
def get_llm_config():
    cfg = llm_service.get_config()
    return {**cfg.model_dump(), "api_key": "***" if cfg.api_key else "", "api_key_ref": cfg.api_key_ref}


@app.put("/llm/config")
def save_llm_config(cfg: LLMConfig):
    if cfg.api_key and not cfg.api_key.startswith("secret://"):
        raise HTTPException(status_code=400, detail="inline LLM api_key is not allowed in V2.7; use api_key_ref=secret://...")
    if cfg.api_key.startswith("secret://") and not cfg.api_key_ref:
        cfg.api_key_ref, cfg.api_key = cfg.api_key, ""
    saved=llm_service.save_config(cfg).model_dump(); saved["api_key"]="***" if saved.get("api_key") else ""; return saved


@app.post("/llm/test")
def test_llm():
    return llm_service.test_connection()


# --- Datasource management ---

@app.get("/datasources")
def list_datasources():
    out=[]
    for row in datasource_store.list():
        x=dict(row); x["password"]="***" if x.get("password") else ""; out.append(x)
    return out


@app.post("/datasources")
def create_datasource(cfg: DataSourceConfig):
    if cfg.password and not cfg.password.startswith("secret://"):
        raise HTTPException(status_code=400, detail="inline datasource password is not allowed in V2.7; use credential_ref=secret://...")
    if cfg.password.startswith("secret://") and not cfg.credential_ref:
        cfg.credential_ref, cfg.password = cfg.password, ""
    return datasource_store.save(cfg)


@app.put("/datasources/{ds_id}")
def update_datasource(ds_id: str, cfg: DataSourceConfig):
    cfg.id = ds_id
    if cfg.password and cfg.password != "***" and not cfg.password.startswith("secret://"):
        raise HTTPException(status_code=400, detail="inline datasource password is not allowed in V2.7; use credential_ref=secret://...")
    if cfg.password.startswith("secret://") and not cfg.credential_ref:
        cfg.credential_ref, cfg.password = cfg.password, ""
    if cfg.password == "***": cfg.password = ""
    return datasource_store.save(cfg)


@app.delete("/datasources/{ds_id}")
def delete_datasource(ds_id: str):
    try:
        datasource_store.delete(ds_id)
        return {"deleted": ds_id}
    except KeyError:
        raise HTTPException(status_code=404, detail="Datasource not found")


@app.post("/datasources/{ds_id}/test")
def test_datasource(ds_id: str):
    ds = datasource_store.get(ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    return datasource_store.test_connection(DataSourceConfig(**ds))


@app.post("/datasources/{ds_id}/scan")
def scan_datasource(ds_id: str):
    ds = datasource_store.get(ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    try:
        cfg = DataSourceConfig(**ds)
        snapshot = datasource_store.scan_metadata(cfg)
        candidates = generate_candidates(snapshot)
        review_store.save_candidates(candidates)
        return {"snapshot": snapshot.model_dump(), "candidates_count": len(candidates)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/ontology")
def ontology():
    return registry.ontology


@app.get("/semantic/graph")
def semantic_graph():
    return registry.graph()


@app.put("/ontology/entities/{name}")
def save_entity(name: str, cfg: dict):
    try:
        with semantic_write_lock:
            result = registry.save_entity(name, cfg)
            _snapshot_semantic("save_entity", detail=name)
            return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/ontology/entities/{name}")
def delete_entity(name: str):
    try:
        with semantic_write_lock:
            registry.delete_entity(name)
            _snapshot_semantic("delete_entity", detail=name)
        return {"deleted": name}
    except KeyError:
        raise HTTPException(status_code=404, detail="Entity not found in custom layer")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/ontology/relationships")
def save_relationships(relationships: List[dict] = Body()):
    try:
        with semantic_write_lock:
            result = registry.save_relationships(relationships)
            _snapshot_semantic("save_relationships", detail=f"count={len(relationships)}")
            return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/metrics")
def metrics():
    return registry.metrics


@app.post("/metrics")
def create_metric(m: MetricDefinition):
    try:
        with semantic_write_lock:
            result = registry.add_metric(m)
            _snapshot_semantic("create_metric", detail=m.name)
            return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/metrics/{name}")
def update_metric(name: str, m: MetricDefinition):
    try:
        with semantic_write_lock:
            result = registry.update_metric(name, m)
            _snapshot_semantic("update_metric", detail=f"{name}->{m.name}")
            return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Metric not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/metrics/{name}")
def delete_metric(name: str):
    try:
        with semantic_write_lock:
            registry.delete_metric(name)
            _snapshot_semantic("delete_metric", detail=name)
        return {"deleted": name}
    except KeyError:
        raise HTTPException(status_code=404, detail="Metric not found (only custom metrics can be deleted)")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/metadata/scan", response_model=MetadataScanResponse)
def metadata_scan(req: MetadataScanRequest):
    try:
        snapshot = get_metadata_scanner().scan(req.catalogs)
        candidates = generate_candidates(snapshot)
        if req.save_candidates:
            review_store.save_candidates(candidates)
        return MetadataScanResponse(snapshot=snapshot, candidates=candidates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/semantic/candidates")
def create_candidate(candidate: SemanticCandidate):
    review_store.save_candidates([candidate])
    return review_store.list().get(candidate.id, candidate.model_dump())


@app.get("/semantic/candidates")
def semantic_candidates():
    return review_store.list()


@app.post("/semantic/candidates/{candidate_id:path}/review")
def review_candidate(candidate_id: str, decision: ReviewDecision):
    try:
        with semantic_write_lock:
            result = review_store.review(candidate_id, decision)
            if decision.status == "approved":
                review_store.export_approved_yaml()
                # Auto-merge candidate metrics as custom metrics
                for name, cfg in review_store.get_approved_metrics().items():
                    if name not in registry.metrics.get("metrics", {}):
                        from .models import MetricDefinition
                        registry.add_metric(MetricDefinition(
                            name=name, expression=cfg["expression"],
                            description=cfg.get("description", ""),
                            entity=cfg.get("entity"), unit=cfg.get("unit"),
                        ))
                registry.reload()
            return result
    except KeyError:
        raise HTTPException(status_code=404, detail="Candidate not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/semantic/merge")
def semantic_merge():
    """Export all approved candidates to ontology and reload."""
    with semantic_write_lock:
        yaml_text = review_store.export_approved_yaml()
        registry.reload()
        _snapshot_semantic("semantic_merge")
    return {"merged": True, "approved_yaml": yaml_text}


@app.post("/semantic/resolve")
def semantic_resolve(req: ChatRequest):
    try:
        return registry.resolve(req.question)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/plan/semantic", response_model=QueryPlan)
def build_semantic_plan(intent: SemanticIntent):
    """Compile an explicit governed SemanticIntent without natural-language resolution."""
    try:
        return _compile_governed_plan(intent)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/plan", response_model=QueryPlan)
def build_plan(req: ChatRequest):
    try:
        intent = registry.resolve(req.question)
        return _compile_governed_plan(intent, roles=req.roles, attributes=req.attributes, user=req.user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    import time as _time
    t0 = _time.time()
    try:
        sid = req.session_id
        if not sid:
            sid = session_store.create_session()
        session_store.add_message(sid, "user", req.question)
        audit_log.log("chat", req.question, user=req.user)

        # Governance-aware cache key: never share cached governed results across
        # different role/RLS attribute contexts.
        cache_context = {
            "user": req.user,
            "roles": sorted(req.roles),
            "attributes": req.attributes,
        }
        cached = query_cache.get(req.question, context=cache_context)
        if cached and not req.preview_only:
            cached["session_id"] = sid
            cached["from_cache"] = True
            return cached

        intent = registry.resolve(req.question)

        # Uncertainty: check if key fields were resolved
        confidence = _assess_confidence(intent, req.question)

        plan = _compile_governed_plan(intent, roles=req.roles, attributes=req.attributes, user=req.user)
        intent = plan.intent

        # JOIN paths are now produced by the semantic planner itself.
        join_paths = plan.join_paths

        if req.preview_only:
            return {"session_id": sid, "intent": intent.model_dump(), "plan": plan.model_dump(),
                    "confidence": confidence, "join_paths": join_paths, "preview": True}

        executor = get_executor()
        data = executor.execute_plan(plan.sql)
        if intent.analysis_mode == "diagnostic":
            data["rca"] = rca_engine.analyze(data, question=req.question)
            data["evidence_graph"] = evidence_graph_builder.build(plan, data, data["rca"])
        answer = answer_composer.compose(intent, data)

        # Prepend uncertainty warning if low confidence
        if confidence["score"] < 0.6:
            answer = f"⚠️ {confidence['reason']}\n\n{answer}"

        # Evidence chain
        evidence = {
            "resolved_intent": intent.model_dump(),
            "sql_executed": plan.sql,
            "data_sources": [],
            "join_paths": join_paths,
            "governance": plan.governance,
            "lineage": plan.lineage,
        }
        for e in plan.required_entities:
            try:
                evidence["data_sources"].append(registry.table_ref(e))
            except (KeyError, TypeError):
                pass

        session_store.add_message(sid, "assistant", answer, {"intent": intent.model_dump()})
        resp = ChatResponse(intent=intent, plan=plan, data=data, answer=answer)
        result = {"session_id": sid, "confidence": confidence, "evidence": evidence, **resp.model_dump()}

        # Cache successful response
        duration_ms = (_time.time() - t0) * 1000
        query_stats.record(req.question, True, duration_ms)
        runtime_query_store.record({
            "question": req.question, "user": req.user, "roles": req.roles, "success": True,
            "duration_ms": round(duration_ms, 2), "subject": intent.subject.model_dump() if intent.subject else None,
            "metrics": intent.metrics, "catalogs": plan.physical_plan.get("catalogs", []),
            "normalized_cost": (plan.governance or {}).get("estimated_cost"),
            "semantic_version": (plan.lineage or {}).get("semantic_digest"),
        })
        audit_center.emit(category="semantic_query", action="execute", actor=req.user or "anonymous",
                          tenant_id=str((req.attributes or {}).get("tenant_id") or default_tenant_id()),
                          resource_type="semantic_query", resource_id=str((plan.lineage or {}).get("query_id") or sid),
                          decision="allow", status="success", correlation_id=getattr(request.state,"correlation_id",""),
                          detail={"question":req.question,"metrics":intent.metrics,"entities":plan.required_entities,
                                  "catalogs":plan.physical_plan.get("catalogs",[]),"duration_ms":round(duration_ms,2)},
                          provenance={"semantic_digest":(plan.lineage or {}).get("semantic_digest")}, source="chat")
        query_cache.set(req.question, result, context=cache_context)
        return result
    except Exception as e:
        duration_ms = (_time.time() - t0) * 1000
        query_stats.record(req.question, False, duration_ms, error=str(e))
        runtime_query_store.record({"question": req.question, "user": req.user, "roles": req.roles, "success": False,
                                    "duration_ms": round(duration_ms, 2), "error": str(e)})
        audit_center.emit(category="semantic_query", action="execute", actor=req.user or "anonymous",
                          tenant_id=str((req.attributes or {}).get("tenant_id") or default_tenant_id()),
                          resource_type="semantic_query", resource_id=getattr(request.state,"correlation_id",""),
                          decision="deny", status="failure", correlation_id=getattr(request.state,"correlation_id",""),
                          detail={"question":req.question,"duration_ms":round(duration_ms,2),"error":str(e)}, source="chat")
        raise HTTPException(status_code=400, detail=str(e))


def _assess_confidence(intent, question: str) -> dict:
    """Assess confidence in the semantic resolution."""
    score = 1.0
    reasons = []
    if not intent.subject or not intent.subject.reference:
        score -= 0.2
        reasons.append("未识别到具体业务主体引用；将按主体类型进行范围查询")
    if not intent.metric:
        score -= 0.3
        reasons.append("未匹配到已注册指标")
    if not intent.related_entities:
        score -= 0.2
        reasons.append("未关联到任何实体")
    # Check if question is too vague
    if len(question) < 5:
        score -= 0.2
        reasons.append("问题过于简短")
    score = max(0.0, min(1.0, score))
    reason = "；".join(reasons) if reasons else "解析完整"
    return {"score": round(score, 2), "reason": reason}



@app.post("/analytics/timeseries")
def analyze_timeseries(payload: dict = Body(...)):
    rows = payload.get("rows") or []
    value_field = payload.get("value_field", "value")
    time_field = payload.get("time_field", "timestamp")
    threshold = float(payload.get("anomaly_threshold", 3.5))
    return timeseries_engine.analyze(rows, value_field=value_field, time_field=time_field, anomaly_threshold=threshold)


@app.get("/knowledge/search")
def knowledge_search(q: str, top_k: int = 5, doc_type: str = ""):
    filters = {"type": doc_type} if doc_type else None
    return {"query": q, "backend": knowledge_retriever.health(), "results": knowledge_retriever.search(q, top_k=top_k, filters=filters)}


@app.post("/knowledge/documents")
def knowledge_upsert_document(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "knowledge_engineer"))
    chunk_size = int(payload.pop("chunk_size", 420))
    overlap = int(payload.pop("overlap", 80))
    try:
        return knowledge_ingestion.ingest_documents([payload], actor=actor, chunk_size=chunk_size, overlap=overlap)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/knowledge/ingest")
def knowledge_ingest(payload: dict = Body(...)):
    docs = payload.get("documents") or []
    if not isinstance(docs, list) or not docs:
        raise HTTPException(status_code=400, detail="documents must be a non-empty list")
    try:
        return knowledge_ingestion.ingest_documents(docs, actor=str(payload.get("actor", "knowledge_engineer")),
            chunk_size=int(payload.get("chunk_size", 420)), overlap=int(payload.get("overlap", 80)))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/knowledge/documents")
def knowledge_documents(limit: int = 100, doc_type: str = "", status: str = ""):
    return {"documents": knowledge_store.list_documents(limit=limit, doc_type=doc_type, status=status)}


@app.get("/knowledge/stats")
def knowledge_stats():
    return {**knowledge_store.stats(), "retrieval": knowledge_retriever.health()}


@app.get("/knowledge/rca-cases/search")
def knowledge_rca_case_search(q: str, top_k: int = 5):
    return {"query": q, "results": historical_rca_retriever.search(q, top_k=top_k)}


# --- V1.2 Knowledge Quality & Learning Loop ---
@app.post("/knowledge/workflow/submit")
def knowledge_workflow_submit(payload: dict = Body(...)):
    actor=str(payload.pop("actor","knowledge_engineer"))
    try: return knowledge_workflow.submit_document(payload,actor=actor)
    except Exception as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.post("/knowledge/workflow/{document_id}/{version}/approve")
def knowledge_workflow_approve(document_id:str,version:str,payload:dict=Body(default={})):
    try:
        result=knowledge_workflow.approve(document_id,version,actor=str(payload.get("actor","knowledge_approver")),effective_from=payload.get("effective_from"))
        knowledge_backend.upsert_chunks(result["chunks"])
        result["graph_ingestion"] = graph_ingestion.ingest_knowledge(result["document"])
        return result
    except KeyError: raise HTTPException(status_code=404,detail="Knowledge document not found")

@app.post("/knowledge/workflow/{document_id}/{version}/retire")
def knowledge_workflow_retire(document_id:str,version:str,payload:dict=Body(default={})):
    try: return knowledge_workflow.retire(document_id,version,actor=str(payload.get("actor","knowledge_approver")),reason=str(payload.get("reason","")))
    except KeyError: raise HTTPException(status_code=404,detail="Knowledge document not found")

@app.post("/knowledge/workflow/{document_id}/{version}/supersede")
def knowledge_workflow_supersede(document_id:str,version:str,payload:dict=Body(...)):
    actor=str(payload.pop("actor","knowledge_approver"))
    try:
        result=knowledge_workflow.supersede(document_id,version,payload,actor=actor)
        knowledge_backend.upsert_chunks(result["replacement"]["chunks"])
        return result
    except KeyError: raise HTTPException(status_code=404,detail="Knowledge document not found")

@app.post("/knowledge/evaluate")
def knowledge_evaluate(payload:dict=Body(...)):
    return retrieval_evaluator.evaluate(payload.get("cases") or [],top_k=int(payload.get("top_k",5)))

@app.get("/rca/similar-cases")
def rca_similar_cases(q:str,top_k:int=5,subject_entity:str="",subject_reference:str=""):
    subject={"entity":subject_entity,"reference":subject_reference} if subject_entity or subject_reference else None
    return {"query":q,"results":rca_similarity.search(q,subject=subject,top_k=top_k)}

@app.get("/rca/calibration")
def rca_calibration():
    return {"weights":rca_calibrator.weights()}

@app.post("/rca/cases/{case_id}/knowledge-candidate")
def rca_case_to_knowledge_candidate(case_id:str,payload:dict=Body(default={})):
    case=rca_case_store.get(case_id)
    if not case: raise HTTPException(status_code=404,detail="RCA case not found")
    try: return knowledge_workflow.candidate_from_case(case,actor=str(payload.get("actor","engineer")))
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/knowledge/candidates")
def knowledge_candidates(limit:int=100,status:str=""):
    return {"candidates":knowledge_workflow.list_candidates(limit=limit,status=status)}

@app.post("/knowledge/candidates/{candidate_id}/approve")
def approve_knowledge_candidate(candidate_id:str,payload:dict=Body(default={})):
    try:
        result = knowledge_workflow.promote_candidate(candidate_id,document=payload.get("document"),actor=str(payload.get("actor","knowledge_approver")))
        result["graph_ingestion"] = graph_ingestion.ingest_knowledge(result["knowledge"]["document"])
        return result
    except KeyError: raise HTTPException(status_code=404,detail="Knowledge candidate not found")


# --- V1.4 Industrial Failure Model & FMEA Studio ---

@app.post("/fmea")
def create_fmea(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        row = fmea_store.create(payload, actor=actor)
        if row.get("status") == "approved":
            row["graph_ingestion"] = failure_model_ingestion.ingest_fmea(row)
        return row
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/fmea")
def list_fmea(limit: int = 100, status: str = "", asset: str = "", component: str = ""):
    return {"records": fmea_store.list(limit=limit, status=status, asset=asset, component=component), "stats": fmea_store.stats()}

@app.get("/fmea/risk-ranking")
def fmea_risk_ranking(limit: int = 20, status: str = "approved"):
    return {"records": fmea_store.rank(limit=limit, status=status), "stats": fmea_store.stats()}

@app.get("/fmea/{fmea_id}")
def get_fmea(fmea_id: str):
    row = fmea_store.get(fmea_id)
    if not row: raise HTTPException(status_code=404, detail="FMEA record not found")
    return row

@app.put("/fmea/{fmea_id}")
def update_fmea(fmea_id: str, payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        return fmea_store.update(fmea_id, payload, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="FMEA record not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/fmea/{fmea_id}/approve")
def approve_fmea(fmea_id: str, payload: dict = Body(default={})):
    try:
        row = fmea_store.approve(fmea_id, actor=str(payload.get("actor", "reliability_engineer")))
        row["graph_ingestion"] = failure_model_ingestion.ingest_fmea(row)
        return row
    except KeyError:
        raise HTTPException(status_code=404, detail="FMEA record not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/fmea/{fmea_id}/retire")
def retire_fmea(fmea_id: str, payload: dict = Body(default={})):
    try:
        return fmea_store.retire(fmea_id, actor=str(payload.get("actor", "reliability_engineer")), reason=str(payload.get("reason", "")))
    except KeyError:
        raise HTTPException(status_code=404, detail="FMEA record not found")

@app.get("/knowledge-graph")
def knowledge_graph_export():
    return industrial_graph.export()


@app.get("/knowledge-graph/nodes")
def knowledge_graph_nodes(node_type: str = "", limit: int = 200):
    return {"nodes": industrial_graph.nodes(node_type=node_type, limit=limit)}


@app.get("/knowledge-graph/edges")
def knowledge_graph_edges(relation: str = "", limit: int = 500):
    return {"edges": industrial_graph.edges(relation=relation, limit=limit)}


@app.post("/knowledge-graph/reason")
def knowledge_graph_reason(payload: dict = Body(...)):
    return {"hypotheses": causal_reasoner.rank_failure_modes(payload.get("evidence_terms") or [], top_k=int(payload.get("top_k", 5)))}


@app.get("/knowledge-graph/failure-modes/{failure_mode_id}/explain")
def knowledge_graph_explain(failure_mode_id: str):
    return causal_reasoner.explain_path(failure_mode_id)


@app.post("/knowledge-graph/ingest-document")
def knowledge_graph_ingest_document(payload: dict = Body(...)):
    return graph_ingestion.ingest_knowledge(payload)


@app.post("/knowledge-graph/ingest-rca-case/{case_id}")
def knowledge_graph_ingest_case(case_id: str):
    case = rca_case_store.get(case_id)
    if not case:
        raise HTTPException(404, "RCA case not found")
    return graph_ingestion.ingest_rca_case(case)


@app.post("/rca/analyze")
def analyze_rca(payload: dict = Body(...)):
    data = payload.get("data") or payload
    question = str(payload.get("question", ""))
    rca = rca_engine.analyze(data, question=question)
    return rca


@app.post("/rca/temporal-chain")
def rca_temporal_chain(payload: dict = Body(...)):
    return temporal_engine.build_chain(payload.get("anchor_time"), payload.get("events") or [],
                                       before_minutes=int(payload.get("before_minutes", 120)),
                                       after_minutes=int(payload.get("after_minutes", 30)))


@app.post("/rca/sensor-correlation")
def rca_sensor_correlation(payload: dict = Body(...)):
    return sensor_correlation_engine.lag_correlation(payload.get("driver_rows") or [], payload.get("target_rows") or [],
        driver_field=payload.get("driver_field", "value"), target_field=payload.get("target_field", "value"),
        max_lag_points=int(payload.get("max_lag_points", 6)))


@app.post("/rca/baseline")
def rca_baseline(payload: dict = Body(...)):
    return operating_baseline_engine.compare(payload.get("current_rows") or [], payload.get("baseline_rows") or [],
                                             value_field=payload.get("value_field", "value"))


@app.post("/rca/feedback")
def rca_feedback(payload: dict = Body(...)):
    if payload.get("accepted") is None and not payload.get("correct_cause"):
        raise HTTPException(status_code=400, detail="accepted or correct_cause is required")
    return rca_feedback_store.add(payload)


@app.get("/rca/feedback")
def rca_feedback_list(limit: int = 100):
    return {"feedback": rca_feedback_store.list(limit)}


# --- V1.0 Enterprise Pilot: RCA Case Management & runtime operations ---

@app.post("/rca/cases")
def create_rca_case(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "anonymous"))
    return rca_case_store.create(payload, actor=actor)


@app.get("/rca/cases")
def list_rca_cases(limit: int = 100, status: str = ""):
    return {"cases": rca_case_store.list(limit=limit, status=status or None)}


@app.get("/rca/cases/{case_id}")
def get_rca_case(case_id: str):
    row = rca_case_store.get(case_id)
    if not row:
        raise HTTPException(status_code=404, detail="RCA case not found")
    return row


@app.post("/rca/cases/{case_id}/analyze")
def analyze_rca_case(case_id: str, payload: dict = Body(default={})):
    case = rca_case_store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="RCA case not found")
    data = payload.get("data") or case.get("analysis_input") or payload
    analysis = rca_engine.analyze(data, question=case.get("question", ""))
    graph = payload.get("evidence_graph")
    return rca_case_store.attach_analysis(case_id, analysis, evidence_graph=graph, actor=str(payload.get("actor", "system")))


@app.post("/rca/cases/{case_id}/review")
def review_rca_case(case_id: str, payload: dict = Body(...)):
    try:
        actor = str(payload.pop("actor", "engineer"))
        row = rca_case_store.review(case_id, payload, actor=actor)
        rca_feedback_store.add({"case_id": case_id, **payload, "reviewed_by": actor})
        return row
    except KeyError:
        raise HTTPException(status_code=404, detail="RCA case not found")


@app.post("/rca/cases/{case_id}/resolve")
def resolve_rca_case(case_id: str, payload: dict = Body(...)):
    try:
        actor = str(payload.pop("actor", "engineer"))
        row = rca_case_store.resolve(case_id, payload, actor=actor)
        row["graph_ingestion"] = graph_ingestion.ingest_rca_case(row)
        return row
    except KeyError:
        raise HTTPException(status_code=404, detail="RCA case not found")



@app.get("/rca/workflows")
def list_rca_workflows(status: str = "", asset: str = "", limit: int = 100):
    return rca_workflow.list(status=status, asset=asset, limit=limit)

@app.get("/rca/cases/{case_id}/workflow")
def get_rca_workflow(case_id: str):
    try:
        return rca_workflow.get(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="RCA case not found")

@app.post("/rca/cases/{case_id}/close")
def close_rca_case(case_id: str, payload: dict = Body(default={})):
    try:
        return rca_case_store.close(case_id, actor=str(payload.get("actor", "engineer")), comment=str(payload.get("comment", "")))
    except KeyError:
        raise HTTPException(status_code=404, detail="RCA case not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

# --- V1.5 Reliability Intelligence & Predictive Maintenance ---

@app.post("/reliability/sensor-mappings")
def upsert_failure_sensor_mapping(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        return failure_sensor_mappings.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/reliability/sensor-mappings")
def list_failure_sensor_mappings(failure_mode: str = "", status: str = "approved", limit: int = 200):
    return {"mappings": failure_sensor_mappings.list(failure_mode=failure_mode, status=status, limit=limit)}

@app.post("/reliability/assess")
def assess_reliability(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "system"))
    try:
        return reliability_service.assess(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/reliability/assets/{asset}/health")
def reliability_asset_health(asset: str, limit: int = 30):
    return reliability_service.asset_health(asset, limit=limit)

@app.get("/reliability/risk-ranking")
def reliability_risk_ranking(limit: int = 20):
    return {"assets": reliability_service.risk_ranking(limit=limit)}

# --- V1.6 Condition Analytics & Predictive Maintenance Integration ---

@app.post("/condition/definitions")
def upsert_condition_definition(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        return condition_definitions.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/condition/definitions")
def list_condition_definitions(sensor: str = "", status: str = "approved", limit: int = 500):
    return {"definitions": condition_definitions.list(sensor=sensor, status=status, limit=limit)}

@app.post("/condition/baselines")
def upsert_condition_baseline(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        return condition_baselines.upsert(str(payload.get("asset") or ""), str(payload.get("indicator") or ""), payload.get("values") or [], actor=actor, metadata=payload.get("metadata"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/condition/baselines/{asset}/{indicator}")
def get_condition_baseline(asset: str, indicator: str):
    row = condition_baselines.get(asset, indicator)
    if not row:
        raise HTTPException(status_code=404, detail="condition baseline not found")
    return row

@app.post("/condition/analyze")
def analyze_condition(payload: dict = Body(...)):
    try:
        return condition_service.analyze(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/reliability/assess-timeseries")
def assess_reliability_from_timeseries(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "system"))
    try:
        condition = condition_service.analyze(payload)
        rel_payload = dict(payload)
        rel_payload["condition_indicators"] = condition["condition_indicators"]
        reliability = reliability_service.assess(rel_payload, actor=actor)
        return {"condition": condition, "reliability": reliability}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/predictive/rul")
def estimate_rul(payload: dict = Body(...)):
    return rul_adapter.estimate(payload)

@app.get("/predictive/assets/{asset}/rul")
def estimate_asset_rul(asset: str, limit: int = 30, failure_threshold: float = 20.0, interval_hours: float = 24.0):
    rows = reliability_service.history(asset, limit=limit)
    if len(rows) < 2:
        return rul_adapter.estimate({"health_scores": [], "failure_threshold": failure_threshold, "interval_hours": interval_hours})
    chronological = sorted(rows, key=lambda r: str(r.get("created_at", "")))
    scores = [float(r.get("asset_health_score", 0.0)) for r in chronological]
    result = rul_adapter.estimate({"health_scores": scores, "failure_threshold": failure_threshold, "interval_hours": interval_hours})
    return {"asset": asset, "observations": len(scores), **result}

@app.post("/maintenance/recommend")
def recommend_maintenance(payload: dict = Body(...)):
    reliability = payload.get("reliability") or payload
    rul = payload.get("rul")
    return maintenance_decision.recommend(reliability, rul)

@app.post("/cmms/work-order-candidates")
def create_cmms_candidate(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "system"))
    try:
        return cmms_candidates.create(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/cmms/work-order-candidates")
def list_cmms_candidates(status: str = "", limit: int = 200):
    return {"candidates": cmms_candidates.list(status=status, limit=limit)}

@app.post("/cmms/work-order-candidates/{candidate_id}/approve")
def approve_cmms_candidate(candidate_id: str, payload: dict = Body(default={})):
    try:
        return cmms_candidates.transition(candidate_id, "approved", actor=str(payload.get("actor", "maintenance_planner")))
    except KeyError:
        raise HTTPException(status_code=404, detail="work-order candidate not found")

@app.post("/cmms/work-order-candidates/{candidate_id}/dispatch")
def dispatch_cmms_candidate(candidate_id: str, payload: dict = Body(default={})):
    external_id = str(payload.get("external_work_order_id", "")).strip()
    if not external_id:
        raise HTTPException(status_code=400, detail="external_work_order_id is required to confirm CMMS dispatch")
    try:
        row = cmms_candidates.transition(candidate_id, "dispatched", actor=str(payload.get("actor", "cmms_adapter")), external_id=external_id)
        return {"candidate": row, "integration_contract": cmms_candidates.integration_contract(row)}
    except KeyError:
        raise HTTPException(status_code=404, detail="work-order candidate not found")

@app.get("/cmms/work-order-candidates/{candidate_id}/contract")
def cmms_candidate_contract(candidate_id: str):
    row = cmms_candidates.get(candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="work-order candidate not found")
    return cmms_candidates.integration_contract(row)

# --- V1.7 Condition Model Templates, Feature Pipelines & Model Registry ---

@app.get("/condition-models")
def list_condition_models(status: str = "approved", limit: int = 100):
    return {"templates": condition_models.list(status=status, limit=limit)}

@app.get("/condition-models/{template_id}")
def get_condition_model(template_id: str):
    row = condition_models.get(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="condition model template not found")
    return row

@app.post("/condition-models")
def upsert_condition_model(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "reliability_engineer"))
    try:
        return condition_models.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/condition-models/{template_id}/apply")
def apply_condition_model(template_id: str, payload: dict = Body(default={})):
    try:
        return condition_models.apply(template_id, condition_definitions, actor=str(payload.get("actor", "template")))
    except KeyError:
        raise HTTPException(status_code=404, detail="condition model template not found")

@app.post("/feature-pipelines")
def upsert_feature_pipeline(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "data_engineer"))
    try:
        return feature_pipelines.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/feature-pipelines")
def list_feature_pipelines(status: str = "", limit: int = 200):
    return {"pipelines": feature_pipelines.list(status=status, limit=limit)}

@app.post("/feature-pipelines/{pipeline_id}/run")
def run_feature_pipeline(pipeline_id: str, payload: dict = Body(...)):
    try:
        return feature_pipelines.execute(pipeline_id, payload, condition_service, actor=str(payload.get("actor", "system")))
    except KeyError:
        raise HTTPException(status_code=404, detail="feature pipeline not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/feature-pipelines/runs")
def list_feature_pipeline_runs(pipeline_id: str = "", limit: int = 100):
    return {"runs": feature_pipelines.runs(pipeline_id=pipeline_id, limit=limit)}

@app.get("/data-bindings/contract")
def data_binding_contract():
    return data_bindings.contract()

@app.post("/data-bindings")
def upsert_data_binding(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "data_engineer"))
    try:
        return data_bindings.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/data-bindings")
def list_data_bindings(status: str = "", target: str = "", limit: int = 200):
    return {"bindings": data_bindings.list(status=status, target=target, limit=limit)}

@app.post("/data-bindings/{binding_id}/approve")
def approve_data_binding(binding_id: str, payload: dict = Body(default={})):
    try:
        return data_bindings.approve(binding_id, actor=str(payload.get("actor", "data_governor")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")

@app.post("/data-bindings/{binding_id}/preview")
def preview_data_binding(binding_id: str, payload: dict = Body(...)):
    try:
        return data_bindings.preview(binding_id, payload.get("records") or [], limit=int(payload.get("limit", 20)))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")

@app.post("/data-bindings/{binding_id}/run")
def run_data_binding(binding_id: str, payload: dict = Body(...)):
    try:
        return data_bindings.execute(binding_id, payload.get("records") or [], {"asset_registry": asset_registry, "cmms_candidates": cmms_candidates}, actor=str(payload.get("actor", "system")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/data-bindings/runs")
def list_data_binding_runs(binding_id: str = "", limit: int = 100):
    return {"runs": data_bindings.runs(binding_id=binding_id, limit=limit)}


@app.post("/integration/runtime/{binding_id}/configure")
def configure_integration_runtime(binding_id: str, payload: dict = Body(default={})):
    try:
        return integration_runtime.configure(binding_id, payload, actor=str(payload.get("actor", "data_engineer")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/integration/runtime/{binding_id}")
def get_integration_runtime(binding_id: str):
    try:
        return integration_runtime.state(binding_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")

@app.post("/integration/runtime/{binding_id}/quality-rules")
def add_integration_quality_rule(binding_id: str, payload: dict = Body(...)):
    try:
        return integration_runtime.add_quality_rule(binding_id, payload, actor=str(payload.get("actor", "data_governor")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/integration/quality-rules")
def list_integration_quality_rules(binding_id: str = "", limit: int = 500):
    return {"rules": integration_runtime.quality_rules(binding_id=binding_id, limit=limit)}

@app.post("/integration/runtime/{binding_id}/schema/inspect")
def inspect_integration_schema(binding_id: str, payload: dict = Body(...)):
    try:
        return integration_runtime.inspect_schema(binding_id, payload.get("records") or [], accept=False, actor=str(payload.get("actor", "runtime")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")

@app.post("/integration/runtime/{binding_id}/schema/accept")
def accept_integration_schema(binding_id: str, payload: dict = Body(...)):
    try:
        return integration_runtime.accept_schema(binding_id, payload.get("records") or [], actor=str(payload.get("actor", "data_governor")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")

@app.post("/integration/runtime/{binding_id}/run")
def run_integration_runtime(binding_id: str, payload: dict = Body(...)):
    try:
        return integration_runtime.execute(binding_id, payload.get("records") or [], {"asset_registry": asset_registry, "cmms_candidates": cmms_candidates}, actor=str(payload.get("actor", "runtime")))
    except KeyError:
        raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/integration/dead-letters")
def list_integration_dead_letters(binding_id: str = "", status: str = "", limit: int = 200):
    return {"dead_letters": integration_runtime.dead_letters(binding_id=binding_id, status=status, limit=limit)}

@app.post("/integration/dead-letters/{dead_letter_id}/retry")
def retry_integration_dead_letter(dead_letter_id: str, payload: dict = Body(default={})):
    try:
        return integration_runtime.retry_dead_letter(dead_letter_id, {"asset_registry": asset_registry, "cmms_candidates": cmms_candidates}, actor=str(payload.get("actor", "operator")))
    except KeyError:
        raise HTTPException(status_code=404, detail="dead letter not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/integration/monitoring")
def integration_monitoring():
    return integration_runtime.monitoring()

@app.get("/connectors/contract")
def connector_contract():
    return {"connector": connectors.contract(), "edge_agent": edge_agents.contract()}

@app.post("/connectors")
def upsert_connector(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "integration_engineer"))
    try:
        return connectors.upsert(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/connectors")
def list_connectors(status: str = "", connector_type: str = "", limit: int = 200):
    return {"connectors": connectors.list(status=status, connector_type=connector_type, limit=limit)}

@app.post("/connectors/{connector_id}/approve")
def approve_connector(connector_id: str, payload: dict = Body(default={})):
    try:
        return connectors.approve(connector_id, actor=str(payload.get("actor", "integration_approver")))
    except KeyError:
        raise HTTPException(status_code=404, detail="connector not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/connectors/{connector_id}/retire")
def retire_connector(connector_id: str, payload: dict = Body(default={})):
    try:
        return connectors.retire(connector_id, actor=str(payload.get("actor", "integration_approver")))
    except KeyError:
        raise HTTPException(status_code=404, detail="connector not found")

@app.get("/connectors/batches")
def list_connector_batches(connector_id: str = "", limit: int = 100):
    return {"batches": connectors.batches(connector_id=connector_id, limit=limit)}

@app.post("/edge-agents")
def register_edge_agent(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "integration_engineer"))
    try:
        return edge_agents.register(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/edge-agents")
def list_edge_agents(status: str = "", limit: int = 200):
    return {"agents": edge_agents.list(status=status, limit=limit)}

@app.get("/edge-agents/health")
def edge_agent_health(stale_after_seconds: int = 180):
    return edge_agents.health(stale_after_seconds=stale_after_seconds)

@app.post("/edge-agents/{agent_id}/heartbeat")
def edge_agent_heartbeat(agent_id: str, payload: dict = Body(default={})):
    try:
        return edge_agents.heartbeat(agent_id, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="edge agent not found")

@app.post("/edge-agents/{agent_id}/offline")
def edge_agent_offline(agent_id: str, payload: dict = Body(default={})):
    try:
        return edge_agents.set_offline(agent_id, actor=str(payload.get("actor", "operator")))
    except KeyError:
        raise HTTPException(status_code=404, detail="edge agent not found")

@app.post("/integration/connector-batches")
def submit_connector_batch(payload: dict = Body(...)):
    try:
        return connector_batches.submit(payload, {"asset_registry": asset_registry, "cmms_candidates": cmms_candidates}, actor=str(payload.get("actor", "edge_agent")))
    except KeyError:
        raise HTTPException(status_code=404, detail="connector not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _authenticated_principal(request: Request) -> dict:
    auth = getattr(request.state, "auth", None) or {}
    return auth.get("principal") or {}

def _require_tenant_admin(request: Request) -> dict:
    if auth_service.config.mode == "disabled":
        return {}
    principal = _authenticated_principal(request)
    if "tenant_admin" not in (principal.get("roles") or []):
        raise HTTPException(status_code=403, detail="tenant_admin role is required")
    return principal

def _effective_principal_id(request: Request, requested: str = "") -> str:
    if auth_service.config.mode == "disabled":
        return requested
    caller = _authenticated_principal(request)
    caller_id = str(caller.get("principal_id") or "")
    if not caller_id:
        raise HTTPException(status_code=401, detail="authenticated principal is unavailable")
    if not requested or requested == caller_id:
        return caller_id
    if "tenant_admin" not in (caller.get("roles") or []):
        raise HTTPException(status_code=403, detail="cannot act as another principal")
    target = enterprise_identity.principal(requested)
    if not target or enterprise_identity.normalize_tenant(target) != enterprise_identity.normalize_tenant(caller):
        raise HTTPException(status_code=403, detail="cannot act across tenant boundary")
    return requested

# --- V2.6 Enterprise Authentication & SSO ---

@app.get("/auth/config")
def authentication_config():
    return auth_service.config.public_dict()

@app.post("/auth/reload")
def authentication_reload(request: Request):
    _require_tenant_admin(request)
    return auth_service.reload()

@app.post("/auth/dev/token")
def authentication_dev_token(payload: dict = Body(default={})):
    try:
        return auth_service.dev_token(payload)
    except AuthenticationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/auth/me")
def authentication_me(request: Request):
    auth = getattr(request.state, "auth", None) or {}
    if auth_service.config.mode == "disabled":
        return {"authenticated": False, "mode": "disabled", "principal": None}
    if not auth.get("authenticated"):
        raise HTTPException(status_code=401, detail="not authenticated")
    principal = auth.get("principal") or {}
    try:
        context = enterprise_scope.context(str(principal.get("principal_id") or "")).as_dict()
    except Exception:
        context = {}
    return {"authenticated": True, "mode": auth.get("mode"), "principal": principal, "context": context}

@app.get("/auth/audit")
def authentication_audit(request: Request, limit: int = 200):
    _require_tenant_admin(request)
    return {"audit": auth_service.audit(limit=limit)}

# --- V2.5 Enterprise Identity & Multi-Tenant Governance ---

@app.get("/enterprise/contract")
def enterprise_contract():
    from .enterprise_identity import PERMISSIONS
    return {
        "version": "1.0",
        "default_tenant_id": default_tenant_id(),
        "roles": PERMISSIONS,
        "scope_dimensions": ["tenant_id", "org_id", "site_ids", "asset_ids", "connector_ids"],
        "semantics": "Semantic RBAC/RLS governs query meaning; enterprise scope governance controls resource tenancy and operational access.",
    }

@app.post("/enterprise/tenants")
def upsert_enterprise_tenant(request: Request, payload: dict = Body(...)):
    _require_tenant_admin(request)
    actor = str(payload.pop("actor", "platform_admin"))
    try: return enterprise_identity.upsert_tenant(payload, actor=actor)
    except IdentityError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/enterprise/tenants")
def list_enterprise_tenants(request: Request, status: str = "", limit: int = 200):
    _require_tenant_admin(request)
    return {"tenants": enterprise_identity.tenants(status=status, limit=limit)}

@app.post("/enterprise/organizations")
def upsert_enterprise_org(request: Request, payload: dict = Body(...)):
    _require_tenant_admin(request)
    actor = str(payload.pop("actor", "tenant_admin"))
    try: return enterprise_identity.upsert_org(payload, actor=actor)
    except IdentityError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/enterprise/organizations")
def list_enterprise_orgs(request: Request, tenant_id: str = "", limit: int = 500):
    _require_tenant_admin(request)
    return {"organizations": enterprise_identity.orgs(tenant_id=tenant_id, limit=limit)}

@app.post("/enterprise/sites")
def upsert_enterprise_site(request: Request, payload: dict = Body(...)):
    _require_tenant_admin(request)
    actor = str(payload.pop("actor", "tenant_admin"))
    try: return enterprise_identity.upsert_site(payload, actor=actor)
    except IdentityError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/enterprise/sites")
def list_enterprise_sites(request: Request, tenant_id: str = "", org_id: str = "", limit: int = 1000):
    _require_tenant_admin(request)
    return {"sites": enterprise_identity.sites(tenant_id=tenant_id, org_id=org_id, limit=limit)}

@app.post("/enterprise/principals")
def upsert_enterprise_principal(request: Request, payload: dict = Body(...)):
    _require_tenant_admin(request)
    actor = str(payload.pop("actor", "tenant_admin"))
    try: return enterprise_identity.upsert_principal(payload, actor=actor)
    except IdentityError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/enterprise/principals")
def list_enterprise_principals(request: Request, tenant_id: str = "", status: str = "", limit: int = 500):
    _require_tenant_admin(request)
    return {"principals": enterprise_identity.principals(tenant_id=tenant_id, status=status, limit=limit)}

@app.get("/enterprise/principals/{principal_id}/context")
def enterprise_principal_context(principal_id: str, request: Request):
    principal_id = _effective_principal_id(request, principal_id)
    try: return enterprise_scope.context(principal_id).as_dict()
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))

@app.post("/enterprise/access/check")
def enterprise_access_check(request: Request, payload: dict = Body(...)):
    try:
        principal_id = _effective_principal_id(request, str(payload.get("principal_id") or ""))
        return enterprise_scope.check(
            principal_id, str(payload.get("resource_type") or ""),
            str(payload.get("action") or "read"), payload.get("resource") or {}, str(payload.get("resource_id") or ""),
        )
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))

@app.get("/enterprise/access-audit")
def enterprise_access_audit(request: Request, principal_id: str = "", allowed: bool = None, limit: int = 200):
    _require_tenant_admin(request)
    return {"audit": enterprise_identity.audit_rows(principal_id=principal_id, allowed=allowed, limit=limit)}

@app.get("/enterprise/scoped/assets")
def enterprise_scoped_assets(request: Request, principal_id: str = "", limit: int = 500):
    principal_id = _effective_principal_id(request, principal_id)
    try:
        rows = enterprise_scope.filter_resources(principal_id, "asset", "read", asset_registry.list_assets(limit=5000))
        return {"assets": rows[:limit], "total": len(rows)}
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))

@app.get("/enterprise/scoped/connectors")
def enterprise_scoped_connectors(request: Request, principal_id: str = "", limit: int = 500):
    principal_id = _effective_principal_id(request, principal_id)
    try:
        rows = enterprise_scope.filter_resources(principal_id, "connector", "read", connectors.list(limit=5000))
        return {"connectors": rows[:limit], "total": len(rows)}
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))

@app.get("/enterprise/scoped/edge-agents")
def enterprise_scoped_edge_agents(request: Request, principal_id: str = "", limit: int = 500):
    principal_id = _effective_principal_id(request, principal_id)
    try:
        rows = enterprise_scope.filter_resources(principal_id, "edge_agent", "read", edge_agents.list(limit=5000))
        return {"agents": rows[:limit], "total": len(rows)}
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))



@app.get("/enterprise/scoped/fmea")
def enterprise_scoped_fmea(request: Request, principal_id: str = "", status: str = "", limit: int = 500):
    principal_id = _effective_principal_id(request, principal_id)
    try:
        rows = fmea_store.list(limit=1000, status=status)
        rows = enterprise_scope.filter_resources(principal_id, "fmea", "read", rows)
        return {"fmea": rows[:limit], "total": len(rows)}
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))

@app.get("/enterprise/scoped/rca-cases")
def enterprise_scoped_rca_cases(request: Request, principal_id: str = "", status: str = "", limit: int = 500):
    principal_id = _effective_principal_id(request, principal_id)
    try:
        rows = rca_case_store.list(limit=1000, status=status or None)
        rows = enterprise_scope.filter_resources(principal_id, "rca", "read", rows)
        return {"cases": rows[:limit], "total": len(rows)}
    except KeyError: raise HTTPException(status_code=404, detail="principal not found")
    except AccessDenied as exc: raise HTTPException(status_code=403, detail=str(exc))



@app.post("/models")
def register_predictive_model(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "ml_engineer"))
    try:
        return model_registry.register(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/models")
def list_predictive_models(status: str = "", model_type: str = "", limit: int = 200):
    return {"models": model_registry.list(status=status, model_type=model_type, limit=limit)}

@app.post("/models/{model_id}/approve")
def approve_predictive_model(model_id: str, payload: dict = Body(default={})):
    try:
        return model_registry.approve(model_id, actor=str(payload.get("actor", "model_approver")))
    except KeyError:
        raise HTTPException(status_code=404, detail="model not found")

@app.post("/models/{model_id}/retire")
def retire_predictive_model(model_id: str, payload: dict = Body(default={})):
    try:
        return model_registry.retire(model_id, actor=str(payload.get("actor", "model_approver")))
    except KeyError:
        raise HTTPException(status_code=404, detail="model not found")

@app.post("/models/{model_id}/infer")
def infer_predictive_model(model_id: str, payload: dict = Body(...)):
    try:
        return model_registry.infer(model_id, payload, actor=str(payload.get("actor", "system")))
    except KeyError:
        raise HTTPException(status_code=404, detail="model not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/model-datasets")
def register_model_dataset(payload: dict = Body(...)):
    actor=str(payload.pop("actor", "ml_engineer"))
    try: return model_datasets.register(payload, actor=actor)
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/model-datasets")
def list_model_datasets(status: str = "", limit: int = 200):
    return {"datasets": model_datasets.list(status=status, limit=limit)}

@app.post("/models/{model_id}/evaluate/{dataset_id}")
def evaluate_predictive_model(model_id: str, dataset_id: str, payload: dict = Body(default={})):
    try: return model_evaluator.evaluate(model_id, dataset_id, actor=str(payload.get("actor", "ml_validator")))
    except KeyError as exc: raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/model-evaluations")
def list_model_evaluations(model_id: str = "", limit: int = 200):
    return {"evaluations": model_evaluator.list(model_id=model_id, limit=limit)}

@app.post("/model-deployments/{slot}/role")
def set_model_deployment_role(slot: str, payload: dict = Body(...)):
    try: return model_deployments.set_role(slot, str(payload.get("model_id","")), str(payload.get("role","")), actor=str(payload.get("actor","model_approver")))
    except KeyError: raise HTTPException(status_code=404, detail="model not found")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/model-deployments/{slot}/promote")
def promote_model(slot: str, payload: dict = Body(default={})):
    try: return model_deployments.promote(slot, actor=str(payload.get("actor","model_approver")))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/model-deployments/{slot}/rollback")
def rollback_model(slot: str, payload: dict = Body(default={})):
    try: return model_deployments.rollback(slot, actor=str(payload.get("actor","model_approver")))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/model-deployments")
def list_model_deployments(limit: int = 100):
    return {"deployments": model_deployments.list(limit=limit)}

@app.post("/models/{model_id}/monitoring/baseline")
def set_model_monitoring_baseline(model_id: str, payload: dict = Body(...)):
    return model_monitoring.set_baseline(model_id, payload.get("feature_stats") or {}, actor=str(payload.get("actor","ml_engineer")))

@app.post("/models/{model_id}/monitor")
def monitor_model(model_id: str, payload: dict = Body(...)):
    return model_monitoring.monitor(model_id, payload.get("current_feature_stats") or {}, performance=payload.get("performance"), actor=str(payload.get("actor","monitor")))

@app.get("/model-monitoring/events")
def model_monitoring_events(model_id: str = "", limit: int = 100):
    return {"summary": model_monitoring.summary(), "events": model_monitoring.recent(model_id=model_id, limit=limit)}

@app.get("/operations/runtime-queries")
def runtime_queries(limit: int = 100):
    return {"summary": runtime_query_store.summary(), "queries": runtime_query_store.recent(limit)}


# --- V1.9 Asset Reliability Registry & Cockpit ---

@app.post("/assets")
def upsert_asset(payload: dict = Body(...)):
    actor = str(payload.pop("actor", "asset_engineer"))
    try:
        return asset_registry.upsert_asset(payload, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/assets")
def list_assets(asset_type: str = "", status: str = "", parent_asset_id: str = None, limit: int = 500):
    return {"assets": asset_registry.list_assets(asset_type=asset_type, status=status, parent_asset_id=parent_asset_id, limit=limit)}

@app.get("/assets/hierarchy")
def asset_hierarchy(root_asset_id: str = ""):
    try:
        return asset_registry.hierarchy(root_asset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")

@app.get("/assets/{asset_id}")
def get_asset(asset_id: str):
    row = asset_registry.get_asset(asset_id)
    if not row:
        raise HTTPException(status_code=404, detail="asset not found")
    return row

@app.post("/assets/{asset_id}/components")
def upsert_asset_component(asset_id: str, payload: dict = Body(...)):
    actor = str(payload.pop("actor", "asset_engineer"))
    try:
        return asset_registry.upsert_component(asset_id, payload, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/assets/{asset_id}/components")
def list_asset_components(asset_id: str, limit: int = 500):
    return {"components": asset_registry.components(asset_id, limit=limit)}

@app.post("/assets/{asset_id}/sensors")
def bind_asset_sensor(asset_id: str, payload: dict = Body(...)):
    actor = str(payload.pop("actor", "asset_engineer"))
    try:
        return asset_registry.bind_sensor(asset_id, payload, actor=actor)
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/assets/{asset_id}/sensors")
def list_asset_sensors(asset_id: str, limit: int = 1000):
    return {"sensors": asset_registry.sensors(asset_id, limit=limit)}

@app.get("/assets/{asset_id}/cockpit")
def asset_reliability_cockpit(asset_id: str, health_limit: int = 30, days: int = 30):
    try:
        return asset_cockpit.cockpit(asset_id, health_limit=health_limit, days=days)
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")

@app.get("/reliability/fleet")
def reliability_fleet(limit: int = 100):
    return asset_cockpit.fleet(limit=limit)

@app.get("/workspace/home")
def workspace_home(role: str = "reliability_engineer", limit: int = 12):
    return product_workspace.home(role=role, limit=limit)

# --- V2.7 Secret Registry / Credential Management ---
@app.get("/secrets/contract")
def secret_contract():
    return {"version":"1.0","reference":"secret://<provider>/<name>","providers":["env","file","vault","azure-key-vault"],"rules":["secret values are never returned by API","registry persists metadata/reference only","runtime resolves secrets at point of use"]}

@app.post("/secrets")
def register_secret(request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    actor=str(payload.pop("actor","security_admin"))
    try: return secret_registry.register(payload,actor=actor)
    except Exception as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/secrets")
def list_secrets(request: Request, limit: int = 200):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"secrets":secret_registry.list(limit=limit)}

@app.post("/secrets/{secret_id}/check")
def check_secret(secret_id: str, request: Request):
    principal="security_admin"
    if auth_service.config.mode != "disabled": principal=_require_tenant_admin(request).get("principal_id","tenant_admin")
    try: return secret_manager.check(secret_id,principal=principal)
    except KeyError: raise HTTPException(status_code=404,detail="secret metadata not found")

@app.post("/secrets/{secret_id}/rotate")
def rotate_secret(secret_id: str, request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return secret_registry.rotate(secret_id,payload,actor=str(payload.get("actor","security_admin")))
    except KeyError: raise HTTPException(status_code=404,detail="secret metadata not found")
    except Exception as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/secrets/audit")
def secret_audit(request: Request, limit: int = 200):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"audit":secret_registry.audits(limit=limit)}

# --- V2.8 Audit, Compliance & Policy Center ---

@app.get("/audit/summary")
def audit_summary(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return audit_center.summary()

@app.get("/audit/events")
def audit_events(request: Request, actor: str = "", tenant_id: str = "", category: str = "", action: str = "",
                 decision: str = "", status: str = "", resource_type: str = "", resource_id: str = "",
                 correlation_id: str = "", since: str = "", until: str = "", limit: int = 200):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"events": audit_center.search(actor=actor,tenant_id=tenant_id,category=category,action=action,decision=decision,status=status,
        resource_type=resource_type,resource_id=resource_id,correlation_id=correlation_id,since=since,until=until,limit=limit)}

@app.get("/audit/traces/{correlation_id}")
def audit_trace(correlation_id: str, request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"correlation_id":correlation_id,"events":audit_center.trace(correlation_id)}

@app.post("/audit/legacy/import")
def audit_import_legacy(request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return audit_center.import_legacy(limit_each=int(payload.get("limit_each",1000)))

@app.get("/compliance/policies")
def compliance_policies(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"policies":audit_center.policies()}

@app.post("/compliance/policies")
def compliance_add_policy(request: Request, payload: dict = Body(...)):
    principal=_require_tenant_admin(request) if auth_service.config.mode != "disabled" else {"principal_id":"compliance_admin"}
    return audit_center.add_policy(payload,actor=str(principal.get("principal_id") or "compliance_admin"))

@app.get("/compliance/violations")
def compliance_violations(request: Request, status: str = "", severity: str = "", limit: int = 500):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return {"violations":audit_center.violations(status=status,severity=severity,limit=limit)}

@app.post("/compliance/violations/{violation_id}/resolve")
def compliance_resolve_violation(violation_id: str, request: Request, payload: dict = Body(default={})):
    principal=_require_tenant_admin(request) if auth_service.config.mode != "disabled" else {"principal_id":"compliance_admin"}
    try: return audit_center.resolve_violation(violation_id,actor=str(principal.get("principal_id") or "compliance_admin"),comment=str(payload.get("comment") or ""))
    except KeyError: raise HTTPException(status_code=404, detail="violation not found")

@app.get("/compliance/retention")
def compliance_retention(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return audit_center.retention()

@app.put("/compliance/retention")
def compliance_set_retention(request: Request, payload: dict = Body(...)):
    principal=_require_tenant_admin(request) if auth_service.config.mode != "disabled" else {"principal_id":"compliance_admin"}
    return audit_center.set_retention(int(payload.get("retention_days",365)),actor=str(principal.get("principal_id") or "compliance_admin"))

@app.post("/compliance/retention/enforce")
def compliance_enforce_retention(request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return audit_center.enforce_retention(dry_run=bool(payload.get("dry_run",True)))

@app.get("/audit/export")
def audit_export(request: Request, format: str = "json", category: str = "", tenant_id: str = ""):
    from fastapi.responses import PlainTextResponse
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    content=audit_center.export(fmt=format,category=category,tenant_id=tenant_id)
    media="text/csv" if format.lower()=="csv" else "application/json"
    return PlainTextResponse(content,media_type=media)

@app.get("/production/config/validate")
def production_validate_config(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return production_lifecycle.validator.validate()

@app.get("/production/migrations")
def production_migrations(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return production_lifecycle.migrations.status()

@app.post("/production/migrations/apply")
def production_apply_migrations(request: Request):
    principal=_require_tenant_admin(request) if auth_service.config.mode != "disabled" else {"principal_id":"system_admin"}
    return production_lifecycle.migrations.migrate(actor=str(principal.get("principal_id") or "system_admin"))

@app.post("/production/backups")
def production_backup(request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return backup_manager.create(destination=str(payload.get("destination") or "") or None)

@app.post("/production/backups/inspect")
def production_backup_inspect(request: Request, payload: dict = Body(...)):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return backup_manager.inspect(str(payload.get("path") or ""))
    except (FileNotFoundError,ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/production/backups/restore")
def production_backup_restore(request: Request, payload: dict = Body(...)):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return backup_manager.restore_json(str(payload.get("path") or ""), confirm=bool(payload.get("confirm",False)))
    except (FileNotFoundError,ValueError,RuntimeError) as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/production/upgrade/check")
def production_upgrade_check(request: Request, from_version: str = ""):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    return upgrade_advisor.check(from_version)

@app.get("/operations/health")
def operations_health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "persistence": repository.health(),
        "execution_mode": __import__("os").getenv("EXECUTION_MODE", "mock"),
        "semantic_entities": len(registry.ontology.get("entities", {})),
        "semantic_metrics": len(registry.metrics.get("metrics", {})),
        "runtime": runtime_query_store.summary(),
        "knowledge": knowledge_retriever.health(),
        "knowledge_stats": knowledge_store.stats(),
        "knowledge_graph": {"nodes": len(industrial_graph.nodes()), "edges": len(industrial_graph.edges())},
        "fmea": fmea_store.stats(),
        "reliability": {"assessments": len(repository.list("reliability_assessments", limit=1000)), "sensor_mappings": len(failure_sensor_mappings.list(status="", limit=1000))},
        "condition_analytics": {"definitions": len(condition_definitions.list(status="", limit=1000)), "baselines": len(condition_baselines.list(limit=1000))},
        "predictive_maintenance": {"rul_adapter": rul_adapter.name, "cmms_candidates": len(cmms_candidates.list(limit=1000))},
        "condition_models": {"templates": len(condition_models.list(status="", limit=1000))},
        "feature_pipelines": {"jobs": len(feature_pipelines.list(limit=1000)), "runs": len(feature_pipelines.runs(limit=1000))},
        "model_registry": {"models": len(model_registry.list(limit=1000)), "approved": len(model_registry.list(status="approved", limit=1000))},
        "model_monitoring": {"datasets": len(model_datasets.list(limit=1000)), "evaluations": len(model_evaluator.list(limit=1000)), "deployments": len(model_deployments.list(limit=1000)), **model_monitoring.summary()},
        "asset_registry": asset_registry.stats(),
        "asset_cockpit": {"fleet_assets": asset_cockpit.fleet(limit=1000).get("total", 0)},
        "data_bindings": {"bindings": len(data_bindings.list(limit=1000)), "runs": len(data_bindings.runs(limit=1000)), "approved": len(data_bindings.list(status="approved", limit=1000))},
        "integration_runtime": integration_runtime.monitoring(),
        "connectors": connectors.summary(),
        "secrets": secret_manager.health(),
        "audit_compliance": audit_center.summary(),
        "edge_agents": edge_agents.health(),
        "enterprise_identity": enterprise_identity.summary(),
        "authentication": auth_service.health(),
        "observability_sre": telemetry.summary(),
        "production": {"configuration": production_lifecycle.validator.validate(), "migrations": production_lifecycle.migrations.status(), "live": production_lifecycle.live()},
        "enterprise_pilot": {**pilot_pack.readiness(), "data_onboarding": pilot_delivery.onboarding_status()},
    }


# --- V3.1 Enterprise Pilot Pack ---
@app.get("/pilot/scenarios")
def pilot_scenarios():
    return {"items": pilot_pack.scenarios()}

@app.get("/pilot/scenarios/{scenario_id}")
def pilot_scenario(scenario_id: str):
    try: return pilot_pack.get_scenario(scenario_id)
    except KeyError: raise HTTPException(status_code=404, detail="pilot scenario not found")

@app.post("/pilot/scenarios/{scenario_id}/bootstrap")
def pilot_bootstrap(scenario_id: str, request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return pilot_pack.bootstrap(scenario_id, actor="pilot_admin")
    except (KeyError,ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/pilot/scenarios/{scenario_id}/sample-data")
def pilot_sample_data(scenario_id: str, points: int = 96):
    try: pilot_pack.get_scenario(scenario_id)
    except KeyError: raise HTTPException(status_code=404, detail="pilot scenario not found")
    return pilot_pack.synthetic_series(points)

@app.post("/pilot/run-demo")
def pilot_run_demo(request: Request):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return pilot_pack.run_demo(actor="pilot_engineer")
    except (KeyError,ValueError) as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/pilot/kpis")
def pilot_record_kpi(request: Request, payload: dict = Body(...)):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return pilot_pack.record_kpi(payload, actor="pilot_owner")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/pilot/kpis")
def pilot_kpis():
    return pilot_pack.kpis()

@app.get("/pilot/readiness")
def pilot_readiness():
    return pilot_pack.readiness()

@app.get("/pilot/data-contract")
def pilot_data_contract():
    return pilot_delivery.data_contract()

@app.post("/pilot/onboarding/prepare")
def pilot_prepare_onboarding(request: Request, payload: dict = Body(default={})):
    if auth_service.config.mode != "disabled": _require_tenant_admin(request)
    try: return pilot_delivery.prepare_bindings(payload, actor="pilot_data_engineer")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/pilot/onboarding/status")
def pilot_onboarding_status():
    return pilot_delivery.onboarding_status()

@app.get("/pilot/evidence-quality")
def pilot_evidence_quality():
    return pilot_delivery.latest_rca_quality()

@app.post("/pilot/customer-data/{binding_id}/validate")
def pilot_validate_customer_data(binding_id: str, payload: dict = Body(...)):
    try: return pilot_customer_validator.validate(binding_id, payload.get("records") or [], actor=str(payload.get("actor", "pilot_data_engineer")))
    except KeyError: raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/pilot/customer-data/{binding_id}/dry-run")
def pilot_customer_data_dry_run(binding_id: str, payload: dict = Body(...)):
    try: return pilot_customer_validator.dry_run(binding_id, payload.get("records") or [], actor=str(payload.get("actor", "pilot_data_engineer")))
    except KeyError: raise HTTPException(status_code=404, detail="data binding not found")
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/pilot/customer-data/validation")
def pilot_customer_data_validation(binding_id: str = ""):
    return pilot_customer_validator.latest(binding_id=binding_id)

@app.get("/pilot/report")
def pilot_acceptance_report():
    return pilot_delivery.report(pilot_pack.readiness(), pilot_pack.kpis())

@app.get("/pilot/report.md", response_class=PlainTextResponse)
def pilot_acceptance_report_markdown():
    return pilot_delivery.report_markdown(pilot_pack.readiness(), pilot_pack.kpis())


# --- V2.9 Observability & SRE Control Plane ---
def _require_sre_admin(request: Request):
    if auth_service.config.mode == "disabled": return {"principal_id": "sre_admin", "roles": ["tenant_admin"]}
    return _require_tenant_admin(request)

@app.get("/observability/summary")
def observability_summary(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return telemetry.summary()

@app.get("/observability/metrics")
def observability_metrics(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return telemetry.http_metrics()

@app.get("/observability/traces")
def observability_traces(request: Request, trace_id: str = "", status: str = "", limit: int = 200):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return {"spans": telemetry.spans(trace_id=trace_id, status=status, limit=limit)}

@app.get("/observability/traces/{trace_id}")
def observability_trace(trace_id: str, request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return telemetry.trace(trace_id)

@app.post("/observability/spans")
def observability_record_span(request: Request, payload: dict = Body(default={})): 
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    payload.setdefault("correlation_id", getattr(request.state, "correlation_id", ""))
    return telemetry.record_span(payload)

@app.post("/observability/dependencies/check")
def observability_dependency_check(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    def doris_probe():
        import os, time
        if os.getenv("EXECUTION_MODE", "mock").lower() != "doris":
            return {"status":"disabled","mode":"mock"}
        executor=get_executor(); started=time.perf_counter()
        conn=executor.pymysql.connect(**executor.cfg)
        try:
            with conn.cursor() as cur: cur.execute("SELECT 1"); cur.fetchone()
            return {"status":"ok","mode":"doris","latency_ms":round((time.perf_counter()-started)*1000,2)}
        finally: conn.close()
    probes = {
        "persistence": repository.health,
        "knowledge": knowledge_retriever.health,
        "doris": doris_probe,
        "authentication": auth_service.health,
        "secrets": secret_manager.health,
        "edge_agents": lambda: {"status":"ok", **edge_agents.health()},
        "connectors": lambda: {"status":"ok", **connectors.summary()},
        "integration_runtime": lambda: {"status":"ok", **integration_runtime.monitoring()},
    }
    return dependency_health.check(probes)

@app.get("/observability/dependencies")
def observability_dependencies(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return {"dependencies": telemetry.dependencies()}

@app.get("/sre/slos")
def sre_slos(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return telemetry.evaluate_slos()

@app.post("/sre/slos")
def sre_put_slo(request: Request, payload: dict = Body(default={})):
    principal=_require_sre_admin(request)
    try: return telemetry.put_slo(payload, actor=str(principal.get("principal_id") or "sre_admin"))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.get("/sre/alert-rules")
def sre_alert_rules(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return {"rules": telemetry.alert_rules()}

@app.post("/sre/alert-rules")
def sre_put_alert_rule(request: Request, payload: dict = Body(default={})):
    principal=_require_sre_admin(request)
    try: return telemetry.put_alert_rule(payload, actor=str(principal.get("principal_id") or "sre_admin"))
    except ValueError as exc: raise HTTPException(status_code=400, detail=str(exc))

@app.post("/sre/alerts/evaluate")
def sre_evaluate_alerts(request: Request):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return telemetry.evaluate_alerts()

@app.get("/sre/alerts")
def sre_alerts(request: Request, status: str = "", limit: int = 200):
    if auth_service.config.mode != "disabled": _require_sre_admin(request)
    return {"alerts": telemetry.alerts(status=status, limit=limit)}

@app.post("/sre/alerts/{alert_id}/resolve")
def sre_resolve_alert(alert_id: str, request: Request):
    principal=_require_sre_admin(request)
    try: return telemetry.resolve_alert(alert_id, actor=str(principal.get("principal_id") or "sre_admin"))
    except KeyError: raise HTTPException(status_code=404, detail="alert not found")

@app.get("/observability/prometheus")
def prometheus_metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(telemetry.prometheus(), media_type="text/plain; version=0.0.4")


@app.post("/cost/explain")
def explain_cost(intent: SemanticIntent):
    try:
        plan = _compile_governed_plan(intent, user="cost_explain")
        estimate = doris_cost_adapter.estimate_from_plan(plan)
        result = {"estimate": estimate, "physical_plan": plan.physical_plan}
        executor = get_executor()
        if hasattr(executor, "explain") and plan.sql:
            try:
                result["doris_explain"] = doris_cost_adapter.parse(executor.explain(plan.sql[0]))
            except Exception as exc:
                result["doris_explain_error"] = str(exc)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/governance/policy")
def governance_policy():
    return policy_store.policy


@app.post("/governance/reload")
def governance_reload():
    policy_store.reload()
    return {"reloaded": True, "roles": list(policy_store.policy.get("roles", {}).keys())}


@app.get("/semantic/versions")
def semantic_version_list(limit: int = 50):
    return {"versions": semantic_versions.list(limit)}


@app.get("/lineage/queries")
def query_lineage_list(limit: int = 50):
    return {"lineage": query_lineage.recent(limit)}

@app.get("/chat/session/{session_id}")
def get_session(session_id: str):
    history = session_store.get_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": history}


@app.post("/chat/feedback")
def submit_feedback(req: FeedbackRequest):
    feedback_store.add(req.session_id, req.message_index, req.rating, req.comment or "")
    return {"ok": True}


@app.get("/chat/feedback/stats")
def feedback_stats():
    return feedback_store.stats()


@app.get("/suggestions")
def get_suggestions(q: str = ""):
    """Return question suggestions based on ontology and metrics."""
    suggestions = []
    entities = list(registry.ontology.get("entities", {}).keys())
    metrics_cfg = registry.metrics.get("metrics", {})
    # Generate contextual suggestions
    for metric_name, cfg in metrics_cfg.items():
        synonyms = cfg.get("synonyms", [])
        label = synonyms[0] if synonyms else metric_name
        if entities:
            suggestions.append(f"{entities[0]}设备最近一周{label}趋势")
            if len(entities) > 1:
                suggestions.append(f"所有设备的{label}对比")
        suggestions.append(f"哪个设备{label}最高？")
    if q:
        q_lower = q.lower()
        suggestions = [s for s in suggestions if q_lower in s.lower() or any(c in s for c in q)]
    return {"suggestions": suggestions[:8]}


@app.post("/datasources/upload")
async def upload_datasource_file(file: bytes = Body(...)):
    """Upload a file for Excel/CSV datasource. Returns the saved filename."""
    # This is a simplified upload — in production use UploadFile with multipart
    import base64
    upload_dir = Path(__file__).resolve().parents[1] / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Expect base64 encoded file with metadata
    return {"message": "Use multipart upload or place file in data/uploads/ directory"}


@app.post("/datasources/{ds_id}/preview")
def preview_datasource_table(ds_id: str, table: str = "", schema: str = "", limit: int = 10):
    """Preview sample rows from a datasource table."""
    ds = datasource_store.get(ds_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Datasource not found")
    cfg = DataSourceConfig(**ds)
    try:
        conn = datasource_store._connect(cfg)
        try:
            if cfg.type in ("doris", "mysql"):
                import pymysql
                with conn.cursor() as cur:
                    if schema:
                        cur.execute(f"USE `{schema}`")
                    cur.execute(f"SELECT * FROM `{table}` LIMIT {min(limit, 50)}")
                    rows = cur.fetchall()
                    columns = [desc[0] for desc in cur.description] if cur.description else []
            elif cfg.type == "postgresql":
                cur = conn.cursor()
                qualified = f'"{schema}"."{table}"' if schema else f'"{table}"'
                cur.execute(f"SELECT * FROM {qualified} LIMIT {min(limit, 50)}")
                rows = cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                rows = [dict(zip(columns, row)) for row in rows]
                cur.close()
            else:
                raise ValueError("不支持的数据源类型")
        finally:
            conn.close()
        return {"table": table, "columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Admin / Observability ---

@app.get("/admin/stats")
def admin_stats():
    """Query performance stats and failure tracking."""
    return query_stats.get_stats()


@app.get("/admin/failures")
def admin_failures():
    """List recent failed queries for debugging."""
    return query_stats.get_failed_questions()


@app.get("/admin/export")
def admin_export():
    """Export all system configuration."""
    return export_config()


@app.post("/admin/import")
def admin_import(config: dict):
    """Import system configuration."""
    try:
        with semantic_write_lock:
            result = import_config(config)
            registry.reload()
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/overview")
def admin_overview():
    """System overview dashboard data."""
    entities_count = len(registry.ontology.get("entities", {}))
    metrics_count = len(registry.metrics.get("metrics", {}))
    ds_count = len(datasource_store.list())
    llm_cfg = llm_service.get_config()
    stats = query_stats.get_stats()
    fb = feedback_store.stats()
    return {
        "entities": entities_count,
        "metrics": metrics_count,
        "datasources": ds_count,
        "llm_enabled": llm_cfg.enabled,
        "queries": stats,
        "feedback": fb,
    }


# --- Field Aliases & Enums ---

@app.get("/aliases")
def get_aliases():
    return alias_store.get_all()


@app.put("/aliases")
def set_aliases(aliases: Dict[str, str] = Body()):
    with semantic_write_lock:
        return alias_store.set_aliases(aliases)


@app.delete("/aliases/{alias}")
def delete_alias(alias: str):
    with semantic_write_lock:
        alias_store.delete_alias(alias)
    return {"deleted": alias}


@app.put("/enums/{entity_field}")
def set_enum(entity_field: str, mappings: Dict[str, str] = Body()):
    with semantic_write_lock:
        return alias_store.set_enum(entity_field, mappings)


@app.delete("/enums/{entity_field}")
def delete_enum(entity_field: str):
    with semantic_write_lock:
        alias_store.delete_enum(entity_field)
    return {"deleted": entity_field}


# --- Industry Templates ---

@app.get("/templates")
def list_industry_templates():
    try:
        return template_store.list()
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.post("/templates/validate")
def validate_industry_template(req: object = Body()):
    try:
        try:
            upload = TemplateUploadRequest.model_validate(req)
        except ValidationError as exc:
            errors = [
                {
                    "path": ".".join(str(part) for part in item["loc"]),
                    "message": item["msg"],
                }
                for item in exc.errors()
            ]
            raise TemplateValidationError("上传请求格式无效", errors) from exc
        template = template_store.parse_upload(upload.filename, upload.content)
        existing_ids = {item["id"] for item in template_store.list()}
        return {
            "template": template,
            "counts": {
                "entities": len(template.get("entities", {})),
                "relationships": len(template.get("relationships", [])),
                "metrics": len(template.get("metrics", {})),
                "aliases": len(template.get("aliases", {})),
            },
            "conflict": template["id"] in existing_ids,
        }
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.post("/templates", status_code=201)
def create_industry_template(req: object = Body()):
    try:
        return template_store.create(req)
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.get("/templates/{template_id}")
def get_industry_template(template_id: str):
    try:
        return template_store.get(template_id)
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.put("/templates/{template_id}")
def update_industry_template(template_id: str, req: object = Body()):
    try:
        return template_store.update(template_id, req)
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.delete("/templates/{template_id}")
def delete_industry_template(template_id: str):
    try:
        return template_store.delete(template_id)
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.post("/templates/{template_id}/reset")
def reset_industry_template(template_id: str):
    try:
        return template_store.reset(template_id)
    except TemplateStoreError as exc:
        raise_template_http_error(exc)


@app.get("/templates/{template_id}/apply-preview")
def preview_industry_template_apply(template_id: str):
    try:
        return template_applier.preview(template_store.get(template_id))
    except TemplateStoreError as exc:
        raise_template_http_error(exc)
    except TemplateApplyError as exc:
        raise_template_apply_http_error(exc)


@app.post("/templates/{template_id}/apply")
def apply_industry_template(template_id: str):
    try:
        return template_applier.apply(template_store.get(template_id))
    except TemplateStoreError as exc:
        raise_template_http_error(exc)
    except TemplateApplyError as exc:
        raise_template_apply_http_error(exc)


def raise_template_http_error(exc: TemplateStoreError):
    if isinstance(exc, TemplateNotFoundError):
        status = 404
    elif isinstance(exc, TemplateConflictError):
        status = 409
    elif isinstance(exc, (TemplateValidationError, TemplateOperationError)):
        status = 400
    else:
        status = 500
    raise HTTPException(
        status_code=status,
        detail={
            "message": str(exc),
            "errors": getattr(exc, "errors", []),
        },
    )


def raise_template_apply_http_error(exc: TemplateApplyError):
    raise HTTPException(
        status_code=500,
        detail={"message": str(exc), "errors": []},
    )


# --- Chat History ---

@app.get("/chat/sessions")
def list_sessions():
    """List recent chat sessions."""
    data = session_store._load()
    sessions = []
    for sid, s in sorted(data.items(), key=lambda x: x[1].get("created", 0), reverse=True)[:20]:
        msgs = s.get("messages", [])
        first_q = next((m["content"] for m in msgs if m["role"] == "user"), "")
        sessions.append({"session_id": sid, "created": s.get("created"), "message_count": len(msgs), "preview": first_q[:50]})
    return sessions


# --- Datasource Health ---

@app.get("/datasources/health")
def datasources_health():
    """Check connectivity of all enabled datasources."""
    results = []
    for ds in datasource_store.list():
        if not ds.get("enabled", True):
            results.append({"id": ds["id"], "name": ds["name"], "status": "disabled"})
            continue
        cfg = DataSourceConfig(**ds)
        check = datasource_store.test_connection(cfg)
        results.append({"id": ds["id"], "name": ds["name"], "status": "ok" if check["success"] else "error", "message": check["message"]})
    return results


# --- Audit Log ---

@app.get("/admin/audit")
def get_audit_log(limit: int = 50):
    return audit_log.recent(limit)


@app.get("/admin/audit/stats")
def audit_stats():
    return audit_log.stats()


# --- Cache Management ---

@app.get("/admin/cache")
def cache_stats():
    return query_cache.stats()


@app.post("/admin/cache/clear")
def clear_cache():
    query_cache.clear()
    return {"cleared": True}


# --- JOIN Path Discovery ---

@app.get("/ontology/join-path")
def find_join_path(source: str, target: str):
    """Find JOIN path between two entities."""
    finder = JoinPathFinder(registry.ontology)
    path = finder.find_path(source, target)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No path found from {source} to {target}")
    return {"source": source, "target": target, "path": path, "hops": len(path)}
