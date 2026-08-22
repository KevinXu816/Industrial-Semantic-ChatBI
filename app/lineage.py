"""Semantic version snapshots and query lineage for V0.7."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "data" / "semantic_versions.json"
LINEAGE_FILE = ROOT / "data" / "query_lineage.json"
SNAPSHOT_DIR = ROOT / "data" / "semantic_snapshots"


class SemanticVersionStore:
    def __init__(self, path: Path = VERSION_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
        except Exception:
            return []

    def snapshot(self, registry, action: str, actor: str = "system", detail: str = "") -> Dict[str, Any]:
        payload = {"ontology": registry.ontology, "metrics": registry.metrics}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self._lock:
            versions = self._load()
            if versions and versions[-1].get("digest") == digest:
                return versions[-1]
            SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
            snapshot_path = SNAPSHOT_DIR / f"{digest}.json"
            if not snapshot_path.exists():
                snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            entry = {
                "version": len(versions) + 1,
                "digest": digest,
                "action": action,
                "actor": actor,
                "detail": detail[:500],
                "created_at": time.time(),
                "entity_count": len(registry.ontology.get("entities", {})),
                "metric_count": len(registry.metrics.get("metrics", {})),
                "snapshot_file": str(snapshot_path.relative_to(ROOT)),
            }
            versions.append(entry)
            self.path.write_text(json.dumps(versions[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
            return entry

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._load()[-max(1, min(limit, 200)):][::-1]

    def latest(self) -> Optional[Dict[str, Any]]:
        data = self._load()
        return data[-1] if data else None


class QueryLineageStore:
    def __init__(self, path: Path = LINEAGE_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list:
        try:
            return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else []
        except Exception:
            return []

    def record(self, plan, governance: Optional[Dict[str, Any]] = None, user: str = "anonymous") -> Dict[str, Any]:
        record = {
            "id": hashlib.sha1(f"{time.time_ns()}:{user}".encode()).hexdigest()[:16],
            "time": time.time(),
            "user": user,
            "subject": plan.subject_entity,
            "metrics": list(plan.intent.metrics),
            "dimensions": list(plan.intent.dimensions),
            "entities": list(plan.required_entities),
            "metric_dependencies": list(plan.metric_dependencies),
            "join_paths": plan.join_paths,
            "tables": plan.physical_plan.get("tables", []),
            "catalogs": plan.physical_plan.get("catalogs", []),
            "sql_count": len(plan.sql),
            "governance": governance or {},
        }
        with self._lock:
            data = self._load()
            data.append(record)
            self.path.write_text(json.dumps(data[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._load()[-max(1, min(limit, 200)):][::-1]
