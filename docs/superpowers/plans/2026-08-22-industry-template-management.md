# Industry Template Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a complete industry-template management UI and persistent backend supporting browse, detail preview, JSON/YAML upload, structured create/edit, built-in reset, custom deletion, apply preview, and safe application.

**Architecture:** Keep `app/templates.py` as the immutable built-in baseline. Add a JSON-backed `TemplateStore`, a separate safe-merge `TemplateApplier`, focused Pydantic models, and thin FastAPI routes. Add isolated CSS and JavaScript files to the existing no-build single-page frontend.

**Tech Stack:** Python 3.10+, FastAPI 0.116.1, Pydantic 2.11.7, PyYAML 6.0.2, standard-library `unittest`, FastAPI `TestClient` with development-only `httpx==0.28.1`, vanilla HTML/CSS/JavaScript.

**Status:** Implemented and verified locally on 2026-08-22. Per the project constraint, the working tree is intentionally left uncommitted.

## Global Constraints

- Modify only `/Users/xuhongliang/Workspace/git-chatbi/Industrial-Semantic-ChatBI`.
- Do not run `git commit`, `git push`, or create branches.
- Preserve all pre-existing user changes and runtime data.
- Template application never overwrites existing entities, relationships, metrics, or aliases.
- Uploaded template files must be UTF-8 JSON/YAML/YML and no larger than 2 MiB.
- Do not introduce a frontend framework or build step.
- All user-controlled text must be escaped before HTML rendering.

---

### Task 1: Template Models and Persistent Store

**Files:**
- Create: `requirements-dev.txt`
- Create: `app/template_models.py`
- Create: `app/template_store.py`
- Create: `tests/test_template_store.py`

**Interfaces:**
- Consumes: `app.templates.TEMPLATES` as `dict[str, dict]`.
- Produces: `IndustryTemplate`, `TemplateUploadRequest`, `TemplateStore`, `TemplateStoreError`, `TemplateNotFoundError`, `TemplateConflictError`, `TemplateOperationError`, and `TemplateValidationError`.
- Produces store methods: `list() -> list[dict]`, `get(template_id: str) -> dict`, `parse_upload(filename: str, content: str) -> dict`, `create(payload: dict) -> dict`, `update(template_id: str, payload: dict) -> dict`, `delete(template_id: str) -> dict`, and `reset(template_id: str) -> dict`.

- [x] **Step 1: Add the development-only HTTP test dependency**

```text
httpx==0.28.1
```

- [x] **Step 2: Write failing model and store tests**

Create tests that use `tempfile.TemporaryDirectory()` and an injected two-template built-in dictionary. Cover these concrete assertions:

```python
class TemplateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "industry_templates.json"
        self.store = TemplateStore(path=self.path, builtins=BUILTINS)

    def test_lists_builtin_templates_with_metadata(self):
        item = self.store.list()[0]
        self.assertEqual(item["origin"], "builtin")
        self.assertFalse(item["customized"])
        self.assertEqual(item["counts"]["entities"], 1)

    def test_editing_and_resetting_builtin_uses_override_layer(self):
        payload = template_payload("manufacturing", name="修改名称")
        self.assertEqual(self.store.update("manufacturing", payload)["name"], "修改名称")
        self.assertTrue(self.store.get("manufacturing")["customized"])
        self.store.reset("manufacturing")
        self.assertEqual(self.store.get("manufacturing")["name"], "制造业通用")

    def test_custom_template_can_be_created_updated_and_deleted(self):
        self.store.create(template_payload("automotive-parts"))
        self.store.update("automotive-parts", template_payload("automotive-parts", name="汽车件"))
        self.assertEqual(self.store.get("automotive-parts")["name"], "汽车件")
        self.store.delete("automotive-parts")
        with self.assertRaises(TemplateNotFoundError):
            self.store.get("automotive-parts")

    def test_builtin_cannot_be_deleted_and_custom_cannot_be_reset(self):
        with self.assertRaises(TemplateOperationError):
            self.store.delete("manufacturing")
        self.store.create(template_payload("custom-one"))
        with self.assertRaises(TemplateOperationError):
            self.store.reset("custom-one")

    def test_parse_upload_accepts_json_and_yaml_without_saving(self):
        parsed_json = self.store.parse_upload("template.json", json.dumps(template_payload("json-one")))
        parsed_yaml = self.store.parse_upload("template.yaml", yaml.safe_dump(template_payload("yaml-one"), allow_unicode=True))
        self.assertEqual(parsed_json["id"], "json-one")
        self.assertEqual(parsed_yaml["id"], "yaml-one")
        self.assertFalse(self.path.exists())

    def test_validation_rejects_invalid_id_relationship_reference_and_large_file(self):
        bad = template_payload("Invalid ID")
        with self.assertRaises(TemplateValidationError):
            self.store.create(bad)
        dangling = template_payload("dangling")
        dangling["relationships"] = [{"from": "Machine", "relation": "USES", "to": "Missing", "on": "id"}]
        with self.assertRaises(TemplateValidationError):
            self.store.create(dangling)
        with self.assertRaises(TemplateValidationError):
            self.store.parse_upload("large.json", "x" * (2 * 1024 * 1024 + 1))

    def test_corrupt_store_is_reported_and_original_file_survives_failed_write(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(TemplateStoreError):
            self.store.list()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")
```

