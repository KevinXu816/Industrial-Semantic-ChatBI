import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

import app.main as main_module
from app.template_apply import TemplateApplyError
from app.template_store import TemplateStore
from tests.test_template_store import BUILTINS, template_payload


def apply_result(template_id: str, applied: bool = False) -> dict:
    result = {
        "template_id": template_id,
        "added": {
            "entities": ["ProductionRecord"],
            "relationships": [],
            "metrics": ["production_output"],
            "aliases": [],
        },
        "skipped": {
            "entities": [{"name": "Machine", "reason": "同名实体已存在"}],
            "relationships": [],
            "metrics": [],
            "aliases": [],
        },
        "counts": {
            "added": {
                "entities": 1,
                "relationships": 0,
                "metrics": 1,
                "aliases": 0,
            },
            "skipped": {
                "entities": 1,
                "relationships": 0,
                "metrics": 0,
                "aliases": 0,
            },
        },
    }
    if applied:
        result["applied"] = True
    return result


class FakeApplier:
    def __init__(self):
        self.previewed = []
        self.applied = []

    def preview(self, template: dict) -> dict:
        self.previewed.append(template["id"])
        return apply_result(template["id"])

    def apply(self, template: dict) -> dict:
        self.applied.append(template["id"])
        return apply_result(template["id"], applied=True)


class TemplateApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TemplateStore(
            path=Path(self.tmp.name) / "industry_templates.json",
            builtins=BUILTINS,
        )
        self.applier = FakeApplier()
        self.production_template_applier = main_module.template_applier
        self.store_patch = patch.object(
            main_module, "template_store", self.store, create=True
        )
        self.applier_patch = patch.object(
            main_module, "template_applier", self.applier, create=True
        )
        self.store_patch.start()
        self.applier_patch.start()
        self.client = TestClient(main_module.app)

    def tearDown(self):
        self.applier_patch.stop()
        self.store_patch.stop()
        self.tmp.cleanup()

    def test_lists_and_gets_template_details(self):
        listed = self.client.get("/templates")
        detail = self.client.get("/templates/manufacturing")

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["origin"], "builtin")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], "manufacturing")
        self.assertIn("counts", detail.json())

    def test_non_utf8_store_returns_the_structured_500_contract(self):
        self.store.path.write_bytes(b"\xff")

        response = self.client.get("/templates")

        self.assertEqual(response.status_code, 500)
        self.assertIn("读取失败", response.json()["detail"]["message"])
        self.assertEqual(response.json()["detail"]["errors"], [])

    def test_template_create_update_delete_and_conflict(self):
        created = self.client.post(
            "/templates", json=template_payload("custom-one")
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["origin"], "custom")

        conflict = self.client.post(
            "/templates", json=template_payload("custom-one")
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("已存在", conflict.json()["detail"]["message"])

        updated = self.client.put(
            "/templates/custom-one",
            json=template_payload("custom-one", name="修改名称"),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "修改名称")

        deleted = self.client.delete("/templates/custom-one")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"deleted": "custom-one"})
        self.assertEqual(self.client.get("/templates/custom-one").status_code, 404)

    def test_builtin_update_reset_and_delete_rules(self):
        updated = self.client.put(
            "/templates/manufacturing",
            json=template_payload("manufacturing", name="修改内置"),
        )
        self.assertTrue(updated.json()["customized"])

        reset = self.client.post("/templates/manufacturing/reset")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["name"], "制造业通用")
        self.assertFalse(reset.json()["customized"])

        rejected = self.client.delete("/templates/manufacturing")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("不能删除", rejected.json()["detail"]["message"])

    def test_upload_validation_returns_normalized_preview_without_saving(self):
        payload = template_payload("yaml-one")
        response = self.client.post(
            "/templates/validate",
            json={
                "filename": "yaml-one.yaml",
                "content": yaml.safe_dump(payload, allow_unicode=True),
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["template"]["id"], "yaml-one")
        self.assertEqual(body["counts"]["entities"], 2)
        self.assertFalse(body["conflict"])
        self.assertFalse(self.store.path.exists())

    def test_upload_validation_reports_conflicts_and_bad_inputs(self):
        conflict = self.client.post(
            "/templates/validate",
            json={
                "filename": "manufacturing.json",
                "content": json.dumps(
                    template_payload("manufacturing"), ensure_ascii=False
                ),
            },
        )
        self.assertEqual(conflict.status_code, 200)
        self.assertTrue(conflict.json()["conflict"])

        unsupported = self.client.post(
            "/templates/validate",
            json={"filename": "template.txt", "content": "plain"},
        )
        self.assertEqual(unsupported.status_code, 400)
        self.assertTrue(unsupported.json()["detail"]["errors"])

        malformed_request = self.client.post(
            "/templates/validate", json={"filename": "missing-content.json"}
        )
        self.assertEqual(malformed_request.status_code, 400)

    def test_apply_preview_and_apply_routes_use_managed_template(self):
        self.store.create(template_payload("api-template"))

        preview = self.client.get("/templates/api-template/apply-preview")
        applied = self.client.post("/templates/api-template/apply")

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["counts"]["added"]["entities"], 1)
        self.assertEqual(applied.status_code, 200)
        self.assertTrue(applied.json()["applied"])
        self.assertEqual(self.applier.previewed, ["api-template"])
        self.assertEqual(self.applier.applied, ["api-template"])

    def test_missing_template_and_id_mismatch_return_expected_statuses(self):
        self.assertEqual(self.client.get("/templates/missing").status_code, 404)

        self.store.create(template_payload("custom-one"))
        mismatch = self.client.put(
            "/templates/custom-one", json=template_payload("different-id")
        )
        self.assertEqual(mismatch.status_code, 400)
        self.assertTrue(mismatch.json()["detail"]["errors"])

    def test_non_object_template_bodies_use_the_structured_400_contract(self):
        responses = (
            self.client.post("/templates/validate", json=[]),
            self.client.post("/templates", json=[]),
            self.client.put("/templates/manufacturing", json=[]),
        )

        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertIn("message", response.json()["detail"])
            self.assertTrue(response.json()["detail"]["errors"])

    def test_internal_store_and_apply_failures_return_structured_500(self):
        self.store.path.write_text("{broken", encoding="utf-8")
        store_failure = self.client.get("/templates")
        self.assertEqual(store_failure.status_code, 500)
        self.assertIn("message", store_failure.json()["detail"])

        self.store.path.unlink()

        def fail_apply(_template):
            raise TemplateApplyError("事务写入失败")

        self.applier.apply = fail_apply
        apply_failure = self.client.post("/templates/manufacturing/apply")
        self.assertEqual(apply_failure.status_code, 500)
        self.assertEqual(
            apply_failure.json()["detail"]["message"], "事务写入失败"
        )

    def test_production_applier_shares_the_semantic_write_lock(self):
        self.assertIs(
            self.production_template_applier.write_lock,
            main_module.semantic_write_lock,
        )


if __name__ == "__main__":
    unittest.main()
