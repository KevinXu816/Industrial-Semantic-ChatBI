import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from app.template_store import (
    TemplateConflictError,
    TemplateNotFoundError,
    TemplateOperationError,
    TemplateStore,
    TemplateStoreError,
    TemplateValidationError,
)


BUILTINS = {
    "manufacturing": {
        "name": "制造业通用",
        "description": "制造行业模板",
        "entities": {
            "Machine": {
                "description": "设备",
                "properties": {"machine_id": {"type": "string"}},
            }
        },
        "relationships": [],
        "metrics": {},
        "aliases": {},
    },
    "energy": {
        "name": "能源管理",
        "description": "能源行业模板",
        "entities": {
            "Meter": {
                "description": "计量表",
                "properties": {"meter_id": {"type": "string"}},
            }
        },
        "relationships": [],
        "metrics": {},
        "aliases": {},
    },
}


def template_payload(template_id: str, name: str = "汽车零部件") -> dict:
    return {
        "id": template_id,
        "name": name,
        "description": "自定义行业模板",
        "entities": {
            "Machine": {
                "description": "设备",
                "properties": {"machine_id": {"type": "string"}},
            },
            "ProductionRecord": {
                "description": "生产记录",
                "properties": {
                    "machine_id": {"type": "string"},
                    "output_qty": {"type": "number"},
                },
            },
        },
        "relationships": [
            {
                "from": "Machine",
                "relation": "HAS_PRODUCTION",
                "to": "ProductionRecord",
                "on": "machine_id",
            }
        ],
        "metrics": {
            "production_output": {
                "description": "总产量",
                "expression": "SUM(output_qty)",
                "unit": "件",
                "synonyms": ["产量"],
            }
        },
        "aliases": {"设备编号": "machine_id"},
    }


class TemplateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "industry_templates.json"
        self.store = TemplateStore(path=self.path, builtins=BUILTINS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_builtin_templates_with_metadata(self):
        items = self.store.list()

        self.assertEqual([item["id"] for item in items], ["manufacturing", "energy"])
        self.assertEqual(items[0]["origin"], "builtin")
        self.assertFalse(items[0]["customized"])
        self.assertEqual(items[0]["counts"]["entities"], 1)
        self.assertEqual(items[0]["counts"]["aliases"], 0)

    def test_editing_and_resetting_builtin_uses_override_layer(self):
        payload = template_payload("manufacturing", name="修改名称")

        updated = self.store.update("manufacturing", payload)

        self.assertEqual(updated["name"], "修改名称")
        self.assertTrue(updated["customized"])
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("manufacturing", stored["overrides"])
        self.store.reset("manufacturing")
        restored = self.store.get("manufacturing")
        self.assertEqual(restored["name"], "制造业通用")
        self.assertFalse(restored["customized"])

    def test_custom_template_can_be_created_updated_and_deleted(self):
        created = self.store.create(template_payload("automotive-parts"))
        self.assertEqual(created["origin"], "custom")

        updated = self.store.update(
            "automotive-parts",
            template_payload("automotive-parts", name="汽车件"),
        )
        self.assertEqual(updated["name"], "汽车件")

        deleted = self.store.delete("automotive-parts")
        self.assertEqual(deleted, {"deleted": "automotive-parts"})
        with self.assertRaises(TemplateNotFoundError):
            self.store.get("automotive-parts")

    def test_create_rejects_existing_template_id(self):
        with self.assertRaises(TemplateConflictError):
            self.store.create(template_payload("manufacturing"))
        self.store.create(template_payload("custom-one"))
        with self.assertRaises(TemplateConflictError):
            self.store.create(template_payload("custom-one"))

    def test_builtin_cannot_be_deleted_and_custom_cannot_be_reset(self):
        with self.assertRaises(TemplateOperationError):
            self.store.delete("manufacturing")

        self.store.create(template_payload("custom-one"))
        with self.assertRaises(TemplateOperationError):
            self.store.reset("custom-one")

    def test_parse_upload_accepts_json_and_yaml_without_saving(self):
        parsed_json = self.store.parse_upload(
            "template.json", json.dumps(template_payload("json-one"), ensure_ascii=False)
        )
        parsed_yaml = self.store.parse_upload(
            "template.yaml",
            yaml.safe_dump(template_payload("yaml-one"), allow_unicode=True),
        )

        self.assertEqual(parsed_json["id"], "json-one")
        self.assertEqual(parsed_yaml["id"], "yaml-one")
        self.assertFalse(self.path.exists())

    def test_parse_upload_rejects_unsupported_or_malformed_files(self):
        with self.assertRaises(TemplateValidationError):
            self.store.parse_upload("template.txt", "plain text")
        with self.assertRaises(TemplateValidationError):
            self.store.parse_upload("template.json", "{broken")
        with self.assertRaises(TemplateValidationError):
            self.store.parse_upload("template.yaml", "- list-item")

    def test_validation_rejects_invalid_fields_and_relationship_references(self):
        with self.assertRaises(TemplateValidationError) as id_error:
            self.store.create(template_payload("Invalid ID"))
        self.assertTrue(any(item["path"] == "id" for item in id_error.exception.errors))

        dangling = template_payload("dangling")
        dangling["relationships"][0]["to"] = "Missing"
        with self.assertRaises(TemplateValidationError) as relation_error:
            self.store.create(dangling)
        self.assertTrue(
            any(item["path"] == "relationships.0.to" for item in relation_error.exception.errors)
        )

        invalid_type = template_payload("invalid-type")
        invalid_type["entities"]["Machine"]["properties"]["machine_id"]["type"] = "uuid"
        with self.assertRaises(TemplateValidationError):
            self.store.create(invalid_type)

        invalid_mapping = template_payload("invalid-mapping")
        invalid_mapping["entities"]["Machine"]["physical_mapping"] = "not-an-object"
        with self.assertRaises(TemplateValidationError) as mapping_error:
            self.store.create(invalid_mapping)
        self.assertTrue(
            any(
                item["path"] == "entities.Machine.physical_mapping"
                for item in mapping_error.exception.errors
            )
        )

        invalid_columns = template_payload("invalid-columns")
        invalid_columns["entities"]["Machine"]["physical_mapping"] = {
            "table": "machine",
            "columns": "not-an-object",
        }
        with self.assertRaises(TemplateValidationError):
            self.store.create(invalid_columns)

        duplicate_relationship = template_payload("duplicate-relationship")
        duplicate_relationship["relationships"].append(
            {
                **duplicate_relationship["relationships"][0],
                "on": "another_field",
            }
        )
        with self.assertRaises(TemplateValidationError) as duplicate_error:
            self.store.create(duplicate_relationship)
        self.assertTrue(
            any(
                item["path"] == "relationships.1"
                for item in duplicate_error.exception.errors
            )
        )

    def test_parse_upload_rejects_files_over_two_mib(self):
        with self.assertRaises(TemplateValidationError):
            self.store.parse_upload("large.json", "x" * (2 * 1024 * 1024 + 1))

    def test_update_rejects_template_id_change(self):
        self.store.create(template_payload("custom-one"))
        with self.assertRaises(TemplateValidationError):
            self.store.update("custom-one", template_payload("different-id"))

    def test_corrupt_store_is_reported_without_overwriting_the_file(self):
        self.path.write_text("{broken", encoding="utf-8")

        with self.assertRaises(TemplateStoreError):
            self.store.list()

        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")

    def test_non_utf8_store_is_reported_as_a_store_error(self):
        self.path.write_bytes(b"\xff")

        with self.assertRaises(TemplateStoreError):
            self.store.list()

        self.assertEqual(self.path.read_bytes(), b"\xff")

    def test_write_operations_return_the_locked_snapshot_without_get_race(self):
        with patch.object(
            self.store,
            "get",
            side_effect=AssertionError("write result must not perform an unlocked reread"),
        ):
            created = self.store.create(template_payload("custom-one"))
            updated = self.store.update(
                "custom-one",
                template_payload("custom-one", name="更新后"),
            )
            reset = self.store.reset("manufacturing")

        self.assertEqual(created["name"], "汽车零部件")
        self.assertEqual(updated["name"], "更新后")
        self.assertEqual(reset["name"], "制造业通用")


if __name__ == "__main__":
    unittest.main()
