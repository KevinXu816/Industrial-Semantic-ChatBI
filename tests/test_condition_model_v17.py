from pathlib import Path
import tempfile
from app.persistence import JsonRepository
from app.condition_models import ConditionModelTemplateStore
from app.condition_analytics import ConditionIndicatorDefinitionStore, ConditionBaselineStore, ConditionAnalyticsService
from app.feature_pipeline import FeaturePipelineStore
from app.model_registry import PredictiveModelRegistry


def repo():
    return JsonRepository(Path(tempfile.mkdtemp()))

def test_builtin_templates_and_apply():
    r=repo(); t=ConditionModelTemplateStore(r); t.bootstrap(); defs=ConditionIndicatorDefinitionStore(r)
    assert t.get("bearing")["asset_type"] == "bearing"
    out=t.apply("bearing",defs)
    assert out["count"] >= 4
    assert any(x["indicator"]=="vibration_rms" for x in defs.list())

def test_feature_pipeline_executes_condition_contract():
    r=repo(); defs=ConditionIndicatorDefinitionStore(r); bases=ConditionBaselineStore(r); svc=ConditionAnalyticsService(defs,bases)
    d=defs.upsert({"indicator":"temp_mean","sensor":"temp","feature":"mean","warn":60,"critical":80})
    p=FeaturePipelineStore(r); job=p.upsert({"name":"bearing-hourly","definition_ids":[d["definition_id"]]})
    run=p.execute(job["pipeline_id"],{"asset":"A1","series":{"temp":[60,70,80]}},svc)
    assert run["status"]=="succeeded"
    assert run["result"]["condition_indicators"][0]["indicator"]=="temp_mean"

def test_model_registry_requires_approval_and_is_versioned():
    r=repo(); mr=PredictiveModelRegistry(r)
    m=mr.register({"name":"temp-risk","version":"1.0","model_type":"rule","parameters":{"field":"temp","warn":60,"critical":80}})
    try:
        mr.infer(m["model_id"],{"inputs":{"temp":70}})
        assert False
    except ValueError:
        pass
    mr.approve(m["model_id"])
    out=mr.infer(m["model_id"],{"inputs":{"temp":70}})
    assert out["inference"]["model_version"]=="1.0"
    assert 49 <= out["inference"]["output"]["risk_score"] <= 51

def test_external_model_is_governed_adapter_contract():
    r=repo(); mr=PredictiveModelRegistry(r)
    m=mr.register({"name":"bearing-rul","version":"2.0","model_type":"onnx","artifact_uri":"models/bearing-rul.onnx"})
    mr.approve(m["model_id"])
    out=mr.infer(m["model_id"],{"inputs":{"values":[1,2,3]}})
    assert out["inference"]["output"]["status"]=="adapter_required"