- [x] **Step 3: Run the store tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_store -v
```

Expected: import failure because `app.template_store` and `app.template_models` do not exist.

- [x] **Step 4: Implement validated Pydantic models**

Implement these concrete types in `app/template_models.py`:

```python
ALLOWED_PROPERTY_TYPES = {"string", "number", "integer", "boolean", "date", "datetime"}
TEMPLATE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

class PropertyDefinition(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str

class TemplateEntity(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str = ""
    properties: Dict[str, PropertyDefinition]

class TemplateRelationship(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")
    from_entity: str = Field(alias="from")
    relation: str
    to_entity: str = Field(alias="to")
    on: str

class TemplateMetric(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str = ""
    expression: str
    unit: Optional[str] = None
    synonyms: List[str] = Field(default_factory=list)
    entity: Optional[str] = None
    time_field: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)

class IndustryTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    entities: Dict[str, TemplateEntity]
    relationships: List[TemplateRelationship] = Field(default_factory=list)
    metrics: Dict[str, TemplateMetric] = Field(default_factory=dict)
    aliases: Dict[str, str] = Field(default_factory=dict)

class TemplateUploadRequest(BaseModel):
    filename: str
    content: str
```

Add validators that trim strings, enforce the ID pattern, require at least one entity, reject blank mapping keys and values, restrict property types, and preserve any supported extra semantic fields.

- [x] **Step 5: Implement the persistent store**

Implement the following store structure and behavior in `app/template_store.py`:

```python
DEFAULT_TEMPLATE_FILE = ROOT / "data" / "industry_templates.json"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

class TemplateStore:
    def __init__(self, path: Path = DEFAULT_TEMPLATE_FILE, builtins: Optional[dict] = None):
        self.path = Path(path)
        self.builtins = copy.deepcopy(TEMPLATES if builtins is None else builtins)
        self._lock = threading.RLock()

    def _empty_data(self) -> dict:
        return {"version": 1, "overrides": {}, "custom": {}}

    def _serialize_template(self, template: IndustryTemplate) -> dict:
        return template.model_dump(by_alias=True, exclude={"id"}, exclude_none=True)

    def _load_data(self) -> dict:
        if not self.path.exists():
            return self._empty_data()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TemplateStoreError(f"行业模板存储文件读取失败：{exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("overrides"), dict) or not isinstance(data.get("custom"), dict):
            raise TemplateStoreError("行业模板存储文件结构无效")
        return {"version": 1, "overrides": data["overrides"], "custom": data["custom"]}

    def _validate(self, payload: dict, expected_id: Optional[str] = None) -> IndustryTemplate:
        try:
            template = IndustryTemplate.model_validate(payload)
        except ValidationError as exc:
            errors = [{"path": ".".join(str(part) for part in item["loc"]), "message": item["msg"]} for item in exc.errors()]
            raise TemplateValidationError("模板校验失败", errors) from exc
        errors = []
        if expected_id is not None and template.id != expected_id:
            errors.append({"path": "id", "message": "模板 ID 与请求路径不一致"})
        entity_names = set(template.entities)
        for index, relationship in enumerate(template.relationships):
            if relationship.from_entity not in entity_names:
                errors.append({"path": f"relationships.{index}.from", "message": "起点实体不存在"})
            if relationship.to_entity not in entity_names:
                errors.append({"path": f"relationships.{index}.to", "message": "终点实体不存在"})
        if errors:
            raise TemplateValidationError("模板校验失败", errors)
        return template

    def _save_data(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as handle:
                temporary_name = handle.name
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
        except OSError as exc:
            raise TemplateStoreError(f"行业模板存储文件写入失败：{exc}") from exc
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    def _detail(self, template_id: str, content: dict, origin: str, customized: bool) -> dict:
        detail = {"id": template_id, **copy.deepcopy(content), "origin": origin, "customized": customized}
        detail["counts"] = {
            "entities": len(detail.get("entities", {})),
            "relationships": len(detail.get("relationships", [])),
            "metrics": len(detail.get("metrics", {})),
            "aliases": len(detail.get("aliases", {})),
        }
        return detail

    def _get_from_data(self, template_id: str, data: dict) -> dict:
        if template_id in self.builtins:
            content = data["overrides"].get(template_id, self.builtins[template_id])
            return self._detail(template_id, content, "builtin", template_id in data["overrides"])
        if template_id in data["custom"]:
            return self._detail(template_id, data["custom"][template_id], "custom", False)
        raise TemplateNotFoundError(f"模板不存在：{template_id}")

    def _summary(self, detail: dict) -> dict:
        return {key: copy.deepcopy(detail[key]) for key in ("id", "name", "description", "origin", "customized", "counts")}

    def list(self) -> list[dict]:
        data = self._load_data()
        template_ids = list(self.builtins) + [item for item in data["custom"] if item not in self.builtins]
        return [self._summary(self._get_from_data(item, data)) for item in template_ids]

    def get(self, template_id: str) -> dict:
        return self._get_from_data(template_id, self._load_data())

    def parse_upload(self, filename: str, content: str) -> dict:
        if len(content.encode("utf-8")) > MAX_UPLOAD_BYTES:
            raise TemplateValidationError("模板文件不能超过 2 MiB", [{"path": "content", "message": "文件过大"}])
        suffix = Path(filename).suffix.lower()
        try:
            if suffix == ".json":
                payload = json.loads(content)
            elif suffix in {".yaml", ".yml"}:
                payload = yaml.safe_load(content)
            else:
                raise TemplateValidationError("仅支持 JSON、YAML 或 YML 文件", [{"path": "filename", "message": "文件扩展名不受支持"}])
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise TemplateValidationError("模板文件解析失败", [{"path": "content", "message": str(exc)}]) from exc
        if not isinstance(payload, dict):
            raise TemplateValidationError("模板顶层必须是对象", [{"path": "content", "message": "顶层结构不是对象"}])
        return self._validate(payload).model_dump(by_alias=True, exclude_none=True)

    def create(self, payload: dict) -> dict:
        template = self._validate(payload)
        with self._lock:
            data = self._load_data()
            if template.id in self.builtins or template.id in data["custom"]:
                raise TemplateConflictError(f"模板 ID 已存在：{template.id}")
            data["custom"][template.id] = self._serialize_template(template)
            self._save_data(data)
        return self.get(template.id)

    def update(self, template_id: str, payload: dict) -> dict:
        template = self._validate(payload, expected_id=template_id)
        with self._lock:
            data = self._load_data()
            if template_id in self.builtins:
                data["overrides"][template_id] = self._serialize_template(template)
            elif template_id in data["custom"]:
                data["custom"][template_id] = self._serialize_template(template)
            else:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            self._save_data(data)
        return self.get(template_id)

    def delete(self, template_id: str) -> dict:
        with self._lock:
            data = self._load_data()
            if template_id in self.builtins:
                raise TemplateOperationError("内置模板不能删除")
            if template_id not in data["custom"]:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            del data["custom"][template_id]
            self._save_data(data)
        return {"deleted": template_id}

    def reset(self, template_id: str) -> dict:
        with self._lock:
            data = self._load_data()
            if template_id in data["custom"]:
                raise TemplateOperationError("自定义模板没有预置版本")
            if template_id not in self.builtins:
                raise TemplateNotFoundError(f"模板不存在：{template_id}")
            data["overrides"].pop(template_id, None)
            self._save_data(data)
        return self.get(template_id)
```

`get()` must inject `id`, `origin`, `customized`, and `counts`. `parse_upload()` must select the parser only from the lower-cased filename suffix and never save. Each mutating operation must reload the latest file while holding the lock.

- [x] **Step 6: Run store tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_store -v
```

Expected: all Task 1 tests pass.

- [x] **Step 7: Review changes without committing**

Run:

```bash
git diff -- app/template_models.py app/template_store.py requirements-dev.txt tests/test_template_store.py
git status --short
```

Expected: only local uncommitted changes; no Git commit is created.

---

### Task 2: Safe Apply Preview and Execution

**Files:**
- Create: `app/template_apply.py`
- Create: `tests/test_template_apply.py`

**Interfaces:**
- Consumes: normalized detail dictionaries from `TemplateStore.get()`.
- Consumes registry attributes/methods: `ontology`, `metrics`, `save_entity()`, `save_relationships()`, and `add_metric()`.
- Consumes alias-store methods: `get_all()` and `set_aliases()`.
- Produces: `TemplateApplier.preview(template: dict) -> dict` and `TemplateApplier.apply(template: dict) -> dict`.

- [x] **Step 1: Write failing safe-merge tests**

Use in-memory fake registry and alias classes. Assert these behaviors:

```python
class TemplateApplierTest(unittest.TestCase):
    def test_preview_reports_additions_and_skips_without_mutation(self):
        before = copy.deepcopy(self.registry.ontology)
        result = self.applier.preview(TEMPLATE)
        self.assertIn("ProductionRecord", result["added"]["entities"])
        self.assertEqual(result["skipped"]["entities"][0]["name"], "Machine")
        self.assertEqual(self.registry.ontology, before)

    def test_apply_preserves_existing_values_and_relationships(self):
        result = self.applier.apply(TEMPLATE)
        self.assertTrue(result["applied"])
        self.assertEqual(self.registry.ontology["entities"]["Machine"]["description"], "existing")
        self.assertIn(EXISTING_RELATIONSHIP, self.registry.ontology["relationships"])
        self.assertEqual(self.registry.metrics["metrics"]["energy_consumption"]["expression"], "existing_expr")
        self.assertEqual(self.aliases.get_all()["aliases"]["设备编号"], "existing_field")

    def test_preview_and_apply_have_identical_counts(self):
        preview = self.applier.preview(TEMPLATE)
        applied = self.applier.apply(TEMPLATE)
        self.assertEqual(preview["counts"], applied["counts"])
```

- [x] **Step 2: Run apply tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_apply -v
```

Expected: import failure because `app.template_apply` does not exist.

- [x] **Step 3: Implement one shared analysis path**

Implement `TemplateApplier` so both public methods call `_analyze(template)`. Use these keys:

```python
def relationship_key(rel: dict) -> tuple[str, str, str]:
    return rel["from"], rel["relation"], rel["to"]

def relationship_label(rel: dict) -> str:
    return f'{rel["from"]}-{rel["relation"]}-{rel["to"]}'

class TemplateApplier:
    def preview(self, template: dict) -> dict:
        analysis, _ = self._analyze(template)
        return analysis

    def apply(self, template: dict) -> dict:
        result, pending = self._analyze(template)
        for name in pending["entities"]:
            self.registry.save_entity(name, copy.deepcopy(template["entities"][name]))
        if pending["relationships"]:
            merged = copy.deepcopy(self.registry.ontology.get("relationships", []))
            merged.extend(copy.deepcopy(pending["relationships"]))
            self.registry.save_relationships(merged)
        for name in pending["metrics"]:
            self.registry.add_metric(self._metric_model(name, template["metrics"][name]))
        if pending["aliases"]:
            self.alias_store.set_aliases(pending["aliases"])
        return {**result, "applied": True}
```

All skipped entries must have `name` and `reason`. Added entries must be stable display names. Counts must be derived from the final result lists, not separately maintained counters.

- [x] **Step 4: Run apply tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_apply -v
```

Expected: all Task 2 tests pass.

- [x] **Step 5: Review changes without committing**

Run `git diff -- app/template_apply.py tests/test_template_apply.py` and confirm no commit was created.

---

### Task 3: FastAPI Template Management Endpoints

**Files:**
- Modify: `app/main.py`
- Create: `tests/test_template_api.py`

**Interfaces:**
- Consumes: `TemplateStore` and `TemplateApplier` from Tasks 1–2.
- Produces exact routes: `GET /templates`, `POST /templates`, `POST /templates/validate`, `GET /templates/{id}`, `PUT /templates/{id}`, `DELETE /templates/{id}`, `POST /templates/{id}/reset`, `GET /templates/{id}/apply-preview`, and `POST /templates/{id}/apply`.

- [x] **Step 1: Install the development test dependency**

Run:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

Expected: compatible `httpx` is installed into the project virtual environment.

- [x] **Step 2: Write failing HTTP tests**

Use `fastapi.testclient.TestClient`, a temporary `TemplateStore`, and `unittest.mock.patch.object()` on `app.main.template_store` and `app.main.template_applier`. Cover:

```python
def test_template_crud_and_reset(self):
    self.assertEqual(self.client.get("/templates").status_code, 200)
    created = self.client.post("/templates", json=template_payload("custom-one"))
    self.assertEqual(created.status_code, 201)
    conflict = self.client.post("/templates", json=template_payload("custom-one"))
    self.assertEqual(conflict.status_code, 409)
    updated = self.client.put("/templates/custom-one", json=template_payload("custom-one", name="修改"))
    self.assertEqual(updated.json()["name"], "修改")
    self.assertEqual(self.client.delete("/templates/custom-one").status_code, 200)
    self.assertEqual(self.client.delete("/templates/manufacturing").status_code, 400)

def test_upload_validation_and_not_found_statuses(self):
    valid = self.client.post("/templates/validate", json={"filename": "one.yaml", "content": YAML_TEXT})
    self.assertEqual(valid.status_code, 200)
    invalid = self.client.post("/templates/validate", json={"filename": "one.txt", "content": "x"})
    self.assertEqual(invalid.status_code, 400)
    self.assertEqual(self.client.get("/templates/missing").status_code, 404)

def test_apply_preview_and_apply_routes(self):
    preview = self.client.get("/templates/manufacturing/apply-preview")
    applied = self.client.post("/templates/manufacturing/apply")
    self.assertEqual(preview.status_code, 200)
    self.assertTrue(applied.json()["applied"])
```

- [x] **Step 3: Run API tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_api -v
```

Expected: failures for missing management routes or old response shapes.

- [x] **Step 4: Replace the old static-template route block**

Initialize services near the existing global stores:

```python
template_store = TemplateStore()
template_applier = TemplateApplier(registry, alias_store)
```

Add one error translator:

```python
def raise_template_http_error(exc: TemplateStoreError) -> None:
    if isinstance(exc, TemplateNotFoundError):
        status = 404
    elif isinstance(exc, TemplateConflictError):
        status = 409
    else:
        status = 400
    raise HTTPException(status_code=status, detail={"message": str(exc), "errors": getattr(exc, "errors", [])})
```

Routes must accept raw `dict` bodies and call `TemplateStore` validation so invalid template bodies return the designed `400` response rather than FastAPI's default `422`. `POST /templates` must return status `201`.

- [x] **Step 5: Run API and existing smoke tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_template_api -v
.venv/bin/python tests/smoke_test.py
```

Expected: API tests pass and output ends with `SMOKE TEST PASSED`.

- [x] **Step 6: Review changes without committing**

Run `git diff -- app/main.py tests/test_template_api.py` and confirm only intended local edits.

---

### Task 4: Frontend Shell, Navigation, and Styling

**Files:**
- Modify: `app/static/index.html`
- Create: `app/static/template-management.css`
- Create: `tests/test_template_ui.py`

**Interfaces:**
- Produces DOM IDs used by the script: `panel-templates`, `template-search`, `template-grid`, `template-drawer-root`, `template-modal-root`, and `template-file-input`.
- Produces navigation callback `loadTemplates()` supplied by Task 5.

- [x] **Step 1: Write failing static UI structure tests**

```python
class TemplateUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = Path("app/static/index.html").read_text(encoding="utf-8")

    def test_template_navigation_and_panel_exist(self):
        self.assertIn('data-panel="templates"', self.html)
        self.assertIn('id="panel-templates"', self.html)
        self.assertIn('id="template-grid"', self.html)

    def test_template_assets_are_loaded(self):
        self.assertIn('/static/template-management.css', self.html)
        self.assertIn('/static/template-management.js', self.html)
```

- [x] **Step 2: Run UI tests and verify RED**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: missing navigation, panel, and asset assertions fail.

- [x] **Step 3: Add the template page shell**

Add the stylesheet `<link>` after the viewport meta element, a navigation item before System Management, the panel after Candidates, and an external script before `</body>`. The panel markup must include:

```html
<div class="panel" id="panel-templates">
  <div class="template-toolbar">
    <div><h3>行业模板</h3><p>快速创建和应用可复用的行业语义模型</p></div>
    <div class="template-toolbar-actions">
      <button class="btn btn-outline" onclick="openTemplateUpload()">📤 上传模板</button>
      <button class="btn btn-primary" onclick="openTemplateEditor()">＋ 新建模板</button>
      <input type="file" id="template-file-input" accept=".json,.yaml,.yml" hidden onchange="handleTemplateFile(event)">
    </div>
  </div>
  <input id="template-search" class="template-search" placeholder="搜索模板 ID、名称或描述" oninput="filterTemplates()">
  <div id="template-grid" class="template-grid"><div class="loading">加载中…</div></div>
  <div id="template-drawer-root"></div>
  <div id="template-modal-root"></div>
</div>
```

Extend the `titles` object and panel-change handler with `templates: '行业模板'` and `if (panel === 'templates') loadTemplates();`.

- [x] **Step 4: Add focused responsive CSS**

Implement named classes for toolbar, grid, cards, badges, stat chips, fixed drawer/backdrop, modal, tabs, repeated editor rows, upload drop area, validation errors, result groups, empty state, and toast. At widths below `760px`, use one grid column, make the drawer full width, stack toolbar actions, and make modal content edge-to-edge.

- [x] **Step 5: Run UI tests and verify GREEN for the shell**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: Task 4 structure assertions pass; tests introduced by later tasks may still be absent.

---

### Task 5: Template Cards and Detail Drawer

**Files:**
- Create: `app/static/template-management.js`
- Modify: `tests/test_template_ui.py`

**Interfaces:**
- Consumes DOM from Task 4 and template management API from Task 3.
- Produces global functions `loadTemplates()`, `filterTemplates()`, `openTemplateDetails(id)`, `closeTemplateDrawer()`, `escapeTemplateHtml(value)`, and `templateApi(url, options)`.

- [x] **Step 1: Write failing JavaScript contract tests**

Read `template-management.js` as text and assert it contains definitions for all six public functions, uses `textContent` or `escapeTemplateHtml`, and never interpolates unescaped template description/name values into markup.

- [x] **Step 2: Run UI tests and verify RED**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: script file or required function assertions fail.

- [x] **Step 3: Implement API and safe rendering helpers**

```javascript
let templateItems = [];
let activeTemplate = null;

function escapeTemplateHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
}

async function templateApi(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || body;
    const error = new Error(detail.message || '请求失败');
    error.validationErrors = detail.errors || [];
    throw error;
  }
  return body;
}
```

- [x] **Step 4: Implement list, filter, card, and drawer behavior**

`loadTemplates()` fetches `/templates`, renders cards, and preserves search text. `filterTemplates()` matches lowercase ID/name/description. Cards render origin/customized badges, four count chips, details, and apply buttons. The drawer fetches `/templates/{id}` and renders tab-like sections with escaped text. Drawer actions are determined from `origin` and `customized`.

- [x] **Step 5: Run UI tests and verify GREEN**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: all current UI contract tests pass.

---

### Task 6: Structured Editor, Upload Preview, Reset, and Delete

**Files:**
- Modify: `app/static/template-management.js`
- Modify: `tests/test_template_ui.py`

**Interfaces:**
- Produces global functions `openTemplateEditor(templateId)`, `openTemplateUpload()`, `handleTemplateFile(event)`, `saveTemplate()`, `resetTemplate(id)`, and `deleteTemplate(id)`.
- Internal form serializer produces the exact `IndustryTemplate` JSON shape from Task 1.

- [x] **Step 1: Add failing editor/upload contract tests**

Assert the script defines the six functions, accepts `.json,.yaml,.yml`, checks `2 * 1024 * 1024`, calls `/templates/validate`, and uses `PUT` for edit versus `POST` for create.

- [x] **Step 2: Run UI tests and verify RED**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: missing editor and upload function assertions fail.

- [x] **Step 3: Implement reusable modal and editor state**

Use a single state object:

```javascript
let templateEditorState = {
  mode: 'create',
  originalId: null,
  activeTab: 'basic',
  draft: null,
  validationErrors: []
};
```

Render five tabs: basic, entities, relationships, metrics, aliases. Each repeated row has add/remove controls and stable `data-*` indices. Update the in-memory draft from input events before changing tabs so no edits are lost. Lock ID in edit mode.

- [x] **Step 4: Implement upload validation and preview**

`openTemplateUpload()` clicks the hidden file input. `handleTemplateFile()` validates extension/size, reads with `File.text()`, posts `{filename, content}` to `/templates/validate`, then renders summary counts and “确认创建” / “进入编辑” actions. It must clear the input value after handling so the same file can be selected again.

- [x] **Step 5: Implement save, reset, and delete flows**

`saveTemplate()` serializes the draft, validates it, then calls `POST /templates` with expected `201` for create or `PUT /templates/{id}` for edit. `resetTemplate()` and `deleteTemplate()` show explicit confirmation dialogs, call their endpoints, close stale views, reload cards, and show a toast. No delete action is rendered for built-ins.

- [x] **Step 6: Run UI tests and verify GREEN**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: all editor/upload contract tests pass.

---

### Task 7: Apply Preview, Confirmation, and Detailed Result

**Files:**
- Modify: `app/static/template-management.js`
- Modify: `tests/test_template_ui.py`

**Interfaces:**
- Produces global functions `previewTemplateApply(id)`, `confirmTemplateApply(id)`, `renderApplyImpact(result)`, and `renderApplyResult(result)`.

- [x] **Step 1: Add failing apply-flow contract tests**

Assert the script calls both `/templates/${id}/apply-preview` and `/templates/${id}/apply`, renders all four categories, disables the confirm button while applying, and includes a semantic-graph navigation action.

- [x] **Step 2: Run UI tests and verify RED**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: missing apply-flow assertions fail.

- [x] **Step 3: Implement real impact preview**

`previewTemplateApply(id)` fetches the backend preview and displays added/skipped count grids plus expandable skip reasons. The confirmation button must store the template ID in `data-template-id`, not interpolate it into JavaScript source.

- [x] **Step 4: Implement guarded apply and result views**

`confirmTemplateApply(id)` disables itself, posts to the apply endpoint, and replaces the modal body with detailed actual results. `renderApplyResult()` must show success summary, added lists, skipped reasons, close, and a “查看语义图谱” action that activates the existing graph navigation and calls `loadGraph()`.

- [x] **Step 5: Run all UI tests and verify GREEN**

Run `.venv/bin/python -m unittest tests.test_template_ui -v`.

Expected: all frontend structure and contract tests pass.

---

### Task 8: Documentation, Full Regression, and Browser Acceptance

**Files:**
- Modify: `README.md`
- Modify: `.gitignore` if present; otherwise create it without removing user rules.

**Interfaces:**
- Documents the implemented UI route and JSON/YAML template format.
- Ensures `.superpowers/`, `.idea/`, `.DS_Store`, `__pycache__/`, and `*.pyc` are ignored without deleting user files.

- [x] **Step 1: Update README with implemented workflow**

Document the navigation path “行业模板”, built-in/custom rules, supported upload formats, safe-merge semantics, and exact API table including validation, CRUD, reset, preview, and apply endpoints.

- [x] **Step 2: Run the full automated suite**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python tests/smoke_test.py
```

Expected: every unittest passes and smoke output ends with `SMOKE TEST PASSED`.

- [x] **Step 3: Start the application on a non-conflicting verification port**

Run:

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Expected: application startup completes and `GET http://127.0.0.1:8010/health` returns status `ok`.

- [x] **Step 4: Complete browser acceptance**

Verify in order: card list, detail drawer, built-in edit and reset, JSON upload preview, YAML upload preview, custom create/edit/delete, apply preview, apply result, graph navigation, responsive layout, and literal rendering of `<script>alert(1)</script>` as text.

- [x] **Step 5: Inspect final diff and runtime artifacts without committing**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Expected: no whitespace errors, no Git commit, no push, and only intended source/docs/test changes plus pre-existing user runtime files.
