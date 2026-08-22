"""Preview and safely apply industry templates without overwriting config."""

import copy
import threading

from .models import MetricDefinition


CATEGORIES = ("entities", "relationships", "metrics", "aliases")


class TemplateApplyError(Exception):
    """Raised when a template cannot be applied without risking partial state."""


def relationship_key(relationship: dict) -> tuple[str, str, str]:
    return (
        relationship["from"],
        relationship["relation"],
        relationship["to"],
    )


def relationship_label(relationship: dict) -> str:
    return "-".join(relationship_key(relationship))


class TemplateApplier:
    def __init__(self, registry, alias_store, write_lock=None):
        self.registry = registry
        self.alias_store = alias_store
        self.write_lock = write_lock or threading.RLock()

    @staticmethod
    def _skip(name: str, reason: str) -> dict:
        return {"name": name, "reason": reason}

    @staticmethod
    def _metric_model(name: str, config: dict) -> MetricDefinition:
        return MetricDefinition(
            name=name,
            description=config.get("description", ""),
            entity=config.get("entity"),
            expression=config["expression"],
            unit=config.get("unit"),
            time_field=config.get("time_field"),
            dependencies=config.get("dependencies", []),
            synonyms=config.get("synonyms", []),
        )

    @staticmethod
    def _counts(result: dict) -> dict:
        return {
            group: {
                category: len(result[group][category])
                for category in CATEGORIES
            }
            for group in ("added", "skipped")
        }

    def _analyze(self, template: dict) -> tuple[dict, dict]:
        result = {
            "template_id": template["id"],
            "added": {category: [] for category in CATEGORIES},
            "skipped": {category: [] for category in CATEGORIES},
        }
        pending = {
            "entities": [],
            "relationships": [],
            "metrics": [],
            "aliases": {},
        }

        existing_entities = self.registry.ontology.get("entities", {})
        for name in template.get("entities", {}):
            if name in existing_entities:
                result["skipped"]["entities"].append(
                    self._skip(name, "同名实体已存在")
                )
            else:
                result["added"]["entities"].append(name)
                pending["entities"].append(name)

        existing_relationships = {
            relationship_key(relationship)
            for relationship in self.registry.ontology.get("relationships", [])
        }
        for relationship in template.get("relationships", []):
            label = relationship_label(relationship)
            if relationship_key(relationship) in existing_relationships:
                result["skipped"]["relationships"].append(
                    self._skip(label, "同一起点、关系和终点已存在")
                )
            else:
                result["added"]["relationships"].append(label)
                pending["relationships"].append(copy.deepcopy(relationship))

        existing_metrics = self.registry.metrics.get("metrics", {})
        for name in template.get("metrics", {}):
            if name in existing_metrics:
                result["skipped"]["metrics"].append(
                    self._skip(name, "同名指标已存在")
                )
            else:
                result["added"]["metrics"].append(name)
                pending["metrics"].append(name)

        existing_aliases = self.alias_store.get_all().get("aliases", {})
        for alias, field_name in template.get("aliases", {}).items():
            if alias in existing_aliases:
                result["skipped"]["aliases"].append(
                    self._skip(alias, "同名别名已存在")
                )
            else:
                result["added"]["aliases"].append(alias)
                pending["aliases"][alias] = field_name

        result["counts"] = self._counts(result)
        return result, pending

    def preview(self, template: dict) -> dict:
        with self.write_lock:
            self._validate_target_storage()
            result, _ = self._analyze(template)
            return result

    def apply(self, template: dict) -> dict:
        with self.write_lock:
            self._validate_target_storage()
            result, pending = self._analyze(template)
            registry_snapshot = self.registry.snapshot_custom_state()
            alias_snapshot = self.alias_store.snapshot_state()
            try:
                for name in pending["entities"]:
                    self.registry.save_entity(
                        name,
                        copy.deepcopy(template["entities"][name]),
                    )

                if pending["relationships"]:
                    merged = copy.deepcopy(
                        self.registry.ontology.get("relationships", [])
                    )
                    merged.extend(copy.deepcopy(pending["relationships"]))
                    self.registry.save_relationships(merged)

                for name in pending["metrics"]:
                    self.registry.add_metric(
                        self._metric_model(name, template["metrics"][name])
                    )

                if pending["aliases"]:
                    self.alias_store.set_aliases(pending["aliases"])
            except Exception as exc:
                rollback_errors = []
                try:
                    self.registry.restore_custom_state(registry_snapshot)
                except Exception as rollback_exc:
                    rollback_errors.append(f"语义模型回滚失败：{rollback_exc}")
                try:
                    self.alias_store.restore_state(alias_snapshot)
                except Exception as rollback_exc:
                    rollback_errors.append(f"别名回滚失败：{rollback_exc}")
                detail = f"行业模板应用失败，已回滚：{exc}"
                if rollback_errors:
                    detail = f"{detail}；{'；'.join(rollback_errors)}"
                raise TemplateApplyError(detail) from exc

            return {**result, "applied": True}

    def _validate_target_storage(self) -> None:
        try:
            self.registry.validate_custom_storage()
            self.alias_store.validate_storage()
        except Exception as exc:
            raise TemplateApplyError(
                f"行业模板应用前检查失败，未写入任何配置：{exc}"
            ) from exc
