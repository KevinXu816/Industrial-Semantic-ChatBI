"""System observability: query stats, failure tracking, accuracy metrics."""
import json
import threading
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
STATS_FILE = ROOT / "data" / "query_stats.json"


class QueryStats:
    def __init__(self):
        self._lock = threading.Lock()
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not STATS_FILE.exists():
            return {"queries": [], "summary": {"total": 0, "success": 0, "failed": 0}}
        try:
            return json.loads(STATS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"queries": [], "summary": {"total": 0, "success": 0, "failed": 0}}

    def _save(self, data: dict):
        STATS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(self, question: str, success: bool, duration_ms: float,
               intent_resolved: bool = True, error: str = ""):
        with self._lock:
            data = self._load()
            entry = {
                "question": question,
                "success": success,
                "duration_ms": round(duration_ms, 1),
                "intent_resolved": intent_resolved,
                "error": error,
                "time": time.time(),
            }
            data["queries"].append(entry)
            # Keep last 500
            if len(data["queries"]) > 500:
                data["queries"] = data["queries"][-500:]
            data["summary"]["total"] += 1
            if success:
                data["summary"]["success"] += 1
            else:
                data["summary"]["failed"] += 1
            self._save(data)

    def get_stats(self) -> dict:
        data = self._load()
        total = data["summary"]["total"]
        success = data["summary"]["success"]
        failed = data["summary"]["failed"]
        queries = data["queries"]
        # Recent performance
        recent = queries[-50:] if queries else []
        avg_duration = sum(q["duration_ms"] for q in recent) / max(len(recent), 1)
        # Failed questions
        failed_questions = [q for q in queries if not q["success"]][-20:]
        return {
            "total_queries": total,
            "success_count": success,
            "failed_count": failed,
            "success_rate": round(success / max(total, 1), 3),
            "avg_duration_ms": round(avg_duration, 1),
            "recent_failures": failed_questions,
        }

    def get_failed_questions(self) -> List[dict]:
        data = self._load()
        return [q for q in data["queries"] if not q["success"]][-50:]
