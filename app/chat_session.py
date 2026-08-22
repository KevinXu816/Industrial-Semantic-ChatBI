import json
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "chat_sessions.json"
FEEDBACK_STORE = ROOT / "data" / "feedback.json"


class ChatSessionStore:
    def __init__(self, max_history: int = 20):
        self._lock = threading.Lock()
        self.max_history = max_history
        STORE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict:
        if not STORE.exists():
            return {}
        try:
            return json.loads(STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict):
        STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_session(self) -> str:
        sid = uuid.uuid4().hex[:12]
        with self._lock:
            data = self._load()
            data[sid] = {"created": time.time(), "messages": []}
            self._save(data)
        return sid

    def get_history(self, session_id: str) -> List[dict]:
        data = self._load()
        session = data.get(session_id)
        if not session:
            return []
        return session.get("messages", [])

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[dict] = None):
        with self._lock:
            data = self._load()
            if session_id not in data:
                data[session_id] = {"created": time.time(), "messages": []}
            msg = {"role": role, "content": content, "time": time.time()}
            if metadata:
                msg["metadata"] = metadata
            data[session_id]["messages"].append(msg)
            # Trim old messages
            if len(data[session_id]["messages"]) > self.max_history * 2:
                data[session_id]["messages"] = data[session_id]["messages"][-self.max_history * 2:]
            self._save(data)

    def get_context_summary(self, session_id: str, last_n: int = 6) -> str:
        """Build context from recent messages for LLM."""
        history = self.get_history(session_id)
        if not history:
            return ""
        recent = history[-last_n:]
        lines = []
        for m in recent:
            prefix = "用户" if m["role"] == "user" else "系统"
            lines.append(f"{prefix}: {m['content'][:200]}")
        return "\n".join(lines)


class FeedbackStore:
    def __init__(self):
        self._lock = threading.Lock()
        FEEDBACK_STORE.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list:
        if not FEEDBACK_STORE.exists():
            return []
        try:
            return json.loads(FEEDBACK_STORE.read_text(encoding="utf-8"))
        except Exception:
            return []

    def add(self, session_id: str, message_index: int, rating: str, comment: str = ""):
        with self._lock:
            data = self._load()
            data.append({
                "session_id": session_id,
                "message_index": message_index,
                "rating": rating,
                "comment": comment,
                "time": time.time(),
            })
            FEEDBACK_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def stats(self) -> dict:
        data = self._load()
        up = sum(1 for f in data if f["rating"] == "up")
        down = sum(1 for f in data if f["rating"] == "down")
        return {"total": len(data), "up": up, "down": down, "satisfaction_rate": round(up / max(up + down, 1), 2)}
