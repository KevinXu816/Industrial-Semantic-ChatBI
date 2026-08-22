"""Human RCA review/feedback loop with append-only local persistence."""
from __future__ import annotations
import json, threading, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "rca_feedback.json"

class RCAFeedbackStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DEFAULT_PATH; self.lock = threading.RLock()
    def _load(self):
        if not self.path.exists(): return []
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return []
    def add(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        rec = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **payload}
        with self.lock:
            rows = self._load(); rows.append(rec); self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        return rec
    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(reversed(self._load()))[:max(1, min(limit, 500))]
