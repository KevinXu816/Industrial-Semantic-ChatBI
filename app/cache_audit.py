"""Query cache and audit log."""
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
CACHE_FILE = ROOT / "data" / "query_cache.json"
AUDIT_FILE = ROOT / "data" / "audit_log.json"


class QueryCache:
    """Simple file-based query cache with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        self._lock = threading.Lock()
        self.ttl = ttl_seconds
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _key(self, question: str) -> str:
        return hashlib.md5(question.strip().lower().encode()).hexdigest()

    def _load(self) -> dict:
        if not CACHE_FILE.exists():
            return {}
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict):
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def get(self, question: str) -> Optional[dict]:
        key = self._key(question)
        data = self._load()
        entry = data.get(key)
        if not entry:
            return None
        if time.time() - entry.get("time", 0) > self.ttl:
            return None
        return entry.get("response")

    def set(self, question: str, response: dict):
        with self._lock:
            data = self._load()
            key = self._key(question)
            data[key] = {"question": question, "response": response, "time": time.time()}
            # Evict old entries (keep max 100)
            if len(data) > 100:
                sorted_keys = sorted(data.keys(), key=lambda k: data[k].get("time", 0))
                for k in sorted_keys[:len(data) - 100]:
                    del data[k]
            self._save(data)

    def clear(self):
        with self._lock:
            self._save({})

    def stats(self) -> dict:
        data = self._load()
        now = time.time()
        active = sum(1 for v in data.values() if now - v.get("time", 0) <= self.ttl)
        return {"total_cached": len(data), "active": active, "ttl_seconds": self.ttl}


class AuditLog:
    """Record all user actions for compliance."""

    def __init__(self):
        self._lock = threading.Lock()
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list:
        if not AUDIT_FILE.exists():
            return []
        try:
            return json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, data: list):
        AUDIT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def log(self, action: str, detail: str = "", user: str = "anonymous"):
        with self._lock:
            data = self._load()
            data.append({
                "action": action,
                "detail": detail[:500],
                "user": user,
                "time": time.time(),
            })
            # Keep last 1000 entries
            if len(data) > 1000:
                data = data[-1000:]
            self._save(data)

    def recent(self, limit: int = 50) -> list:
        data = self._load()
        return data[-limit:]

    def stats(self) -> dict:
        data = self._load()
        actions = {}
        for entry in data:
            a = entry.get("action", "unknown")
            actions[a] = actions.get(a, 0) + 1
        return {"total": len(data), "by_action": actions}
