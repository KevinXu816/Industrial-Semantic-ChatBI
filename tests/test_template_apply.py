import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.template_apply import TemplateApplier, TemplateApplyError
from app.semantic import SemanticRegistry
import app.semantic as semantic_module
from app.field_aliases import FieldAliasStore
import app.field_aliases as alias_module
from app.template_models import IndustryTemplate


EXISTING_RELATIONSHIP = {
    "from": "Machine",
    "relation": "LOCATED_IN",
    "to": "Workshop",
    "on": "workshop_id",
}
EXISTING_TEMPLATE_RELATIONSHIP = {
    "from": "Machine",
    "relation": "HAS_ENERGY",
    "to": "EnergyObservation",
    "on": "machine_id",
}

TEMPLATE = {
    "id": "manufacturing",
    "name": "制造业通用",
    "description": "制造行业模板",
    "entities": {
        "Machine": {
            "description": "template machine",
            "properties": {"machine_id": {"type": "string"}},
        },
        "EnergyObservation": {
            "description": "template energy",
            "properties": {"machine_id": {"type": "string"}},
        },
        "ProductionRecord": {
            "description": "production",
            "properties": {
                "machine_id": {"type": "string"},
                "output_qty": {"type": "number"},
            },
        },
    },
    "relationships": [
        EXISTING_TEMPLATE_RELATIONSHIP,
        {
            "from": "Machine",
            "relation": "HAS_PRODUCTION",
            "to": "ProductionRecord",
            "on": "machine_id",
        },
    ],
    "metrics": {
        "energy_consumption": {
            "description": "模板能耗",
            "expression": "SUM(energy_kwh)",
            "unit": "kWh",
            "synonyms": ["能耗"],
        },
        "production_output": {
            "description": "总产量",
            "expression": "SUM(output_qty)",
            "unit": "件",
            "synonyms": ["产量"],
        },
    },
    "aliases": {
        "设备编号": "machine_code",
        "车间": "workshop",
    },
}


class FakeRegistry:
    def __init__(self):
        self.ontology = {
            "entities": {
                "Machine": {
                    "description": "existing machine",
                    "properties": {"id": {"type": "string"}},
                    "physical_mapping": {"table": "machine"},
                },
                "EnergyObservation": {
                    "description": "existing energy",
                    "properties": {"machine_id": {"type": "string"}},
                },
            },
            "relationships": [
                copy.deepcopy(EXISTING_RELATIONSHIP),
                copy.deepcopy(EXISTING_TEMPLATE_RELATIONSHIP),
            ],
        }
        self.metrics = {
            "metrics": {
                "energy_consumption": {
                    "description": "existing metric",
                    "expression": "existing_expr",
                }
            }
        }

    def save_entity(self, name: str, cfg: dict):
        self.ontology["entities"][name] = copy.deepcopy(cfg)

    def save_relationships(self, relationships: list[dict]):
        self.ontology["relationships"] = copy.deepcopy(relationships)

    def add_metric(self, metric):
        self.metrics["metrics"][metric.name] = metric.model_dump(exclude_none=True)

    def validate_custom_storage(self):
        return None

    def snapshot_custom_state(self):
        return copy.deepcopy((self.ontology, self.metrics))

    def restore_custom_state(self, snapshot):
        self.ontology, self.metrics = copy.deepcopy(snapshot)


class FakeAliasStore:
    def __init__(self):
        self.data = {
            "aliases": {"设备编号": "existing_field"},
            "enums": {},
        }

    def get_all(self):
        return copy.deepcopy(self.data)

    def set_aliases(self, aliases: dict[str, str]):
        self.data["aliases"].update(aliases)
        return copy.deepcopy(self.data["aliases"])

    def validate_storage(self):
        return None

    def snapshot_state(self):
        return copy.deepcopy(self.data)

    def restore_state(self, snapshot):
        self.data = copy.deepcopy(snapshot)


