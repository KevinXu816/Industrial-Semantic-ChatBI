import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "app" / "static" / "index.html"
CSS_PATH = ROOT / "app" / "static" / "template-management.css"
SCRIPT_PATH = ROOT / "app" / "static" / "template-management.js"
GRAPH_EDITOR_PATH = ROOT / "app" / "static" / "graph-editor.html"


class TemplateUiShellTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_PATH.read_text(encoding="utf-8")

    def test_template_navigation_and_panel_exist(self):
        self.assertIn('data-panel="templates"', self.html)
        self.assertIn('id="panel-templates"', self.html)
        self.assertIn('id="template-search"', self.html)
        self.assertIn('id="template-grid"', self.html)
        self.assertIn('id="template-drawer-root"', self.html)
        self.assertIn('id="template-modal-root"', self.html)
        self.assertIn('id="template-file-input"', self.html)

    def test_template_assets_are_loaded(self):
        self.assertIn('/static/template-management.css', self.html)
        self.assertIn('/static/template-management.js', self.html)

    def test_template_panel_is_connected_to_navigation_loader(self):
        self.assertIn("templates: '行业模板'", self.html)
        self.assertIn("if (panel === 'templates') loadTemplates();", self.html)

    def test_applied_entity_and_metric_names_are_not_put_in_inline_handlers(self):
        unsafe_fragments = (
            "showEntityForm('${escapeAttr(n.id)}')",
            "saveEntity('${escapeAttr(editName || '')}')",
            "showMetricForm('${escapeAttr(name)}')",
            "deleteMetric('${escapeAttr(name)}')",
        )
        for fragment in unsafe_fragments:
            self.assertNotIn(fragment, self.html)
        self.assertIn('data-entity-edit-index="${nodeIndex}"', self.html)
        self.assertIn('data-metric-edit-index="${metricIndex}"', self.html)
        self.assertIn('data-metric-delete-index="${metricIndex}"', self.html)

    def test_template_stylesheet_contains_layout_primitives(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        for selector in (
            ".template-toolbar",
            ".template-grid",
            ".template-card",
            ".template-drawer",
            ".template-modal",
            ".template-editor-tabs",
            ".template-toast",
        ):
            self.assertIn(selector, css)
        self.assertIn("@media (max-width: 760px)", css)

    def test_template_dialogs_are_named_and_keyboard_managed(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('aria-labelledby="template-modal-title"', script)
        self.assertIn('id="template-modal-title"', script)
        self.assertIn("function handleTemplateDialogKeydown", script)
        self.assertIn("event.key === 'Escape'", script)
        self.assertIn("event.key === 'Tab'", script)
        self.assertIn("function restoreTemplateDialogFocus", script)
        self.assertIn("templateDialogOpenRoots", script)

    def test_template_search_and_editor_tabs_have_accessible_names(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('aria-label="搜索行业模板"', self.html)
        self.assertIn('role="tablist"', script)
        self.assertIn('role="tab"', script)
        self.assertIn('aria-selected=', script)
        self.assertIn('role="tabpanel"', script)

    def test_mobile_template_panel_compacts_the_existing_sidebar(self):
        css = CSS_PATH.read_text(encoding="utf-8")
        self.assertIn("body:has(#panel-templates.active) .sidebar", css)
        self.assertIn("width: 56px", css)
        self.assertIn("body:has(#panel-templates.active) .content", css)


class TemplateBrowserScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_browser_and_api_functions_exist(self):
        for function_name in (
            "loadTemplates",
            "filterTemplates",
            "openTemplateDetails",
            "closeTemplateDrawer",
            "escapeTemplateHtml",
            "templateApi",
        ):
            self.assertIn(f"function {function_name}", self.script)

    def test_template_api_preserves_field_level_errors(self):
        self.assertIn("error.validationErrors", self.script)
        self.assertIn("detail.errors", self.script)

    def test_user_controlled_card_and_detail_text_is_escaped(self):
        for expression in (
            "escapeTemplateHtml(item.name)",
            "escapeTemplateHtml(item.description)",
            "escapeTemplateHtml(template.name)",
            "escapeTemplateHtml(template.description)",
        ):
            self.assertIn(expression, self.script)
        self.assertIn("encodeURIComponent(templateId)", self.script)

    def test_card_actions_use_data_attributes_instead_of_inline_ids(self):
        self.assertIn('data-action="details"', self.script)
        self.assertIn('data-action="apply"', self.script)
        self.assertIn("templateGridClick", self.script)

    def test_graph_editor_uses_dom_apis_for_applied_template_text(self):
        graph_editor = GRAPH_EDITOR_PATH.read_text(encoding="utf-8")
        self.assertIn("document.createElementNS", graph_editor)
        self.assertNotIn("tmp.innerHTML", graph_editor)
        self.assertIn("fromLabel.textContent = from", graph_editor)
        self.assertIn("toLabel.textContent = to", graph_editor)
        self.assertIn("relationInput.value = currentRel", graph_editor)
        self.assertNotIn("confirmAddRelation('${from}','${to}')", graph_editor)
        self.assertNotIn("confirmEditRelation(${index},'${from}','${to}')", graph_editor)


class TemplateEditorScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_PATH.read_text(encoding="utf-8")
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_editor_upload_reset_and_delete_functions_exist(self):
        for function_name in (
            "openTemplateEditor",
            "openTemplateUpload",
            "handleTemplateFile",
            "saveTemplate",
            "resetTemplate",
            "deleteTemplate",
        ):
            self.assertIn(f"function {function_name}", self.script)

    def test_upload_checks_supported_extensions_and_two_mib_limit(self):
        self.assertIn('accept=".json,.yaml,.yml"', self.html)
        self.assertIn("2 * 1024 * 1024", self.script)
        self.assertIn("new TextDecoder('utf-8', { fatal: true })", self.script)
        self.assertIn("await file.arrayBuffer()", self.script)
        self.assertIn("'/templates/validate'", self.script)

    def test_upload_supports_drag_and_drop(self):
        self.assertIn('data-upload-dropzone', self.script)
        self.assertIn("function handleTemplateDragOver", self.script)
        self.assertIn("function handleTemplateDrop", self.script)
        self.assertIn("processTemplateFile(file)", self.script)

    def test_async_editor_operations_have_in_flight_guards(self):
        self.assertIn("let templateValidationInFlight = false", self.script)
        self.assertIn("let templateOperationInFlight = false", self.script)
        self.assertIn("if (templateValidationInFlight) return null", self.script)
        self.assertIn("if (templateOperationInFlight) return", self.script)
        self.assertIn("function runTemplateControlAction", self.script)
        self.assertIn("control.disabled = true", self.script)
        wrapper_start = self.script.index("function runTemplateControlAction")
        action_position = self.script.index("const result = action()", wrapper_start)
        disable_position = self.script.index("control.disabled = true", wrapper_start)
        self.assertLess(action_position, disable_position)

    def test_editor_has_all_structured_sections(self):
        for tab_name in ("basic", "entities", "relationships", "metrics", "aliases"):
            self.assertIn(f"'{tab_name}'", self.script)
        for action in (
            'data-action="add-entity"',
            'data-action="add-relationship"',
            'data-action="add-metric"',
            'data-action="add-alias"',
        ):
            self.assertIn(action, self.script)

    def test_save_uses_post_for_create_and_put_for_edit(self):
        self.assertIn("templateEditorState.mode === 'edit' ? 'PUT' : 'POST'", self.script)
        self.assertIn("JSON.stringify(validation.template)", self.script)

    def test_save_is_guarded_before_async_validation(self):
        self.assertIn("let templateSaveInFlight = false", self.script)
        guard_position = self.script.index("templateSaveInFlight = true")
        validation_position = self.script.index(
            "await validateTemplateEditorDraft()",
            self.script.index("async function saveTemplate"),
        )
        self.assertLess(guard_position, validation_position)

    def test_editor_renders_backend_validation_errors_safely(self):
        self.assertIn("templateEditorState.validationErrors", self.script)
        self.assertIn("escapeTemplateHtml(error.path)", self.script)
        self.assertIn("escapeTemplateHtml(error.message)", self.script)
        self.assertIn("function templateFieldErrorsHtml", self.script)
        self.assertIn('class="template-field-error"', self.script)
        for path in (
            "'id'",
            "`relationships.${index}.from`",
            "`metrics.${name}.expression`",
            "`entities.${name}.properties.${propertyName}.type`",
        ):
            self.assertIn(path, self.script)

    def test_entity_capture_only_selects_editor_rows(self):
        self.assertIn(
            "querySelectorAll('.template-editor-row[data-entity-index]')",
            self.script,
        )

    def test_duplicate_editor_rows_are_preserved_while_showing_errors(self):
        self.assertIn("let commitCapture = () => {};", self.script)
        self.assertIn("function showTemplateEditorErrorsInPlace", self.script)
        self.assertIn("function duplicateErrorTarget", self.script)
        self.assertIn("data-capture-error", self.script)
        self.assertIn("showTemplateEditorErrorsInPlace();", self.script)
        self.assertIn(
            "querySelectorAll('.template-property-row[data-property-index]')",
            self.script,
        )

    def test_reset_and_delete_call_expected_endpoints(self):
        self.assertIn("/reset`", self.script)
        self.assertIn("method: 'DELETE'", self.script)


class TemplateApplyScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_apply_preview_and_result_functions_exist(self):
        for function_name in (
            "previewTemplateApply",
            "confirmTemplateApply",
            "renderApplyImpact",
            "renderApplyResult",
        ):
            self.assertIn(f"function {function_name}", self.script)

    def test_apply_flow_calls_preview_and_apply_endpoints(self):
        self.assertIn("/apply-preview`", self.script)
        self.assertIn("/apply`", self.script)
        self.assertIn("confirmButton.disabled = true", self.script)

    def test_apply_views_render_all_categories_and_skip_reasons(self):
        for category in ("entities", "relationships", "metrics", "aliases"):
            self.assertIn(f"['{category}'", self.script)
        self.assertIn("item.reason", self.script)
        self.assertIn("escapeTemplateHtml(item.reason)", self.script)

    def test_apply_result_offers_semantic_graph_navigation(self):
        self.assertIn('data-action="view-graph"', self.script)
        self.assertIn("openSemanticGraphFromTemplate", self.script)


if __name__ == "__main__":
    unittest.main()
