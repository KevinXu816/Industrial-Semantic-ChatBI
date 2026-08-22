import json
import threading
from pathlib import Path
from typing import Dict, List
import yaml
from .models import SemanticCandidate, ReviewDecision

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "semantic_reviews.json"
APPROVED = ROOT / "config" / "approved_semantic.yaml"


class ReviewStore:
    def __init__(self):
        self._lock = threading.Lock()
        STORE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, dict]:
        if not STORE.exists():
            return {}
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def list(self) -> Dict[str, dict]:
        return self._load()

    def save_candidates(self, candidates: List[SemanticCandidate]) -> None:
        with self._lock:
            data = self._load()
            for candidate in candidates:
                existing = data.get(candidate.id, {})
                payload = candidate.model_dump()
                if existing.get("status") in {"approved", "rejected"}:
                    payload["status"] = existing["status"]
                    payload["review_note"] = existing.get("review_note")
                data[candidate.id] = payload
            STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def review(self, candidate_id: str, decision: ReviewDecision) -> dict:
        with self._lock:
            data = self._load()
            if candidate_id not in data:
                raise KeyError(candidate_id)
            data[candidate_id]["status"] = decision.status
            data[candidate_id]["review_note"] = decision.note
            STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data[candidate_id]

    def build_approved_ontology(self) -> dict:
        """Build ontology fragment from all approved candidates."""
        data = self._load()
        entities: Dict[str, dict] = {}
        relationships = []

        for cid, c in data.items():
            if c.get("status") != "approved":
                continue
            entity_name = c["entity"]
            pm = c["physical_mapping"]
            columns = {}
            props = {}
            for p in c.get("properties", []):
                props[p["logical_name"]] = {"type": p["data_type"]}
                columns[p["logical_name"]] = p["physical_column"]

            entry = {
                "description": c.get("description", ""),
                "source_candidate": cid,
                "identifiers": [p["logical_name"] for p in c.get("properties", [])
                                if p["logical_name"] in ("machine_id", "alarm_id", "work_order_id")],
                "properties": props,
                "physical_mapping": {
                    "catalog": pm.get("catalog", ""),
                    "schema": pm.get("schema", ""),
                    "table": pm.get("table", ""),
                    "columns": columns,
                },
            }
            # If multiple tables map to the same entity, keep higher confidence
            if entity_name in entities:
                existing_cid = entities[entity_name].get("source_candidate", "")
                existing_conf = data.get(existing_cid, {}).get("confidence", 0)
                if c.get("confidence", 0) <= existing_conf:
                    continue
            entities[entity_name] = entry

            for rel in c.get("relationships", []):
                relationships.append({
                    "from": rel["from_entity"],
                    "relation": rel["relation"],
                    "to": rel["to_entity"],
                    "on": rel["on"],
                })

        return {"entities": entities, "relationships": relationships}

    def get_approved_metrics(self) -> dict:
        """Collect metrics from all approved candidates."""
        data = self._load()
        metrics = {}
        for cid, c in data.items():
            if c.get("status") != "approved":
                continue
            for m in c.get("metrics", []):
                if m["name"] not in metrics:
                    entry = {"description": f"Auto-discovered from {cid}", "expression": m["expression"]}
                    if m.get("unit"):
                        entry["unit"] = m["unit"]
                    entry["entity"] = c.get("entity", "")
                    metrics[m["name"]] = entry
        return metrics

    def export_approved_yaml(self) -> str:
        """Write approved ontology to config/approved_semantic.yaml and return it."""
        fragment = self.build_approved_ontology()
        APPROVED.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.dump(fragment, allow_unicode=True, default_flow_style=False, sort_keys=False)
        APPROVED.write_text(text, encoding="utf-8")
        return text
