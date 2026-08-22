from app.persistence import JsonRepository
from app.data_binding import DataBindingStore
from app.integration_runtime import IntegrationRuntimeService
from app.asset_reliability import AssetRegistry
from app.predictive_maintenance import CMMSWorkOrderCandidateStore


def build(tmp_path):
    repo=JsonRepository(tmp_path)
    bindings=DataBindingStore(repo)
    runtime=IntegrationRuntimeService(repo,bindings)
    assets=AssetRegistry(repo)
    cmms=CMMSWorkOrderCandidateStore(repo)
    b=bindings.upsert({"name":"asset-sync","target":"asset","source_type":"mysql","mappings":{"asset_id":"id","name":"name"}})
    bindings.approve(b["binding_id"])
    return repo,bindings,runtime,assets,cmms,b


def test_watermark_quality_dlq_and_schema(tmp_path):
    repo, bindings, runtime, assets, cmms, b=build(tmp_path)
    bid=b["binding_id"]
    runtime.configure(bid,{"watermark_field":"ts","schema_policy":"block"})
    runtime.add_quality_rule(bid,{"rule_type":"not_null","field":"id"})
    services={"asset_registry":assets,"cmms_candidates":cmms}
    rows=[{"id":"A1","name":"Pump","ts":"2026-08-22T10:00:00Z"},{"id":"","name":"Bad","ts":"2026-08-22T10:01:00Z"}]
    out=runtime.execute(bid,rows,services)
    assert out["succeeded"]==1
    assert out["quality_rejected"]==1
    assert runtime.state(bid)["watermark"]=="2026-08-22T10:00:00Z"
    assert len(runtime.dead_letters(status="open"))==1
    # Watermark filters already-consumed rows.
    out2=runtime.execute(bid,[{"id":"A0","name":"Old","ts":"2026-08-22T09:00:00Z"}],services)
    assert out2["incremental_received"]==0
    # New field changes schema and is blocked until accepted.
    try:
        runtime.execute(bid,[{"id":"A2","name":"Pump2","ts":"2026-08-22T11:00:00Z","new_col":1}],services)
        assert False, "schema drift should block"
    except ValueError as exc:
        assert "schema drift" in str(exc)
    accepted=runtime.accept_schema(bid,[{"id":"A2","name":"Pump2","ts":"2026-08-22T11:00:00Z","new_col":1}])
    assert accepted["accepted"] is True


def test_monitoring_contract(tmp_path):
    repo, bindings, runtime, assets, cmms, b=build(tmp_path)
    runtime.configure(b["binding_id"],{"schedule":"*/5 * * * *","watermark_field":"ts","max_retries":2})
    m=runtime.monitoring()
    assert m["bindings"]==1
    assert m["with_watermark"]==1
