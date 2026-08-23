"""V3.2 customer-pilot delivery services.

This module converts the V3.1 demo scenario into a repeatable customer onboarding and
acceptance workflow. It intentionally reuses DataBinding/IntegrationRuntime/RCA domain
services instead of introducing another integration or evidence source of truth.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


BINDING_BLUEPRINTS = [
    {
        "key": "asset_master", "name": "Pilot MES Asset Master", "source_type": "mysql", "target": "asset",
        "mappings": {"asset_id": "asset_id", "name": "asset_name", "asset_type": "asset_type", "parent_asset_id": "parent_asset_id"},
        "purpose": "MES/CMMS equipment master → governed Asset Registry",
    },
    {
        "key": "iot_condition_series", "name": "Pilot IoT Condition Series", "source_type": "influxdb", "target": "condition_series",
        "mappings": {"asset_id": "asset_id", "sensor": "sensor", "value": "value", "timestamp": "timestamp"},
        "purpose": "Normalized IoT/Historian tall-series contract for power/filter DP/temperature/load",
    },
    {
        "key": "mes_production_series", "name": "Pilot MES Production Series", "source_type": "mysql", "target": "condition_series",
        "mappings": {"asset_id": "asset_id", "sensor": "$literal:production_output", "value": "production_output", "timestamp": "timestamp"},
        "purpose": "MES production output → normalized condition-series semantic contract",
    },
    {
        "key": "cmms_alarm", "name": "Pilot CMMS Alarm", "source_type": "api", "target": "alarm",
        "mappings": {"asset_id": "asset_id", "alarm": "alarm", "severity": "severity", "timestamp": "timestamp", "status": "status"},
        "purpose": "CMMS/alarm events for RCA evidence",
    },
    {
        "key": "cmms_work_order", "name": "Pilot CMMS Work Order", "source_type": "api", "target": "work_order",
        "mappings": {"asset_id": "asset_id", "component": "component", "failure_mode": "failure_mode", "priority": "priority", "recommended_action": "recommended_action"},
        "purpose": "CMMS work-order history/action contract",
    },
]


class PilotDeliveryService:
    META = "pilot_delivery"

    def __init__(self, repo, data_bindings, integration_runtime, rca_cases):
        self.repo = repo
        self.bindings = data_bindings
        self.runtime = integration_runtime
        self.rca = rca_cases

    def data_contract(self) -> Dict[str, Any]:
        return {
            "contract_version": "3.3",
            "scenario": "air-compressor-energy-maintenance",
            "recommended_shape": "Normalize time-series to asset_id/sensor/value/timestamp before platform ingestion.",
            "required_signals": ["active_power", "production_output", "filter_dp", "discharge_temp", "load_pct"],
            "recommended_history": {"minimum_days": 30, "preferred_days": 90, "sampling": "1-5 min for process/energy; event timestamp for CMMS"},
            "bindings": BINDING_BLUEPRINTS,
            "security": "Credentials belong in Secret References/Edge Adapters and must not be embedded in mapping payloads.",
        }

    def prepare_bindings(self, payload: Dict[str, Any] | None = None, actor: str = "pilot_data_engineer") -> Dict[str, Any]:
        payload = payload or {}
        overrides = payload.get("mapping_overrides") or {}
        scope = {"tenant_id": payload.get("tenant_id", "default"), "org_id": payload.get("org_id", ""), "site_id": payload.get("site_id", "F01")}
        created=[]
        for bp in BINDING_BLUEPRINTS:
            mappings = dict(bp["mappings"]); mappings.update(overrides.get(bp["key"], {}) or {})
            row = self.bindings.upsert({"name":bp["name"],"source_type":bp["source_type"],"source_id":bp["key"],"target":bp["target"],"mappings":mappings,"description":bp["purpose"],**scope}, actor=actor)
            created.append(row)
        key="air-compressor-energy-maintenance"
        self.repo.put(self.META,key,{"scenario_id":key,"bindings":[x["binding_id"] for x in created],"prepared_at":_now(),"prepared_by":actor,**scope})
        return {"scenario_id":key,"bindings":created,"next_step":"Preview customer records, approve mappings, then configure schema/watermark/quality rules before runtime execution."}

    def onboarding_status(self) -> Dict[str, Any]:
        rows=self.bindings.list(limit=1000)
        by_source={str(x.get("source_id")):x for x in rows}
        items=[]
        for bp in BINDING_BLUEPRINTS:
            row=by_source.get(bp["key"])
            state={}
            if row:
                try: state=self.runtime.state(row["binding_id"])
                except Exception: state={}
            items.append({"key":bp["key"],"required":True,"binding_id":row.get("binding_id") if row else None,"status":row.get("status") if row else "missing","schema_baselined":bool(state.get("schema_fingerprint")),"watermark_configured":bool(state.get("watermark_field")),"quality_rules":len(self.runtime.quality_rules(row["binding_id"])) if row else 0})
        approved=sum(1 for x in items if x["status"]=="approved")
        return {"required":len(items),"configured":sum(1 for x in items if x["binding_id"]),"approved":approved,"ready_for_customer_data":approved==len(items),"items":items}

    @staticmethod
    def evidence_quality(case: Dict[str, Any] | None) -> Dict[str, Any]:
        case=case or {}; hyps=case.get("hypotheses") or []
        ev=[]
        for h in hyps:
            for item in h.get("evidence") or []:
                if isinstance(item,dict): ev.append(item)
                else: ev.append({"type":"unclassified","statement":str(item)})
        categories={str(x.get("type") or "unclassified") for x in ev}
        desired={"metric","sensor","fmea","maintenance"}
        coverage=len(categories & desired)/len(desired)
        provenance=sum(1 for x in ev if x.get("provenance") or x.get("source"))/max(len(ev),1)
        return {"evidence_count":len(ev),"categories":sorted(categories),"category_coverage":round(coverage,3),"provenance_coverage":round(provenance,3),"quality_pass":coverage>=0.75 and provenance>=0.75}

    def latest_rca_quality(self) -> Dict[str, Any]:
        rows=self.rca.list(limit=200)
        pilot=[x for x in rows if str(x.get("title") or "").startswith("A101 单位能耗异常 Pilot")]
        if not pilot: return {"status":"not_measured",**self.evidence_quality(None)}
        pilot.sort(key=lambda x:x.get("updated_at") or x.get("created_at") or "", reverse=True)
        return {"status":"measured","case_id":pilot[0].get("case_id"),**self.evidence_quality(pilot[0])}
    def report(self, pilot_readiness: Dict[str, Any], kpis: Dict[str, Any]) -> Dict[str, Any]:
        onboarding=self.onboarding_status(); evidence=self.latest_rca_quality()
        blockers=[]
        if pilot_readiness.get("status") != "ready": blockers.append("pilot scenario is not bootstrapped")
        if not onboarding.get("ready_for_customer_data"): blockers.append("customer data bindings are not fully approved")
        if evidence.get("status") == "measured" and not evidence.get("quality_pass"): blockers.append("RCA evidence quality is below the pilot gate")
        missing=[x["kpi"] for x in kpis.get("targets",[]) if not x.get("latest")]
        if missing: blockers.append("business KPI measurements are incomplete")
        decision="GO" if kpis.get("pilot_go") and not blockers else "NO_GO"
        return {
            "report_version":"3.3", "scenario_id":"air-compressor-energy-maintenance", "generated_at":_now(),
            "decision":decision, "pilot_go":decision=="GO", "blockers":blockers,
            "readiness":pilot_readiness, "data_onboarding":onboarding, "rca_evidence_quality":evidence, "business_kpis":kpis,
            "acceptance_rule":"GO requires technical readiness, approved customer-data bindings, acceptable RCA evidence when measured, and all five business KPI measurements meeting target.",
        }

    def report_markdown(self, pilot_readiness: Dict[str, Any], kpis: Dict[str, Any]) -> str:
        r=self.report(pilot_readiness,kpis)
        lines=["# Enterprise Pilot Acceptance Report", "", f"- Scenario: `{r['scenario_id']}`", f"- Generated: {r['generated_at']}", f"- Decision: **{r['decision']}**", "", "## Technical readiness", f"- Pilot readiness: {r['readiness'].get('status')}", f"- Data bindings approved: {r['data_onboarding'].get('approved')}/{r['data_onboarding'].get('required')}", f"- RCA evidence quality: {r['rca_evidence_quality'].get('quality_pass')}", "", "## Business KPI"]
        for x in kpis.get("targets",[]):
            latest=x.get("latest") or {}; value=latest.get("value","not measured"); met=latest.get("met")
            lines.append(f"- {x['kpi']}: {value} (target {x['comparison']} {x['target']} {x['unit']}) — {'PASS' if met else 'PENDING/FAIL'}")
        if r['blockers']:
            lines += ["", "## Blockers"] + [f"- {b}" for b in r['blockers']]
        return "\n".join(lines)+"\n"

