import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "llm_config.json"


class LLMConfig(BaseModel):
    api_url: str = ""
    api_key: str = ""  # legacy/dev only; prefer api_key_ref
    api_key_ref: str = ""
    model: str = ""
    temperature: float = 0.3
    timeout: int = 30
    enabled: bool = False


class LLMService:
    def __init__(self, secret_manager=None):
        self.secret_manager = secret_manager
        self._lock = threading.Lock()
        STORE.parent.mkdir(parents=True, exist_ok=True)

    def get_config(self) -> LLMConfig:
        if not STORE.exists():
            return LLMConfig()
        try:
            data = json.loads(STORE.read_text(encoding="utf-8"))
            return LLMConfig(**data)
        except Exception:
            return LLMConfig()

    def save_config(self, cfg: LLMConfig) -> LLMConfig:
        with self._lock:
            STORE.write_text(json.dumps(cfg.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg

    def is_available(self) -> bool:
        cfg = self.get_config()
        return cfg.enabled and bool(cfg.api_url) and bool(cfg.model)

    def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None, json_mode: bool = False) -> str:
        """Call OpenAI-compatible chat completions API."""
        cfg = self.get_config()
        if not cfg.enabled or not cfg.api_url or not cfg.model:
            raise RuntimeError("LLM 服务未配置或未启用")

        url = cfg.api_url.rstrip("/") + "/chat/completions"
        payload: Dict[str, Any] = {
            "model": cfg.model,
            "temperature": temperature if temperature is not None else cfg.temperature,
            "messages": messages,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        api_key = cfg.api_key
        if cfg.api_key_ref:
            if not self.secret_manager:
                raise RuntimeError("api_key_ref configured but SecretManager is unavailable")
            api_key = self.secret_manager.resolve_ref(cfg.api_key_ref, principal="llm_service", purpose="llm_api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

    def test_connection(self) -> Dict[str, Any]:
        """Quick connectivity test."""
        try:
            result = self.chat([{"role": "user", "content": "ping"}], temperature=0)
            return {"success": True, "message": f"连接成功，模型响应: {result[:50]}..."}
        except Exception as e:
            return {"success": False, "message": str(e)}
