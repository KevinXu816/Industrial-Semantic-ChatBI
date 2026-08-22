"""V1.7 governed condition-model templates for common industrial asset classes."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import hashlib
from .persistence import Repository


def _now(): return datetime.now(timezone.utc).isoformat()

BUILTIN_TEMPLATES = {
    "bearing": {
        "asset_type":"bearing","recommended_sensors":["vibration","bearing_temp"],
        "indicators":[
            {"indicator":"vibration_rms","sensor":"vibration","feature":"rms","weight":2.0},
            {"indicator":"vibration_kurtosis","sensor":"vibration","feature":"kurtosis","weight":1.5},
            {"indicator":"vibration_crest_factor","sensor":"vibration","feature":"crest_factor","weight":1.2},
            {"indicator":"bearing_temp_mean","sensor":"bearing_temp","feature":"mean","weight":1.5},
        ]},
    "pump": {"asset_type":"pump","recommended_sensors":["vibration","motor_current","suction_pressure","discharge_pressure"],"indicators":[
        {"indicator":"pump_vibration_rms","sensor":"vibration","feature":"rms"},{"indicator":"motor_current_rms","sensor":"motor_current","feature":"rms"},{"indicator":"suction_pressure_mean","sensor":"suction_pressure","feature":"mean"},{"indicator":"discharge_pressure_mean","sensor":"discharge_pressure","feature":"mean"}]},
    "compressor": {"asset_type":"compressor","recommended_sensors":["discharge_temp","filter_dp","active_power","vibration"],"indicators":[
        {"indicator":"discharge_temp_mean","sensor":"discharge_temp","feature":"mean"},{"indicator":"filter_dp_mean","sensor":"filter_dp","feature":"mean","weight":1.8},{"indicator":"active_power_mean","sensor":"active_power","feature":"mean"},{"indicator":"compressor_vibration_rms","sensor":"vibration","feature":"rms"}]},
    "motor": {"asset_type":"motor","recommended_sensors":["motor_current","motor_temp","vibration"],"indicators":[
        {"indicator":"motor_current_rms","sensor":"motor_current","feature":"rms"},{"indicator":"motor_temp_mean","sensor":"motor_temp","feature":"mean"},{"indicator":"motor_vibration_rms","sensor":"vibration","feature":"rms"}]},
    "fan": {"asset_type":"fan","recommended_sensors":["vibration","motor_current","airflow"],"indicators":[
        {"indicator":"fan_vibration_rms","sensor":"vibration","feature":"rms"},{"indicator":"fan_current_rms","sensor":"motor_current","feature":"rms"},{"indicator":"airflow_mean","sensor":"airflow","feature":"mean","direction":"low"}]},
    "pcs": {"asset_type":"pcs","recommended_sensors":["active_power","reactive_power","dc_voltage","temperature"],"indicators":[
        {"indicator":"pcs_active_power_rms","sensor":"active_power","feature":"rms"},{"indicator":"pcs_reactive_power_rms","sensor":"reactive_power","feature":"rms"},{"indicator":"pcs_dc_voltage_std","sensor":"dc_voltage","feature":"std"},{"indicator":"pcs_temp_mean","sensor":"temperature","feature":"mean"}]},
    "battery": {"asset_type":"battery","recommended_sensors":["cell_voltage","cell_temperature","soc"],"indicators":[
        {"indicator":"cell_voltage_range","sensor":"cell_voltage","feature":"range","weight":2.0},{"indicator":"cell_temp_range","sensor":"cell_temperature","feature":"range","weight":2.0},{"indicator":"soc_slope","sensor":"soc","feature":"slope"}]},
}

class ConditionModelTemplateStore:
    COLLECTION="condition_model_templates"
    def __init__(self, repository:Repository): self.repo=repository
    def bootstrap(self):
        for key,payload in BUILTIN_TEMPLATES.items():
            if not self.repo.get(self.COLLECTION,key):
                row={**payload,"template_id":key,"name":key.title(),"version":"1.0","status":"approved","source":"builtin","updated_at":_now()}
                self.repo.put(self.COLLECTION,key,row)
    def upsert(self,payload:Dict[str,Any],actor="reliability_engineer"):
        key=str(payload.get("template_id") or payload.get("asset_type") or "").strip().lower()
        if not key: raise ValueError("template_id or asset_type is required")
        indicators=payload.get("indicators") or []
        if not isinstance(indicators,list) or not indicators: raise ValueError("indicators are required")
        row=dict(payload); row.update({"template_id":key,"asset_type":str(payload.get("asset_type") or key),"updated_by":actor,"updated_at":_now()}); row.setdefault("version","1.0"); row.setdefault("status","approved")
        return self.repo.put(self.COLLECTION,key,row)
    def get(self,key): return self.repo.get(self.COLLECTION,key)
    def list(self,status="approved",limit=100):
        rows=self.repo.list(self.COLLECTION,limit=limit)
        return [x for x in rows if not status or x.get("status")==status]
    def apply(self,template_id:str, definition_store, actor="template"):
        t=self.get(template_id)
        if not t: raise KeyError(template_id)
        created=[]
        for spec in t.get("indicators") or []:
            created.append(definition_store.upsert({**spec,"source_template":template_id,"status":"approved"},actor=actor))
        return {"template_id":template_id,"definitions":created,"count":len(created)}
