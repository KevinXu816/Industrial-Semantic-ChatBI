"""V1.6 condition analytics: governed indicator definitions, feature extraction and baselines.

The engine turns raw time-series values into transparent condition indicators that can be
consumed directly by the V1.5 reliability risk model. It intentionally uses deterministic,
auditable statistics instead of opaque predictive claims.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from statistics import mean, pstdev
from typing import Any, Dict, List, Optional
import hashlib

from .persistence import Repository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(v)))


def _nums(values: List[Any]) -> List[float]:
    out=[]
    for v in values or []:
        try: out.append(float(v))
        except (TypeError, ValueError): pass
    return out


class ConditionIndicatorDefinitionStore:
    COLLECTION = "condition_indicator_definitions"
    VALID_FEATURES = {"mean", "std", "min", "max", "range", "rms", "slope", "kurtosis", "crest_factor"}

    def __init__(self, repository: Repository):
        self.repo = repository

    def upsert(self, payload: Dict[str, Any], actor: str = "reliability_engineer") -> Dict[str, Any]:
        name = str(payload.get("indicator") or payload.get("name") or "").strip()
        sensor = str(payload.get("sensor") or "").strip()
        feature = str(payload.get("feature") or "mean").strip().lower()
        if not name or not sensor:
            raise ValueError("indicator/name and sensor are required")
        if feature not in self.VALID_FEATURES:
            raise ValueError(f"unsupported feature: {feature}")
        key = str(payload.get("definition_id") or hashlib.sha1(f"{sensor}:{name}:{feature}".encode()).hexdigest()[:16])
        row = dict(payload)
        row.update({"definition_id": key, "indicator": name, "sensor": sensor, "feature": feature,
                    "updated_at": _now(), "updated_by": actor})
        row.setdefault("status", "approved")
        row.setdefault("window_points", 0)
        row.setdefault("direction", "high")
        row.setdefault("weight", 1.0)
        return self.repo.put(self.COLLECTION, key, row)

    def get(self, definition_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get(self.COLLECTION, definition_id)

    def list(self, sensor: str = "", status: str = "approved", limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.COLLECTION, limit=min(max(limit * 3, 500), 2000))
        return [r for r in rows if (not sensor or r.get("sensor") == sensor) and (not status or r.get("status") == status)][:limit]


class ConditionBaselineStore:
    COLLECTION = "condition_baselines"

    def __init__(self, repository: Repository):
        self.repo = repository

    def upsert(self, asset: str, indicator: str, values: List[Any], actor: str = "reliability_engineer", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        xs = _nums(values)
        if not asset or not indicator or len(xs) < 2:
            raise ValueError("asset, indicator and at least two numeric baseline values are required")
        mu = mean(xs); sd = pstdev(xs)
        key = hashlib.sha1(f"{asset}:{indicator}".encode()).hexdigest()[:20]
        row = {"baseline_id": key, "asset": asset, "indicator": indicator, "count": len(xs),
               "mean": round(mu, 6), "std": round(sd, 6), "min": min(xs), "max": max(xs),
               "updated_at": _now(), "updated_by": actor, "metadata": metadata or {}}
        return self.repo.put(self.COLLECTION, key, row)

    def get(self, asset: str, indicator: str) -> Optional[Dict[str, Any]]:
        key = hashlib.sha1(f"{asset}:{indicator}".encode()).hexdigest()[:20]
        return self.repo.get(self.COLLECTION, key)

    def list(self, asset: str = "", limit: int = 500) -> List[Dict[str, Any]]:
        rows = self.repo.list(self.COLLECTION, limit=min(max(limit * 2, 500), 2000))
        return [r for r in rows if not asset or r.get("asset") == asset][:limit]


class TimeSeriesFeatureEngine:
    @staticmethod
    def features(values: List[Any]) -> Dict[str, float]:
        xs = _nums(values)
        if not xs:
            raise ValueError("time series contains no numeric values")
        n = len(xs); mu = mean(xs); sd = pstdev(xs) if n > 1 else 0.0
        rms = sqrt(sum(x*x for x in xs) / n)
        denom = sum((i - (n-1)/2.0) ** 2 for i in range(n))
        slope = 0.0 if not denom else sum((i-(n-1)/2.0)*(x-mu) for i,x in enumerate(xs)) / denom
        kurt = 0.0
        if sd > 1e-12:
            kurt = sum(((x-mu)/sd) ** 4 for x in xs) / n
        crest = max(abs(x) for x in xs) / rms if rms > 1e-12 else 0.0
        return {"mean": mu, "std": sd, "min": min(xs), "max": max(xs), "range": max(xs)-min(xs),
                "rms": rms, "slope": slope, "kurtosis": kurt, "crest_factor": crest}

    @staticmethod
    def rolling(values: List[Any], window: int, feature: str = "mean") -> List[float]:
        xs = _nums(values)
        if window <= 0: window = len(xs)
        if window <= 0 or not xs: return []
        out=[]
        for i in range(window-1, len(xs)):
            out.append(float(TimeSeriesFeatureEngine.features(xs[i-window+1:i+1])[feature]))
        return out


class ConditionAnalyticsService:
    def __init__(self, definitions: ConditionIndicatorDefinitionStore, baselines: ConditionBaselineStore):
        self.definitions, self.baselines = definitions, baselines

    @staticmethod
    def _risk_from_threshold(value: float, definition: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> float:
        direction = str(definition.get("direction", "high")).lower()
        warn, critical = definition.get("warn"), definition.get("critical")
        if warn is not None and critical is not None:
            warn=float(warn); critical=float(critical)
            if direction == "low":
                if value >= warn: return 0.0
                if value <= critical: return 100.0
                return _clamp((warn-value)/max(warn-critical,1e-9)*100.0)
            if value <= warn: return 0.0
            if value >= critical: return 100.0
            return _clamp((value-warn)/max(critical-warn,1e-9)*100.0)
        if baseline:
            mu=float(baseline.get("mean",0.0)); sd=float(baseline.get("std",0.0))
            tolerance=float(definition.get("baseline_sigma",3.0) or 3.0) * max(sd, abs(mu)*0.02, 1e-9)
            deviation = (mu-value) if direction == "low" else (value-mu)
            return _clamp(max(0.0, deviation) / tolerance * 100.0)
        return 0.0

    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        asset = str(payload.get("asset") or "").strip()
        series = payload.get("series") or {}
        if not isinstance(series, dict) or not series:
            raise ValueError("series must be a mapping of sensor name to numeric values")
        requested = set(payload.get("definition_ids") or [])
        definitions = self.definitions.list(status="approved", limit=1000)
        if requested:
            definitions = [d for d in definitions if d.get("definition_id") in requested]
        indicators=[]
        for d in definitions:
            sensor=str(d.get("sensor")); values=_nums(series.get(sensor) or [])
            if not values: continue
            window=int(d.get("window_points",0) or 0)
            window_values=values[-window:] if window > 0 else values
            fs=TimeSeriesFeatureEngine.features(window_values)
            feature=str(d.get("feature","mean")); value=float(fs[feature])
            baseline=self.baselines.get(asset, str(d.get("indicator"))) if asset else None
            risk=self._risk_from_threshold(value,d,baseline)
            indicators.append({"definition_id":d.get("definition_id"),"sensor":sensor,"indicator":d.get("indicator"),
                               "feature":feature,"value":round(value,6),"score":round(risk,2),"weight":float(d.get("weight",1.0)),
                               "unit":d.get("unit"),"window_points":len(window_values),"baseline":baseline,"features":{k:round(v,6) for k,v in fs.items()}})
        return {"asset":asset,"condition_indicators":indicators,"generated_at":_now(),
                "semantics":"Deterministic condition indicators derived from governed feature definitions and baselines."}
