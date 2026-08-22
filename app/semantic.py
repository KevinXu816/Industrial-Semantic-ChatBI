import copy
import os
import re
from pathlib import Path
import yaml
from .models import SemanticIntent, MetricDefinition

ROOT = Path(__file__).resolve().parents[1]
APPROVED_PATH = ROOT / "config" / "approved_semantic.yaml"
CUSTOM_METRICS_PATH = ROOT / "config" / "custom_metrics.yaml"
CUSTOM_ONTOLOGY_PATH = ROOT / "config" / "custom_ontology.yaml"


class SemanticRegistry:
    def __init__(self):
        self.reload()

    def reload(self):
        self.ontology = yaml.safe_load((ROOT / "config/ontology.yaml").read_text(encoding="utf-8"))
        self.metrics = yaml.safe_load((ROOT / "config/metrics.yaml").read_text(encoding="utf-8"))
        self._merge_approved()
        self._merge_custom_ontology()
        self._merge_custom_metrics()

    def _merge_custom_metrics(self):
        if not CUSTOM_METRICS_PATH.exists():
            return
        try:
            custom = yaml.safe_load(CUSTOM_METRICS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not custom or "metrics" not in custom:
            return
        self.metrics.setdefault("metrics", {}).update(custom["metrics"])

    def _save_custom_metrics(self, data: dict):
        CUSTOM_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_METRICS_PATH.write_text(
            yaml.dump({"metrics": data}, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def _load_custom_metrics(self) -> dict:
        if not CUSTOM_METRICS_PATH.exists():
            return {}
        try:
            data = yaml.safe_load(CUSTOM_METRICS_PATH.read_text(encoding="utf-8"))
            return data.get("metrics", {}) if data else {}
        except Exception:
            return {}

    def add_metric(self, m: MetricDefinition) -> dict:
        custom = self._load_custom_metrics()
        entry = {"description": m.description, "expression": m.expression}
        if m.entity:
            entry["entity"] = m.entity
        if m.unit:
            entry["unit"] = m.unit
        if m.time_field:
            entry["time_field"] = m.time_field
        if m.dependencies:
            entry["dependencies"] = m.dependencies
        if m.synonyms:
            entry["synonyms"] = m.synonyms
        custom[m.name] = entry
        self._save_custom_metrics(custom)
        self.reload()
        return self.metrics["metrics"][m.name]

    def update_metric(self, name: str, m: MetricDefinition) -> dict:
        all_metrics = self.metrics.get("metrics", {})
        if name not in all_metrics:
            raise KeyError(name)
        custom = self._load_custom_metrics()
        # Move base metric to custom layer for editing
        entry = {"description": m.description, "expression": m.expression}
        if m.entity:
            entry["entity"] = m.entity
        if m.unit:
            entry["unit"] = m.unit
        if m.time_field:
            entry["time_field"] = m.time_field
        if m.dependencies:
            entry["dependencies"] = m.dependencies
        if m.synonyms:
            entry["synonyms"] = m.synonyms
        if name != m.name:
            custom.pop(name, None)
        custom[m.name] = entry
        self._save_custom_metrics(custom)
        self.reload()
        return self.metrics["metrics"][m.name]

    def delete_metric(self, name: str):
        custom = self._load_custom_metrics()
        if name in custom:
            del custom[name]
            self._save_custom_metrics(custom)
            self.reload()
            return
        raise KeyError(name)

    def _merge_approved(self):
        """Overlay approved candidates onto the base ontology."""
        if not APPROVED_PATH.exists():
            return
        try:
            approved = yaml.safe_load(APPROVED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not approved:
            return
        for name, cfg in approved.get("entities", {}).items():
            if name not in self.ontology.get("entities", {}):
                self.ontology.setdefault("entities", {})[name] = cfg
        existing_edges = {(e["from"], e["relation"], e["to"])
                         for e in self.ontology.get("relationships", [])}
        for rel in approved.get("relationships", []):
            key = (rel["from"], rel["relation"], rel["to"])
            if key not in existing_edges:
                self.ontology.setdefault("relationships", []).append(rel)

    def _merge_custom_ontology(self):
        """Overlay user-edited ontology on top of base + approved."""
        if not CUSTOM_ONTOLOGY_PATH.exists():
            return
        try:
            custom = yaml.safe_load(CUSTOM_ONTOLOGY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if not custom:
            return
        for name, cfg in custom.get("entities", {}).items():
            self.ontology.setdefault("entities", {})[name] = cfg
        if "relationships" in custom:
            self.ontology["relationships"] = custom["relationships"]

    def _load_custom_ontology(self) -> dict:
        if not CUSTOM_ONTOLOGY_PATH.exists():
            return {"entities": {}, "relationships": []}
        try:
            data = yaml.safe_load(CUSTOM_ONTOLOGY_PATH.read_text(encoding="utf-8"))
            return data if data else {"entities": {}, "relationships": []}
        except Exception:
            return {"entities": {}, "relationships": []}

    def _save_custom_ontology(self, data: dict):
        CUSTOM_ONTOLOGY_PATH.parent.mkdir(parents=True, exist_ok=True)
        CUSTOM_ONTOLOGY_PATH.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    def save_entity(self, name: str, cfg: dict) -> dict:
        """Create or update an entity in the custom ontology layer."""
        custom = self._load_custom_ontology()
        custom.setdefault("entities", {})[name] = cfg
        self._save_custom_ontology(custom)
        self.reload()
        return self.ontology["entities"][name]

    def delete_entity(self, name: str):
        custom = self._load_custom_ontology()
        if name in custom.get("entities", {}):
            del custom["entities"][name]
            self._save_custom_ontology(custom)
            self.reload()
            return
        raise KeyError(name)

    def save_relationships(self, relationships: list) -> list:
        """Replace relationships in the custom ontology layer."""
        custom = self._load_custom_ontology()
        custom["relationships"] = relationships
        self._save_custom_ontology(custom)
        self.reload()
        return self.ontology.get("relationships", [])

    def table_ref(self, entity: str) -> str:
        mapping = self.ontology["entities"][entity]["physical_mapping"]
        return f"{mapping['catalog']}.{mapping['schema']}.{mapping['table']}"

    def column(self, entity: str, logical_property: str) -> str:
        return self.ontology["entities"][entity]["physical_mapping"]["columns"][logical_property]

    def graph(self):
        nodes = []
        for name, cfg in self.ontology.get("entities", {}).items():
            nodes.append({
                "id": name,
                "description": cfg.get("description", ""),
                "physical_table": self.table_ref(name),
                "properties": list(cfg.get("properties", {}).keys()),
            })
        edges = self.ontology.get("relationships", [])
        return {"nodes": nodes, "edges": edges}

    def _ontology_summary(self) -> str:
        return "\n".join(
            f"- {n['id']}: properties={','.join(n['properties'])}; table={n['physical_table']}"
            for n in self.graph()["nodes"]
        )

    def _metrics_summary(self) -> str:
        return "\n".join(
            f"- {name}: {cfg.get('description','')}; unit={cfg.get('unit','')}; synonyms={cfg.get('synonyms',[])}"
            for name, cfg in self.metrics.get("metrics", {}).items()
        )

    def resolve(self, question: str) -> SemanticIntent:
        from .llm_service import LLMService
        llm = LLMService()
        use_llm = llm.is_available() or os.getenv("SEMANTIC_PLANNER_MODE", "rules").lower() == "llm"
        if use_llm:
            return self._resolve_llm(question, llm)
        return self._resolve_rules(question)

    def _resolve_llm(self, question: str, llm_svc) -> SemanticIntent:
        import json as _json
        system = (
            "You are an industrial semantic parser. Return JSON only. Never generate SQL. "
            "Resolve the user's question into the supplied semantic model. "
            "Schema: {raw_question:string,machine_ref:string|null,metric:string|null,time_window_days:int,"
            "analysis_mode:'descriptive'|'diagnostic',related_entities:string[]}.\n"
            f"Ontology:\n{self._ontology_summary()}\nMetrics:\n{self._metrics_summary()}"
        )
        if llm_svc.is_available():
            content = llm_svc.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": question}],
                temperature=0, json_mode=True,
            )
        else:
            from .llm_planner import OpenAICompatibleSemanticPlanner
            planner = OpenAICompatibleSemanticPlanner()
            return planner.resolve(question, self._ontology_summary(), self._metrics_summary())
        obj = _json.loads(content)
        obj["raw_question"] = question
        return SemanticIntent.model_validate(obj)

    def _resolve_rules(self, question: str) -> SemanticIntent:
        machine_ref = None
        patterns = [
            r"(?<![A-Za-z0-9])[A-Za-z]{1,5}[-_]?[0-9]{1,5}(?![A-Za-z0-9])",
            r"[0-9]+#(?:空压机|风机|泵|设备)",
        ]
        for p in patterns:
            m = re.search(p, question, re.IGNORECASE)
            if m:
                machine_ref = m.group(0)
                break

        metric = None
        q = question.lower()
        candidates = []
        for metric_name, cfg in self.metrics["metrics"].items():
            for synonym in cfg.get("synonyms", []):
                if synonym.lower() in q:
                    candidates.append((len(synonym), metric_name))
        if candidates:
            metric = sorted(candidates, reverse=True)[0][1]
        if metric is None and ("能耗" in question or "耗电" in question):
            metric = "energy_consumption"

        days = 7
        m = re.search(r"(?:最近|近)?\s*(\d+)\s*天", question)
        if m:
            days = max(1, min(int(m.group(1)), 365))
        elif "昨天" in question or "最近24小时" in question or "24小时" in question:
            days = 1
        elif "最近一周" in question or "本周" in question or "一周" in question:
            days = 7
        elif "最近一个月" in question or "近一个月" in question or "一个月" in question:
            days = 30

        diagnostic = any(k in question for k in ["为什么", "原因", "异常", "故障", "关联", "相关"])
        related = ["Machine"]
        if metric in ("energy_consumption", "specific_energy_consumption"):
            related.append("EnergyObservation")
        if metric == "specific_energy_consumption":
            related.append("ProductionObservation")
        if diagnostic:
            related += ["AlarmEvent", "WorkOrder"]

        return SemanticIntent(
            raw_question=question,
            machine_ref=machine_ref,
            metric=metric,
            time_window_days=days,
            analysis_mode="diagnostic" if diagnostic else "descriptive",
            related_entities=list(dict.fromkeys(related)),
        )
