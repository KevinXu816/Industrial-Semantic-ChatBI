"""V3.1 Enterprise Pilot Pack for air-compressor energy and maintenance validation.

This module intentionally packages an executable customer-POC scenario on top of existing
platform domains. It does not create parallel sources of truth: assets/FMEA/reliability/RCA
are written through their existing domain services, while pilot KPI evidence is stored as
lightweight pilot metadata.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import math


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


AIR_COMPRESSOR_SCENARIO = {
    "scenario_id": "air-compressor-energy-maintenance",
    "name": "空压机能效异常 + 预测维修 Pilot",
    "version": "1.0",
    "business_goal": "验证跨 MES/IoT/CMMS 的语义分析、RCA 与维护决策是否能在客户现场形成可量化价值。",
    "asset": {"asset_id": "A101", "name": "Air Compressor A101", "asset_type": "compressor", "site_id": "F01"},
    "required_sources": ["IoT/Historian", "MES production", "CMMS alarm/work-order"],
    "required_signals": ["active_power", "production_output", "filter_dp", "discharge_temp", "load_pct"],
    "acceptance_kpis": [
        {"kpi": "data_onboarding_days", "target": 5, "comparison": "lte", "unit": "days", "description": "从客户字段到可运行 Pilot 的接入周期"},
        {"kpi": "rca_engineer_acceptance_rate", "target": 0.70, "comparison": "gte", "unit": "ratio", "description": "工程师接受 Top-1 RCA 假设的比例"},
        {"kpi": "rca_evidence_coverage", "target": 0.80, "comparison": "gte", "unit": "ratio", "description": "RCA Case 中具备结构化证据链的比例"},
        {"kpi": "maintenance_lead_time_reduction", "target": 0.20, "comparison": "gte", "unit": "ratio", "description": "平均诊断/维护决策时间降低比例"},
        {"kpi": "specific_energy_improvement", "target": 0.05, "comparison": "gte", "unit": "ratio", "description": "修复后的单位能耗改善比例"},
    ],
}


class PilotPackService:
    META = "pilot_runs"
    KPI = "pilot_kpi_measurements"

    def __init__(self, repo, asset_registry, fmea_store, sensor_mappings, reliability_service, rca_case_store):
        self.repo = repo
        self.assets = asset_registry
        self.fmea = fmea_store
        self.mappings = sensor_mappings
        self.reliability = reliability_service
        self.rca = rca_case_store

    def scenarios(self) -> List[Dict[str, Any]]:
        return [AIR_COMPRESSOR_SCENARIO]

    def get_scenario(self, scenario_id: str) -> Dict[str, Any]:
        if scenario_id != AIR_COMPRESSOR_SCENARIO["scenario_id"]:
            raise KeyError(scenario_id)
        return AIR_COMPRESSOR_SCENARIO

    def bootstrap(self, scenario_id: str, actor: str = "pilot_admin") -> Dict[str, Any]:
        scenario = self.get_scenario(scenario_id)
        # Hierarchy is deliberately small but realistic enough for a customer POC walkthrough.
        self.assets.upsert_asset({"asset_id":"F01","name":"Factory F01","asset_type":"factory","site_id":"F01"}, actor)
        self.assets.upsert_asset({"asset_id":"LINE-01","name":"Compressor Line 01","asset_type":"production_line","parent_asset_id":"F01","site_id":"F01"}, actor)
        self.assets.upsert_asset({**scenario["asset"], "parent_asset_id":"LINE-01"}, actor)
        filter_comp = self.assets.upsert_component("A101", {"name":"Air Filter","component_type":"filter"}, actor)
        self.assets.bind_sensor("A101", {"sensor":"filter_dp","component_id":filter_comp["component_id"],"unit":"kPa","source":"IoT"}, actor)
        self.assets.bind_sensor("A101", {"sensor":"discharge_temp","unit":"degC","source":"IoT"}, actor)
        self.assets.bind_sensor("A101", {"sensor":"active_power","unit":"kW","source":"IoT"}, actor)
        fmea_id = "FMEA-A101-FILTER-001"
        if not self.fmea.get(fmea_id):
            self.fmea.create({
                "fmea_id": fmea_id, "asset":"A101", "site_id":"F01", "component":"Air Filter",
                "failure_mode":"Filter Restriction", "cause_code":"filter_restriction",
                "cause":"Dust/loading increases filter resistance", "effect":"Airflow restriction increases compressor power and specific energy",
                "detection_method":"Filter differential pressure and discharge temperature trend",
                "recommended_action":"Inspect and replace/clean air filter when confirmed",
                "severity":7,"occurrence":6,"detectability":4,"status":"draft",
            }, actor)
            self.fmea.approve(fmea_id, actor)
        self.mappings.upsert({"failure_mode":"filter_restriction","sensor":"filter_dp","weight":2.0,"status":"approved"}, actor)
        self.mappings.upsert({"failure_mode":"filter_restriction","sensor":"discharge_temp","weight":1.2,"status":"approved"}, actor)
        run_id = f"PILOT-{scenario_id}"
        row = {"run_id":run_id,"scenario_id":scenario_id,"status":"bootstrapped","asset_id":"A101","site_id":"F01","updated_at":_now(),"updated_by":actor}
        self.repo.put(self.META, run_id, row)
        return {"scenario":scenario,"pilot":row,"assets":["F01","LINE-01","A101"],"fmea_id":fmea_id}

    @staticmethod
    def synthetic_series(points: int = 96) -> Dict[str, Any]:
        points=max(24,min(int(points),500))
        rows=[]
        for i in range(points):
            progress=i/max(points-1,1)
            degradation=max(0.0,(progress-0.55)/0.45)
            load=72 + 6*math.sin(i/8.0)
            production=100 + 4*math.sin(i/11.0)
            filter_dp=5.5 + 0.5*math.sin(i/6.0) + 8.0*degradation
            discharge_temp=72 + 2*math.sin(i/9.0) + 10*degradation
            active_power=82 + load*0.25 + 18*degradation
            specific_energy=active_power/max(production,1)
            rows.append({"index":i,"load_pct":round(load,2),"production_output":round(production,2),"filter_dp":round(filter_dp,2),"discharge_temp":round(discharge_temp,2),"active_power":round(active_power,2),"specific_energy":round(specific_energy,4)})
        return {"scenario_id":AIR_COMPRESSOR_SCENARIO["scenario_id"],"points":rows,"degradation_starts_near":round(points*0.55)}

    def run_demo(self, actor: str = "pilot_engineer") -> Dict[str, Any]:
        self.bootstrap(AIR_COMPRESSOR_SCENARIO["scenario_id"], actor)
        assessment = self.reliability.assess({
            "asset":"A101", "failure_mode":"filter_restriction",
            "condition_indicators":[
                {"sensor":"filter_dp","score":88},
                {"sensor":"discharge_temp","score":72},
            ],
            "anomaly_score":80, "failure_history_score":55,
        }, actor)
        case = self.rca.create({
            "question":"A101 空压机单位能耗为什么持续升高？",
            "title":"A101 单位能耗异常 Pilot",
            "subject":{"entity":"Machine","reference":"A101"},
            "metrics":["specific_energy_consumption"],"site_id":"F01"
        }, actor)
        top = assessment.get("top_risk") or {}
        analysis={"hypotheses":[{"cause_code":top.get("cause_code"),"cause":top.get("failure_mode"),"confidence":round(float(top.get("dynamic_risk_score",0))/100,2),"evidence":[
            {"type":"metric","statement":"specific_energy_consumption degrades in the pilot scenario","source":"pilot_timeseries","provenance":"pilot:air-compressor-energy-maintenance"},
            {"type":"sensor","statement":"filter_dp risk=88","source":"IoT/Historian","provenance":"sensor:A101:filter_dp"},
            {"type":"sensor","statement":"discharge_temp risk=72","source":"IoT/Historian","provenance":"sensor:A101:discharge_temp"},
            {"type":"fmea","statement":"Approved FMEA supports filter restriction as a governed failure mode","source":"FMEA","provenance":"fmea:FMEA-A101-FILTER-001"},
            {"type":"maintenance","statement":"Inspect and replace/clean air filter when confirmed","source":"FMEA recommended action","provenance":"fmea:FMEA-A101-FILTER-001"}
        ]}]}
        self.rca.attach_analysis(case["case_id"], analysis, actor=actor)
        run_id=f"PILOT-DEMO-{case['case_id']}"
        row={"run_id":run_id,"scenario_id":AIR_COMPRESSOR_SCENARIO["scenario_id"],"status":"analyzed","asset_id":"A101","rca_case_id":case["case_id"],"assessment_id":assessment["assessment_id"],"created_at":_now(),"created_by":actor}
        self.repo.put(self.META,run_id,row)
        return {"pilot_run":row,"assessment":assessment,"rca_case":self.rca.get(case["case_id"]),"next_steps":["engineer_review","maintenance_action","post_repair_kpi_measurement"]}

    def record_kpi(self, payload: Dict[str, Any], actor: str = "pilot_owner") -> Dict[str, Any]:
        kpi=str(payload.get("kpi") or "").strip(); value=payload.get("value")
        if not kpi or value is None: raise ValueError("kpi and value are required")
        target=next((x for x in AIR_COMPRESSOR_SCENARIO["acceptance_kpis"] if x["kpi"]==kpi),None)
        if not target: raise ValueError(f"unsupported pilot kpi: {kpi}")
        value=float(value); met=value <= target["target"] if target["comparison"]=="lte" else value >= target["target"]
        key=f"{kpi}:{_now()}"
        row={"measurement_id":key,"scenario_id":AIR_COMPRESSOR_SCENARIO["scenario_id"],"kpi":kpi,"value":value,"target":target["target"],"comparison":target["comparison"],"unit":target["unit"],"met":met,"measured_at":_now(),"measured_by":actor,"evidence":payload.get("evidence",{})}
        return self.repo.put(self.KPI,key,row)

    def kpis(self) -> Dict[str, Any]:
        measurements=self.repo.list(self.KPI,limit=1000)
        latest={}
        for r in measurements:
            latest.setdefault(r.get("kpi"),r)
        targets=[]
        for t in AIR_COMPRESSOR_SCENARIO["acceptance_kpis"]:
            targets.append({**t,"latest":latest.get(t["kpi"])})
        measured=[x for x in targets if x["latest"]]
        return {"scenario_id":AIR_COMPRESSOR_SCENARIO["scenario_id"],"targets":targets,"measured":len(measured),"met":sum(1 for x in measured if x["latest"].get("met")),"pilot_go": bool(measured) and all(x["latest"].get("met") for x in measured)}

    def readiness(self) -> Dict[str, Any]:
        asset=bool(self.assets.get_asset("A101")); fmea=bool(self.fmea.get("FMEA-A101-FILTER-001"))
        kpis=self.kpis()
        checks={"scenario_bootstrapped":asset and fmea,"asset_master":asset,"approved_fmea":bool(fmea and self.fmea.get("FMEA-A101-FILTER-001").get("status")=="approved"),"kpi_framework":len(kpis["targets"])>=5}
        return {"status":"ready" if all(checks.values()) else "not_ready","checks":checks,"kpis":kpis}