class TemplateApplierTest(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.aliases = FakeAliasStore()
        self.applier = TemplateApplier(self.registry, self.aliases)

    def test_preview_reports_additions_and_skips_without_mutation(self):
        ontology_before = copy.deepcopy(self.registry.ontology)
        metrics_before = copy.deepcopy(self.registry.metrics)
        aliases_before = self.aliases.get_all()

        result = self.applier.preview(TEMPLATE)

        self.assertEqual(result["added"]["entities"], ["ProductionRecord"])
        self.assertEqual(
            [item["name"] for item in result["skipped"]["entities"]],
            ["Machine", "EnergyObservation"],
        )
        self.assertEqual(
            result["added"]["relationships"],
            ["Machine-HAS_PRODUCTION-ProductionRecord"],
        )
        self.assertEqual(
            result["skipped"]["relationships"][0]["name"],
            "Machine-HAS_ENERGY-EnergyObservation",
        )
        self.assertEqual(result["added"]["metrics"], ["production_output"])
        self.assertEqual(result["added"]["aliases"], ["车间"])
        self.assertEqual(self.registry.ontology, ontology_before)
        self.assertEqual(self.registry.metrics, metrics_before)
        self.assertEqual(self.aliases.get_all(), aliases_before)

    def test_apply_preserves_existing_values_and_relationships(self):
        result = self.applier.apply(TEMPLATE)

        self.assertTrue(result["applied"])
        self.assertEqual(
            self.registry.ontology["entities"]["Machine"]["description"],
            "existing machine",
        )
        self.assertIn(EXISTING_RELATIONSHIP, self.registry.ontology["relationships"])
        self.assertIn(
            {
                "from": "Machine",
                "relation": "HAS_PRODUCTION",
                "to": "ProductionRecord",
                "on": "machine_id",
            },
            self.registry.ontology["relationships"],
        )
        self.assertEqual(
            self.registry.metrics["metrics"]["energy_consumption"]["expression"],
            "existing_expr",
        )
        self.assertEqual(
            self.aliases.get_all()["aliases"]["设备编号"],
            "existing_field",
        )
        self.assertEqual(
            self.registry.metrics["metrics"]["production_output"]["expression"],
            "SUM(output_qty)",
        )
        self.assertEqual(self.aliases.get_all()["aliases"]["车间"], "workshop")

    def test_preview_and_apply_have_identical_counts(self):
        preview = self.applier.preview(TEMPLATE)
        applied = self.applier.apply(TEMPLATE)

        self.assertEqual(preview["counts"], applied["counts"])
        self.assertEqual(
            applied["counts"],
            {
                "added": {
                    "entities": 1,
                    "relationships": 1,
                    "metrics": 1,
                    "aliases": 1,
                },
                "skipped": {
                    "entities": 2,
                    "relationships": 1,
                    "metrics": 1,
                    "aliases": 1,
                },
            },
        )

    def test_relationship_duplicate_ignores_different_join_field(self):
        changed = copy.deepcopy(TEMPLATE)
        changed["relationships"][0]["on"] = "different_field"

        result = self.applier.preview(changed)

        self.assertEqual(len(result["skipped"]["relationships"]), 1)
        self.assertEqual(len(result["added"]["relationships"]), 1)

    def test_semantic_graph_can_render_an_unmapped_template_entity(self):
        registry = SemanticRegistry.__new__(SemanticRegistry)
        registry.ontology = {
            "entities": {
                "ProductionRecord": {
                    "description": "模板新增实体",
                    "properties": {"output_qty": {"type": "number"}},
                }
            },
            "relationships": [],
        }

        graph = registry.graph()

        self.assertEqual(graph["nodes"][0]["physical_table"], "未配置")

    def test_validated_physical_mapping_survives_apply_and_graph_rendering(self):
        mapped_template = copy.deepcopy(TEMPLATE)
        mapped_template["entities"]["ProductionRecord"]["physical_mapping"] = {
            "catalog": "mes",
            "schema": "production",
            "table": "production_record",
            "columns": {"machine_id": "device_id", "output_qty": "quantity"},
        }
        validated = IndustryTemplate.model_validate(mapped_template).model_dump(
            by_alias=True,
            exclude_none=True,
        )

        self.applier.apply(validated)
        graph_registry = SemanticRegistry.__new__(SemanticRegistry)
        graph_registry.ontology = self.registry.ontology
        production_node = next(
            node
            for node in graph_registry.graph()["nodes"]
            if node["id"] == "ProductionRecord"
        )

        self.assertEqual(
            production_node["physical_table"],
            "mes.production.production_record",
        )
        self.assertEqual(
            self.registry.ontology["entities"]["ProductionRecord"]
            ["physical_mapping"]["columns"]["output_qty"],
            "quantity",
        )

    def test_apply_rolls_back_all_categories_when_a_later_write_fails(self):
        ontology_before = copy.deepcopy(self.registry.ontology)
        metrics_before = copy.deepcopy(self.registry.metrics)
        aliases_before = self.aliases.get_all()

        def fail_relationship_save(_relationships):
            raise OSError("simulated relationship write failure")

        self.registry.save_relationships = fail_relationship_save

        with self.assertRaises(TemplateApplyError):
            self.applier.apply(TEMPLATE)

        self.assertEqual(self.registry.ontology, ontology_before)
        self.assertEqual(self.registry.metrics, metrics_before)
        self.assertEqual(self.aliases.get_all(), aliases_before)

    def test_apply_fails_closed_when_a_real_target_store_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ontology_path = root / "custom_ontology.yaml"
            metrics_path = root / "custom_metrics.yaml"
            aliases_path = root / "field_aliases.json"
            with (
                patch.object(
                    semantic_module, "CUSTOM_ONTOLOGY_PATH", ontology_path
                ),
                patch.object(
                    semantic_module, "CUSTOM_METRICS_PATH", metrics_path
                ),
                patch.object(alias_module, "ALIASES_FILE", aliases_path),
            ):
                registry = SemanticRegistry()
                aliases = FieldAliasStore()
                applier = TemplateApplier(registry, aliases)
                registry.validate_custom_storage()
                aliases.validate_storage()

                ontology_path.write_text("{broken", encoding="utf-8")
                with self.assertRaises(TemplateApplyError):
                    applier.apply(TEMPLATE)
                self.assertEqual(
                    ontology_path.read_text(encoding="utf-8"), "{broken"
                )
                self.assertFalse(metrics_path.exists())
                self.assertFalse(aliases_path.exists())

                ontology_path.write_text("{}", encoding="utf-8")
                aliases_path.write_text("{broken", encoding="utf-8")
                with self.assertRaises(TemplateApplyError):
                    applier.apply(TEMPLATE)
                self.assertEqual(
                    aliases_path.read_text(encoding="utf-8"), "{broken"
                )
                self.assertFalse(metrics_path.exists())


if __name__ == "__main__":
    unittest.main()
