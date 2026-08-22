import copy
import os
import re
import tempfile
from pathlib import Path
import yaml
from .models import SemanticIntent, MetricDefinition

ROOT = Path(__file__).resolve().parents[1]
APPROVED_PATH = ROOT / "config" / "approved_semantic.yaml"
CUSTOM_METRICS_PATH = ROOT / "config" / "custom_metrics.yaml"
CUSTOM_ONTOLOGY_PATH = ROOT / "config" / "custom_ontology.yaml"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


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
        # Field-level overlay: custom edits must not erase governed execution
        # metadata (entity/time_field/dependencies) that they do not redefine.
        target = self.metrics.setdefault("metrics", {})
        for name, override in custom["metrics"].items():
            base = copy.deepcopy(target.get(name, {}))
            if isinstance(override, dict):
                base.update(override)
                target[name] = base
            else:
                target[name] = override

    def _save_custom_metrics(self, data: dict):
        _atomic_write_text(
            CUSTOM_METRICS_PATH,
            yaml.dump(
                {"metrics": data},
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ),
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
        _atomic_write_text(
            CUSTOM_ONTOLOGY_PATH,
            yaml.dump(
                data,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            ),
        )

    @staticmethod
    def _strict_yaml_mapping(path: Path, label: str) -> dict:
        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise RuntimeError(f"{label}读取失败：{exc}") from exc
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise RuntimeError(f"{label}顶层必须是对象")
        return data

    def validate_custom_storage(self) -> None:
        ontology = self._strict_yaml_mapping(
            CUSTOM_ONTOLOGY_PATH, "自定义本体配置"
        )
        if "entities" in ontology and not isinstance(
            ontology["entities"], dict
        ):
            raise RuntimeError("自定义本体 entities 必须是对象")
        if "relationships" in ontology and not isinstance(
            ontology["relationships"], list
        ):
            raise RuntimeError("自定义本体 relationships 必须是数组")

        metrics = self._strict_yaml_mapping(
            CUSTOM_METRICS_PATH, "自定义指标配置"
        )
        if "metrics" in metrics and not isinstance(metrics["metrics"], dict):
            raise RuntimeError("自定义指标 metrics 必须是对象")

    def snapshot_custom_state(self) -> dict[Path, bytes | None]:
        self.validate_custom_storage()
        return {
            path: path.read_bytes() if path.exists() else None
            for path in (CUSTOM_ONTOLOGY_PATH, CUSTOM_METRICS_PATH)
        }

    def restore_custom_state(self, snapshot: dict[Path, bytes | None]) -> None:
        for path, content in snapshot.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_text(path, content.decode("utf-8"))
        self.reload()

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
            mapping = cfg.get("physical_mapping") or {}
            table_parts = [
                mapping.get("catalog"),
                mapping.get("schema"),
                mapping.get("table"),
            ]
            nodes.append({
                "id": name,
                "description": cfg.get("description", ""),
                "physical_table": (
                    ".".join(table_parts) if all(table_parts) else "未配置"
                ),
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
            "Resolve the user's question into the supplied governed semantic model. "
            "V0.6 schema: {raw_question:string,subject:{entity:string,reference:string|null,key:string|null},"
            "metrics:string[],dimensions:string[],filters:{entity:string|null,property:string,operator:string,value:any}[],"
            "time_range:{type:'relative'|'absolute',value:int,unit:'hour'|'day'|'week'|'month',start:string|null,end:string|null},"
            "time_grain:string|null,comparison:{type:'none'|'previous_period'|'baseline'},"
            "analysis_mode:'descriptive'|'diagnostic',related_entities:string[]}. "
            "Only use entities, properties and metrics present in the supplied model.\n"
            f"Ontology:\n{self._ontology_summary()}\nMetrics:\n{self._metrics_summary()}"
        )
        if llm_svc.is_available():
            content = llm_svc.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": question}],
                temperature=0, json_mode=True,
            )
        else:
            from .llm_planner import OpenAICompatibleSemanticPlanner
            return OpenAICompatibleSemanticPlanner().resolve(question, self._ontology_summary(), self._metrics_summary())
        obj = _json.loads(content)
        obj["raw_question"] = question
        return SemanticIntent.model_validate(obj)

    def _resolve_rules(self, question: str) -> SemanticIntent:
        from .models import SemanticSubject, SemanticTimeRange, ComparisonSpec
        q = question.lower()

        # Subject entity detection is ontology-driven first, with Machine as compatibility default.
        subject_entity = "Machine"
        entity_keywords = {
            "Factory": ["工厂", "厂区", "factory"],
            "ProductionLine": ["产线", "生产线", "line"],
            "BESS": ["储能系统", "bess"],
            "PCS": ["pcs", "变流器"],
            "BatteryRack": ["rack", "电池簇", "电池架"],
            "Machine": ["设备", "空压机", "风机", "泵", "machine"],
        }
        available = self.ontology.get("entities", {})
        for entity, keywords in entity_keywords.items():
            if entity in available and any(k.lower() in q for k in keywords):
                subject_entity = entity
                break

        # Resolve a business reference without assuming a specific entity id field.
        subject_ref = None
        patterns = [
            r"(?<![A-Za-z0-9])[A-Za-z]{1,8}[-_]?[0-9]{1,8}(?![A-Za-z0-9])",
            r"[0-9]+#(?:空压机|风机|泵|设备|产线)",
        ]
        for pattern in patterns:
            m = re.search(pattern, question, re.IGNORECASE)
            if m:
                subject_ref = m.group(0)
                break

        metric_matches = []
        for metric_name, cfg in self.metrics["metrics"].items():
            matched_len = 0
            for synonym in cfg.get("synonyms", []):
                if synonym.lower() in q:
                    matched_len = max(matched_len, len(synonym))
            if matched_len:
                metric_matches.append((matched_len, metric_name))
        metric_names = []
        for _, metric_name in sorted(metric_matches, reverse=True):
            if metric_name not in metric_names:
                metric_names.append(metric_name)
        if not metric_names and ("能耗" in question or "耗电" in question):
            metric_names = ["energy_consumption"]
        metric = metric_names[0] if metric_names else None

        dimensions = []
        if "ProductionLine" in available and any(k in question for k in ["各产线", "每条产线", "按产线", "生产线分组"]):
            dimensions.append("ProductionLine.line_name")
        if "Machine" in available and any(k in question for k in ["各设备", "每台设备", "按设备"]):
            dimensions.append("Machine.machine_name")

        days = 7
        unit = "day"
        value = 7
        m = re.search(r"(?:最近|近)?\s*(\d+)\s*天", question)
        if m:
            value = max(1, min(int(m.group(1)), 365)); days = value
        elif "昨天" in question or "最近24小时" in question or "24小时" in question:
            value = 1; days = 1
        elif "最近一周" in question or "本周" in question or "一周" in question:
            value = 1; unit = "week"; days = 7
        elif "最近一个月" in question or "近一个月" in question or "一个月" in question or "本月" in question:
            value = 1; unit = "month"; days = 30

        diagnostic = any(k in question for k in ["为什么", "原因", "异常", "故障", "关联", "相关"])
        comparison_type = "previous_period" if any(k in question for k in ["增加", "下降", "同比", "环比", "相比", "变化", "上期", "上月", "上一周期"]) else "none"
        time_grain = None
        if any(k in question for k in ["每小时", "按小时"]): time_grain = "hour"
        elif any(k in question for k in ["每天", "按天", "按日", "每日"]): time_grain = "day"
        elif any(k in question for k in ["每周", "按周"]): time_grain = "week"
        elif any(k in question for k in ["每月", "按月"]): time_grain = "month"

        related = [subject_entity]
        if metric_names:
            from .metric_graph import MetricDependencyGraph
            graph = MetricDependencyGraph(self.metrics)
            for metric_name in metric_names:
                try:
                    related.extend(graph.entities(metric_name))
                except Exception:
                    pass
        if diagnostic:
            for entity in ("AlarmEvent", "WorkOrder"):
                if entity in available:
                    related.append(entity)

        return SemanticIntent(
            raw_question=question,
            subject=SemanticSubject(entity=subject_entity, reference=subject_ref),
            metrics=metric_names,
            dimensions=dimensions,
            time_range=SemanticTimeRange(type="relative", value=value, unit=unit),
            time_window_days=days,
            time_grain=time_grain,
            comparison=ComparisonSpec(type=comparison_type),
            analysis_mode="diagnostic" if diagnostic else "descriptive",
            related_entities=list(dict.fromkeys(related)),
        )
