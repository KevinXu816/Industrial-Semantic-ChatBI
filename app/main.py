from typing import Dict, List
from pathlib import Path
import threading
from fastapi import Body, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import ValidationError
from .models import ChatRequest, ChatResponse, QueryPlan, MetadataScanRequest, MetadataScanResponse, ReviewDecision, MetricDefinition, SemanticCandidate, FeedbackRequest
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

app = FastAPI(title="Industrial Semantic ChatBI Demo", version="0.2.0")
_static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static), name="static")
registry = SemanticRegistry()
planner = QueryPlanner(registry)
rca_engine = RCAEngine()
guardrail = SQLGuardrail()
answer_composer = AnswerComposer()
review_store = ReviewStore()
datasource_store = DataSourceStore()
llm_service = LLMService()
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


@app.get("/")
def root():
    return FileResponse(_static / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0"}


# --- LLM configuration ---

@app.get("/llm/config")
def get_llm_config():
    cfg = llm_service.get_config()
    return {**cfg.model_dump(), "api_key": "***" if cfg.api_key else ""}


@app.put("/llm/config")
def save_llm_config(cfg: LLMConfig):
    return llm_service.save_config(cfg).model_dump()


@app.post("/llm/test")
def test_llm():
    return llm_service.test_connection()


# --- Datasource management ---

@app.get("/datasources")
def list_datasources():
    return datasource_store.list()


@app.post("/datasources")
def create_datasource(cfg: DataSourceConfig):
    return datasource_store.save(cfg)


@app.put("/datasources/{ds_id}")
def update_datasource(ds_id: str, cfg: DataSourceConfig):
    cfg.id = ds_id
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
            return registry.save_entity(name, cfg)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/ontology/entities/{name}")
def delete_entity(name: str):
    try:
        with semantic_write_lock:
            registry.delete_entity(name)
        return {"deleted": name}
    except KeyError:
        raise HTTPException(status_code=404, detail="Entity not found in custom layer")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/ontology/relationships")
def save_relationships(relationships: List[dict] = Body()):
    try:
        with semantic_write_lock:
            return registry.save_relationships(relationships)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/metrics")
def metrics():
    return registry.metrics


@app.post("/metrics")
def create_metric(m: MetricDefinition):
    try:
        with semantic_write_lock:
            return registry.add_metric(m)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/metrics/{name}")
def update_metric(name: str, m: MetricDefinition):
    try:
        with semantic_write_lock:
            return registry.update_metric(name, m)
    except KeyError:
        raise HTTPException(status_code=404, detail="Metric not found")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/metrics/{name}")
def delete_metric(name: str):
    try:
        with semantic_write_lock:
            registry.delete_metric(name)
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
    return {"merged": True, "approved_yaml": yaml_text}


@app.post("/semantic/resolve")
def semantic_resolve(req: ChatRequest):
    try:
        return registry.resolve(req.question)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/plan", response_model=QueryPlan)
def build_plan(req: ChatRequest):
    try:
        intent = registry.resolve(req.question)
        plan = planner.build(intent)
        for sql in plan.sql:
            guardrail.validate(sql)
        return plan
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/chat")
def chat(req: ChatRequest):
    import time as _time
    t0 = _time.time()
    try:
        sid = req.session_id
        if not sid:
            sid = session_store.create_session()
        session_store.add_message(sid, "user", req.question)
        audit_log.log("chat", req.question)

        # Check cache
        cached = query_cache.get(req.question)
        if cached and not req.preview_only:
            cached["session_id"] = sid
            cached["from_cache"] = True
            return cached

        intent = registry.resolve(req.question)

        # Uncertainty: check if key fields were resolved
        confidence = _assess_confidence(intent, req.question)

        plan = planner.build(intent)
        for sql in plan.sql:
            guardrail.validate(sql)

        # JOIN paths are now produced by the semantic planner itself.
        join_paths = plan.join_paths

        if req.preview_only:
            return {"session_id": sid, "intent": intent.model_dump(), "plan": plan.model_dump(),
                    "confidence": confidence, "join_paths": join_paths, "preview": True}

        executor = get_executor()
        data = executor.execute_plan(plan.sql)
        if intent.analysis_mode == "diagnostic":
            data["rca"] = rca_engine.analyze(data)
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
        query_stats.record(req.question, True, (_time.time() - t0) * 1000)
        query_cache.set(req.question, result)
        return result
    except Exception as e:
        query_stats.record(req.question, False, (_time.time() - t0) * 1000, error=str(e))
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
