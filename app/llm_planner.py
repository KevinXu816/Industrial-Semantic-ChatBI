import json
import os
import urllib.request
from typing import Optional
from .models import SemanticIntent


class OpenAICompatibleSemanticPlanner:
    """Optional LLM semantic parser. It produces SemanticIntent only; it never emits SQL."""

    def __init__(self):
        self.url = os.getenv("LLM_API_URL", "").rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "")
        if not self.url or not self.model:
            raise ValueError("LLM_API_URL and LLM_MODEL are required for SEMANTIC_PLANNER_MODE=llm")

    def resolve(self, question: str, ontology_summary: str, metrics_summary: str) -> SemanticIntent:
        system = (
            "You are an industrial semantic parser. Return JSON only. Never generate SQL. "
            "Resolve the user's question into the supplied semantic model. "
            "Schema: {raw_question:string,machine_ref:string|null,metric:string|null,time_window_days:int," 
            "analysis_mode:'descriptive'|'diagnostic',related_entities:string[]}.\n"
            f"Ontology:\n{ontology_summary}\nMetrics:\n{metrics_summary}"
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            self.url + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=int(os.getenv("LLM_TIMEOUT", "30"))) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        obj = json.loads(content)
        obj["raw_question"] = question
        return SemanticIntent.model_validate(obj)
