/* Industry template management UI. */

let templateItems = [];
let activeTemplate = null;
const templateDialogReturnFocus = new Map();
const templateDialogOpenRoots = new Set();


function escapeTemplateHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;',
  })[character]);
}


async function templateApi(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail || body;
    const error = new Error(detail.message || '请求失败');
    error.validationErrors = detail.errors || [];
    error.status = response.status;
    throw error;
  }
  return body;
}


function templateBadgeHtml(item) {
  const badges = [];
  if (item.origin === 'builtin') {
    badges.push('<span class="template-badge template-badge-builtin">内置</span>');
  } else {
    badges.push('<span class="template-badge template-badge-custom">自定义</span>');
  }
  if (item.customized) {
    badges.push('<span class="template-badge template-badge-modified">已修改</span>');
  }
  return badges.join('');
}


function templateStatsHtml(counts = {}) {
  const definitions = [
    ['entities', '实体'],
    ['relationships', '关系'],
    ['metrics', '指标'],
    ['aliases', '别名'],
  ];
  return definitions.map(([key, label]) => `
    <div class="template-stat">
      <strong>${Number(counts[key] || 0)}</strong>
      <span>${label}</span>
    </div>`).join('');
}


function renderTemplateCards(items) {
  const grid = document.getElementById('template-grid');
  if (!grid) return;
  if (!items.length) {
    grid.innerHTML = `
      <div class="template-empty">
        <div style="font-size:30px;margin-bottom:8px">🏭</div>
        <strong>没有找到行业模板</strong>
        <p style="margin-top:6px">尝试更换搜索条件，或上传一个新模板。</p>
      </div>`;
    return;
  }
  grid.innerHTML = items.map(item => {
    const safeId = escapeTemplateHtml(item.id);
    return `
      <article class="template-card" data-template-id="${safeId}">
        <div class="template-card-header">
          <div class="template-card-title">
            <div class="template-card-icon" aria-hidden="true">🏭</div>
            <div>
              <h4>${escapeTemplateHtml(item.name)}</h4>
              <div class="template-card-id">${safeId}</div>
            </div>
          </div>
          <div class="template-badges">${templateBadgeHtml(item)}</div>
        </div>
        <p class="template-card-description">${escapeTemplateHtml(item.description)}</p>
        <div class="template-stats">${templateStatsHtml(item.counts)}</div>
        <div class="template-card-actions">
          <button class="btn btn-outline" data-action="details" data-template-id="${safeId}">查看详情</button>
          <button class="btn btn-primary" data-action="apply" data-template-id="${safeId}">应用</button>
        </div>
      </article>`;
  }).join('');
}


async function loadTemplates() {
  const grid = document.getElementById('template-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="loading">加载中…</div>';
  try {
    templateItems = await templateApi('/templates');
    filterTemplates();
  } catch (error) {
    grid.innerHTML = `<div class="error-msg">${escapeTemplateHtml(error.message)}</div>`;
  }
}


function filterTemplates() {
  const input = document.getElementById('template-search');
  const query = (input ? input.value : '').trim().toLocaleLowerCase();
  const filtered = !query ? templateItems : templateItems.filter(item => (
    `${item.id} ${item.name} ${item.description}`.toLocaleLowerCase().includes(query)
  ));
  renderTemplateCards(filtered);
}


function runTemplateControlAction(control, action) {
  if (control.disabled) return;
  try {
    const result = action();
    control.disabled = true;
    Promise.resolve(result)
      .catch(error => showTemplateToast(error.message || '请求失败', true))
      .finally(() => {
        if (control.isConnected) control.disabled = false;
      });
  } catch (error) {
    showTemplateToast(error.message || '请求失败', true);
  }
}


function templateGridClick(event) {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const templateId = button.dataset.templateId;
  if (button.dataset.action === 'details') {
    runTemplateControlAction(button, () => openTemplateDetails(templateId));
  } else if (button.dataset.action === 'apply') {
    runTemplateControlAction(button, () => previewTemplateApply(templateId));
  }
}


function detailItemsHtml(items, renderer) {
  const entries = Object.entries(items || {});
  if (!entries.length) return '<p class="template-detail-summary">暂无内容</p>';
  return entries.map(([name, config]) => renderer(name, config)).join('');
}


function templateDetailBodyHtml(template) {
  const entities = detailItemsHtml(template.entities, (name, config) => `
    <div class="template-detail-item">
      <strong>${escapeTemplateHtml(name)}</strong>
      <p>${escapeTemplateHtml(config.description || '')} · ${Object.keys(config.properties || {}).length} 个属性</p>
    </div>`);
  const relationships = (template.relationships || []).length
    ? template.relationships.map(relationship => `
        <div class="template-detail-item">
          <strong>${escapeTemplateHtml(relationship.from)} → ${escapeTemplateHtml(relationship.to)}</strong>
          <p>${escapeTemplateHtml(relationship.relation)} · 关联字段 ${escapeTemplateHtml(relationship.on)}</p>
        </div>`).join('')
    : '<p class="template-detail-summary">暂无内容</p>';
  const metrics = detailItemsHtml(template.metrics, (name, config) => `
    <div class="template-detail-item">
      <strong>${escapeTemplateHtml(name)}</strong>
      <p>${escapeTemplateHtml(config.description || '')}</p>
      <p class="template-detail-code">${escapeTemplateHtml(config.expression || '')}${config.unit ? ` · ${escapeTemplateHtml(config.unit)}` : ''}</p>
    </div>`);
  const aliases = detailItemsHtml(template.aliases, (name, fieldName) => `
    <div class="template-detail-item">
      <strong>${escapeTemplateHtml(name)}</strong>
      <p class="template-detail-code">→ ${escapeTemplateHtml(fieldName)}</p>
    </div>`);

  return `
    <p class="template-detail-summary">${escapeTemplateHtml(template.description)}</p>
    <div class="template-stats">${templateStatsHtml(template.counts)}</div>
    <section class="template-detail-section"><h4>实体 <span>${template.counts.entities}</span></h4>${entities}</section>
    <section class="template-detail-section"><h4>关系 <span>${template.counts.relationships}</span></h4>${relationships}</section>
    <section class="template-detail-section"><h4>指标 <span>${template.counts.metrics}</span></h4>${metrics}</section>
    <section class="template-detail-section"><h4>别名 <span>${template.counts.aliases}</span></h4>${aliases}</section>`;
}


function templateDrawerFooterHtml(template) {
  const safeId = escapeTemplateHtml(template.id);
  const secondary = [];
  if (template.origin === 'custom') {
    secondary.push(`<button class="btn btn-danger" data-action="delete" data-template-id="${safeId}">删除</button>`);
  }
  if (template.origin === 'builtin' && template.customized) {
    secondary.push(`<button class="btn btn-outline" data-action="reset" data-template-id="${safeId}">恢复预置</button>`);
  }
  return `
    ${secondary.join('')}
    <button class="btn btn-outline" data-action="edit" data-template-id="${safeId}">编辑</button>
    <button class="btn btn-primary" data-action="apply" data-template-id="${safeId}">应用模板</button>`;
}


function renderTemplateDrawer(template) {
  const root = document.getElementById('template-drawer-root');
  root.innerHTML = `
    <div class="template-overlay" data-action="close-drawer"></div>
    <aside class="template-drawer" role="dialog" aria-modal="true" aria-label="模板详情" tabindex="-1">
      <div class="template-drawer-header">
        <div>
          <h3>${escapeTemplateHtml(template.name)}</h3>
          <div class="template-card-id">${escapeTemplateHtml(template.id)}</div>
          <div class="template-badges" style="justify-content:flex-start;margin-top:7px">${templateBadgeHtml(template)}</div>
        </div>
        <button class="template-close" data-action="close-drawer" aria-label="关闭">×</button>
      </div>
      <div class="template-drawer-body">${templateDetailBodyHtml(template)}</div>
      <div class="template-drawer-footer">${templateDrawerFooterHtml(template)}</div>
    </aside>`;
}


async function openTemplateDetails(templateId) {
  rememberTemplateDialogFocus('template-drawer-root');
  const root = document.getElementById('template-drawer-root');
  root.innerHTML = `
    <div class="template-overlay" data-action="close-drawer"></div>
    <aside class="template-drawer"><div class="loading">加载中…</div></aside>`;
  try {
    activeTemplate = await templateApi(`/templates/${encodeURIComponent(templateId)}`);
    renderTemplateDrawer(activeTemplate);
  } catch (error) {
    root.innerHTML = `
      <div class="template-overlay" data-action="close-drawer"></div>
      <aside class="template-drawer">
        <div class="template-drawer-header"><h3>模板详情</h3><button class="template-close" data-action="close-drawer">×</button></div>
        <div class="template-drawer-body"><div class="error-msg">${escapeTemplateHtml(error.message)}</div></div>
      </aside>`;
  }
}


function closeTemplateDrawer() {
  const root = document.getElementById('template-drawer-root');
  if (root) root.innerHTML = '';
  activeTemplate = null;
  restoreTemplateDialogFocus('template-drawer-root');
}


function templateDrawerClick(event) {
  const control = event.target.closest('[data-action]');
  if (!control) return;
  const action = control.dataset.action;
  const templateId = control.dataset.templateId;
  if (action === 'close-drawer') closeTemplateDrawer();
  if (action === 'edit') runTemplateControlAction(control, () => openTemplateEditor(templateId));
  if (action === 'apply') runTemplateControlAction(control, () => previewTemplateApply(templateId));
  if (action === 'reset') runTemplateControlAction(control, () => resetTemplate(templateId));
  if (action === 'delete') runTemplateControlAction(control, () => deleteTemplate(templateId));
}


const TEMPLATE_EDITOR_TABS = [
  ['basic', '基本信息'],
  ['entities', '实体'],
  ['relationships', '关系'],
  ['metrics', '指标'],
  ['aliases', '别名'],
];
const TEMPLATE_MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
const TEMPLATE_PROPERTY_TYPES = ['string', 'number', 'integer', 'boolean', 'date', 'datetime'];

let templateEditorState = {
  mode: 'create',
  originalId: null,
  origin: 'custom',
  customized: false,
  activeTab: 'basic',
  draft: null,
  validationErrors: [],
};
let templateUploadPreview = null;
let templateSaveInFlight = false;
let templateValidationInFlight = false;
let templateOperationInFlight = false;


function emptyTemplateDraft() {
  return {
    id: '',
    name: '',
    description: '',
    entities: {
      NewEntity: {
        description: '',
        properties: { id: { type: 'string' } },
      },
    },
    relationships: [],
    metrics: {},
    aliases: {},
  };
}


function editableTemplateDraft(template) {
  return JSON.parse(JSON.stringify({
    id: template.id,
    name: template.name,
    description: template.description || '',
    entities: template.entities || {},
    relationships: template.relationships || [],
    metrics: template.metrics || {},
    aliases: template.aliases || {},
  }));
}


function closeTemplateModal() {
  const root = document.getElementById('template-modal-root');
  if (root) root.innerHTML = '';
  restoreTemplateDialogFocus('template-modal-root');
}


function showTemplateToast(message, isError = false) {
  document.querySelector('.template-toast')?.remove();
  const toast = document.createElement('div');
  toast.className = `template-toast${isError ? ' error' : ''}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  window.setTimeout(() => toast.remove(), 3200);
}


function templateModalHtml(title, body, footer = '', sizeClass = '') {
  return `
    <div class="template-modal-wrap">
      <div class="template-overlay" data-action="close-modal"></div>
      <section class="template-modal ${sizeClass}" role="dialog" aria-modal="true" aria-labelledby="template-modal-title" tabindex="-1">
        <div class="template-modal-header">
          <div><h3 id="template-modal-title">${escapeTemplateHtml(title)}</h3></div>
          <button class="template-close" data-action="close-modal" aria-label="关闭">×</button>
        </div>
        <div class="template-modal-body">${body}</div>
        ${footer ? `<div class="template-modal-footer">${footer}</div>` : ''}
      </section>
    </div>`;
}


function editorTabCount(tab) {
  const draft = templateEditorState.draft;
  if (tab === 'entities') return Object.keys(draft.entities || {}).length;
  if (tab === 'relationships') return (draft.relationships || []).length;
  if (tab === 'metrics') return Object.keys(draft.metrics || {}).length;
  if (tab === 'aliases') return Object.keys(draft.aliases || {}).length;
  return null;
}


function templateEditorTabsHtml() {
  return `<div class="template-editor-tabs" role="tablist" aria-label="模板编辑区">${TEMPLATE_EDITOR_TABS.map(([id, label]) => {
    const count = editorTabCount(id);
    const selected = templateEditorState.activeTab === id;
    return `<button id="template-editor-tab-${id}" class="template-editor-tab${selected ? ' active' : ''}" role="tab" aria-selected=${selected ? '"true"' : '"false"'} aria-controls="template-editor-panel" tabindex="${selected ? '0' : '-1'}" data-action="editor-tab" data-tab="${id}">${label}${count === null ? '' : ` <span class="count">${count}</span>`}</button>`;
  }).join('')}</div>`;
}


function templateValidationErrorsHtml() {
  if (!templateEditorState.validationErrors.length) return '';
  return `<div class="template-validation-errors"><strong>请修正以下问题：</strong><ul>${templateEditorState.validationErrors.map(error => `
    <li><span class="template-detail-code">${escapeTemplateHtml(error.path)}</span>：${escapeTemplateHtml(error.message)}</li>`).join('')}</ul></div>`;
}


function templateFieldErrorsHtml(...paths) {
  const errors = templateEditorState.validationErrors.filter(error => (
    paths.includes(String(error.path || ''))
  ));
  return errors.map(error => (
    `<div class="template-field-error">${escapeTemplateHtml(error.message)}</div>`
  )).join('');
}


function renderBasicEditor() {
  const draft = templateEditorState.draft;
  return `
    <div class="template-form-grid">
      <div class="template-form-field">
        <label>模板 ID *</label>
        <input data-editor-field="id" value="${escapeTemplateHtml(draft.id)}" ${templateEditorState.mode === 'edit' ? 'disabled' : ''} placeholder="automotive-parts">
        ${templateFieldErrorsHtml('id')}
        <div class="template-field-help">只允许小写字母、数字和连字符，创建后不可修改。</div>
      </div>
      <div class="template-form-field">
        <label>模板名称 *</label>
        <input data-editor-field="name" value="${escapeTemplateHtml(draft.name)}" placeholder="汽车零部件">
        ${templateFieldErrorsHtml('name')}
      </div>
      <div class="template-form-field full">
        <label>模板描述</label>
        <textarea data-editor-field="description" placeholder="说明模板适用行业和包含的业务对象">${escapeTemplateHtml(draft.description)}</textarea>
        ${templateFieldErrorsHtml('description')}
      </div>
    </div>
    ${templateEditorState.mode === 'edit' && templateEditorState.origin === 'builtin'
      ? '<div class="template-upload-preview">内置模板的修改将保存为用户覆盖版本，预置内容不会被删除。</div>'
      : ''}`;
}


function propertyTypeOptions(selected) {
  return TEMPLATE_PROPERTY_TYPES.map(type => `<option value="${type}"${type === selected ? ' selected' : ''}>${type}</option>`).join('');
}


function renderEntitiesEditor() {
  const entries = Object.entries(templateEditorState.draft.entities || {});
  return `
    ${templateFieldErrorsHtml('entities')}
    <div class="template-editor-list">
      ${entries.map(([name, entity], entityIndex) => `
        <div class="template-editor-row" data-entity-index="${entityIndex}">
          <div class="template-editor-row-header">
            <span class="template-editor-row-title">实体 ${entityIndex + 1}</span>
            <button class="template-remove-btn" data-action="remove-entity" data-index="${entityIndex}">删除实体</button>
          </div>
          <div class="template-form-grid">
            <div class="template-form-field"><label>实体名称 *</label><input data-entity-field="name" value="${escapeTemplateHtml(name)}">${templateFieldErrorsHtml(`entities.${entityIndex}`)}</div>
            <div class="template-form-field"><label>描述</label><input data-entity-field="description" value="${escapeTemplateHtml(entity.description || '')}"></div>
          </div>
          <div class="template-field-help">属性</div>
          ${templateFieldErrorsHtml(`entities.${name}.properties`)}
          <div class="template-properties">${Object.entries(entity.properties || {}).map(([propertyName, property], propertyIndex) => `
            <div class="template-property-row" data-property-index="${propertyIndex}">
              <div class="template-form-field"><label>属性名 *</label><input data-property-field="name" value="${escapeTemplateHtml(propertyName)}"></div>
              <div class="template-form-field"><label>类型</label><select data-property-field="type">${propertyTypeOptions(property.type)}</select>${templateFieldErrorsHtml(`entities.${name}.properties.${propertyName}.type`)}</div>
              <button class="template-remove-btn" data-action="remove-property" data-entity-index="${entityIndex}" data-property-index="${propertyIndex}">删除</button>
            </div>`).join('')}</div>
          <button class="template-add-btn" data-action="add-property" data-entity-index="${entityIndex}">＋ 添加属性</button>
        </div>`).join('')}
      <button class="template-add-btn" data-action="add-entity">＋ 添加实体</button>
    </div>`;
}


function entityOptions(selected) {
  const names = Object.keys(templateEditorState.draft.entities || {});
  const options = names.map(name => `<option value="${escapeTemplateHtml(name)}"${name === selected ? ' selected' : ''}>${escapeTemplateHtml(name)}</option>`).join('');
  return `<option value="">请选择实体</option>${options}`;
}


function renderRelationshipsEditor() {
  return `
    <div class="template-editor-list">
      ${(templateEditorState.draft.relationships || []).map((relationship, index) => `
        <div class="template-editor-row" data-relationship-index="${index}">
          <div class="template-editor-row-header"><span class="template-editor-row-title">关系 ${index + 1}</span><button class="template-remove-btn" data-action="remove-relationship" data-index="${index}">删除</button></div>
          <div class="template-form-grid">
            <div class="template-form-field"><label>起点实体 *</label><select data-relationship-field="from">${entityOptions(relationship.from)}</select>${templateFieldErrorsHtml(`relationships.${index}.from`)}</div>
            <div class="template-form-field"><label>关系名称 *</label><input data-relationship-field="relation" value="${escapeTemplateHtml(relationship.relation || '')}" placeholder="HAS_RECORD">${templateFieldErrorsHtml(`relationships.${index}.relation`)}</div>
            <div class="template-form-field"><label>终点实体 *</label><select data-relationship-field="to">${entityOptions(relationship.to)}</select>${templateFieldErrorsHtml(`relationships.${index}.to`)}</div>
            <div class="template-form-field"><label>关联字段 *</label><input data-relationship-field="on" value="${escapeTemplateHtml(relationship.on || '')}" placeholder="machine_id">${templateFieldErrorsHtml(`relationships.${index}.on`)}</div>
          </div>
        </div>`).join('')}
      <button class="template-add-btn" data-action="add-relationship">＋ 添加关系</button>
    </div>`;
}


function renderMetricsEditor() {
  return `
    <div class="template-editor-list">
      ${Object.entries(templateEditorState.draft.metrics || {}).map(([name, metric], index) => `
        <div class="template-editor-row" data-metric-index="${index}">
          <div class="template-editor-row-header"><span class="template-editor-row-title">指标 ${index + 1}</span><button class="template-remove-btn" data-action="remove-metric" data-index="${index}">删除</button></div>
          <div class="template-form-grid">
            <div class="template-form-field"><label>指标名称 *</label><input data-metric-field="name" value="${escapeTemplateHtml(name)}">${templateFieldErrorsHtml(`metrics.${index}`)}</div>
            <div class="template-form-field"><label>描述</label><input data-metric-field="description" value="${escapeTemplateHtml(metric.description || '')}"></div>
            <div class="template-form-field full"><label>表达式 *</label><input class="template-detail-code" data-metric-field="expression" value="${escapeTemplateHtml(metric.expression || '')}" placeholder="SUM(output_qty)">${templateFieldErrorsHtml(`metrics.${name}.expression`)}</div>
            <div class="template-form-field"><label>单位</label><input data-metric-field="unit" value="${escapeTemplateHtml(metric.unit || '')}"></div>
            <div class="template-form-field"><label>同义词（顿号或逗号分隔）</label><input data-metric-field="synonyms" value="${escapeTemplateHtml((metric.synonyms || []).join('、'))}"></div>
            <div class="template-form-field"><label>关联实体</label><input data-metric-field="entity" value="${escapeTemplateHtml(metric.entity || '')}"></div>
            <div class="template-form-field"><label>时间字段</label><input data-metric-field="time_field" value="${escapeTemplateHtml(metric.time_field || '')}"></div>
            <div class="template-form-field full"><label>依赖指标（顿号或逗号分隔）</label><input data-metric-field="dependencies" value="${escapeTemplateHtml((metric.dependencies || []).join('、'))}"></div>
          </div>
        </div>`).join('')}
      <button class="template-add-btn" data-action="add-metric">＋ 添加指标</button>
    </div>`;
}


function renderAliasesEditor() {
  return `
    ${templateFieldErrorsHtml('aliases')}
    <div class="template-editor-list">
      ${Object.entries(templateEditorState.draft.aliases || {}).map(([alias, fieldName], index) => `
        <div class="template-editor-row" data-alias-index="${index}">
          <div class="template-form-grid">
            <div class="template-form-field"><label>业务叫法 *</label><input data-alias-field="name" value="${escapeTemplateHtml(alias)}">${templateFieldErrorsHtml(`aliases.${index}`)}</div>
            <div class="template-form-field"><label>字段名 *</label><input data-alias-field="value" value="${escapeTemplateHtml(fieldName)}"></div>
          </div>
          <button class="template-remove-btn" data-action="remove-alias" data-index="${index}">删除别名</button>
        </div>`).join('')}
      <button class="template-add-btn" data-action="add-alias">＋ 添加别名</button>
    </div>`;
}


function templateEditorContentHtml() {
  const renderers = {
    basic: renderBasicEditor,
    entities: renderEntitiesEditor,
    relationships: renderRelationshipsEditor,
    metrics: renderMetricsEditor,
    aliases: renderAliasesEditor,
  };
  return `${templateEditorTabsHtml()}${templateValidationErrorsHtml()}<div id="template-editor-panel" role="tabpanel" aria-labelledby="template-editor-tab-${templateEditorState.activeTab}">${renderers[templateEditorState.activeTab]()}</div>`;
}


function renderTemplateEditor() {
  const root = document.getElementById('template-modal-root');
  const title = templateEditorState.mode === 'edit' ? `编辑模板 · ${templateEditorState.draft.name}` : '新建行业模板';
  const resetButton = templateEditorState.mode === 'edit' && templateEditorState.origin === 'builtin' && templateEditorState.customized
    ? `<button class="btn btn-outline" data-action="reset" data-template-id="${escapeTemplateHtml(templateEditorState.originalId)}">恢复预置</button>`
    : '';
  const footer = `
    ${resetButton}
    <button class="btn btn-outline" data-action="close-modal">取消</button>
    <button class="btn btn-outline" data-action="validate-template">校验模板</button>
    <button class="btn btn-primary" data-action="save-template">${templateEditorState.mode === 'edit' ? '保存修改' : '创建模板'}</button>`;
  root.innerHTML = templateModalHtml(title, templateEditorContentHtml(), footer);
  root.dataset.templatePreferredFocus = `#template-editor-tab-${templateEditorState.activeTab}`;
}


function uniqueDraftName(existing, prefix) {
  let candidate = prefix;
  let index = 2;
  while (existing.includes(candidate)) {
    candidate = `${prefix}${index}`;
    index += 1;
  }
  return candidate;
}


function splitTemplateList(value) {
  return value.split(/[、,，]/).map(item => item.trim()).filter(Boolean);
}


function duplicateEditorError(path, name) {
  return { path, message: `名称重复：${name || '空名称'}` };
}


function duplicateErrorTarget(root, path) {
  const [section, index, subsection, nestedIndex] = String(path || '').split('.');
  if (section === 'entities') {
    const entityRow = root.querySelector(`.template-editor-row[data-entity-index="${Number(index)}"]`);
    if (subsection === 'properties') {
      return entityRow?.querySelector(
        `.template-property-row[data-property-index="${Number(nestedIndex)}"] [data-property-field="name"]`,
      ) || null;
    }
    return entityRow?.querySelector('[data-entity-field="name"]') || null;
  }
  if (section === 'metrics') {
    return root.querySelector(`[data-metric-index="${Number(index)}"] [data-metric-field="name"]`);
  }
  if (section === 'aliases') {
    return root.querySelector(`[data-alias-index="${Number(index)}"] [data-alias-field="name"]`);
  }
  return null;
}


function showTemplateEditorErrorsInPlace() {
  const root = document.getElementById('template-modal-root');
  root.querySelector('.template-validation-errors')?.remove();
  root.querySelectorAll('[data-capture-error]').forEach(element => element.remove());
  root.querySelector('.template-editor-tabs')?.insertAdjacentHTML(
    'afterend',
    templateValidationErrorsHtml(),
  );
  templateEditorState.validationErrors.forEach(error => {
    duplicateErrorTarget(root, error.path)?.insertAdjacentHTML(
      'afterend',
      `<div class="template-field-error" data-capture-error>${escapeTemplateHtml(error.message)}</div>`,
    );
  });
}


function captureTemplateEditorDraft() {
  const root = document.getElementById('template-modal-root');
  const draft = templateEditorState.draft;
  const errors = [];
  let commitCapture = () => {};
  if (templateEditorState.activeTab === 'basic') {
    const idInput = root.querySelector('[data-editor-field="id"]');
    if (idInput && templateEditorState.mode !== 'edit') draft.id = idInput.value.trim();
    draft.name = root.querySelector('[data-editor-field="name"]')?.value.trim() || '';
    draft.description = root.querySelector('[data-editor-field="description"]')?.value.trim() || '';
  }
  if (templateEditorState.activeTab === 'entities') {
    const oldEntries = Object.entries(draft.entities || {});
    const entities = {};
    root.querySelectorAll('.template-editor-row[data-entity-index]').forEach((row, entityIndex) => {
      const name = row.querySelector('[data-entity-field="name"]').value.trim();
      if (Object.hasOwn(entities, name)) errors.push(duplicateEditorError(`entities.${entityIndex}`, name));
      const previous = oldEntries[entityIndex]?.[1] || {};
      const oldProperties = Object.entries(previous.properties || {});
      const properties = {};
      row.querySelectorAll('.template-property-row[data-property-index]').forEach((propertyRow, propertyIndex) => {
        const propertyName = propertyRow.querySelector('[data-property-field="name"]').value.trim();
        if (Object.hasOwn(properties, propertyName)) errors.push(duplicateEditorError(`entities.${entityIndex}.properties.${propertyIndex}`, propertyName));
        properties[propertyName] = {
          ...(oldProperties[propertyIndex]?.[1] || {}),
          type: propertyRow.querySelector('[data-property-field="type"]').value,
        };
      });
      entities[name] = {
        ...previous,
        description: row.querySelector('[data-entity-field="description"]').value.trim(),
        properties,
      };
    });
    commitCapture = () => { draft.entities = entities; };
  }
  if (templateEditorState.activeTab === 'relationships') {
    const previous = draft.relationships || [];
    draft.relationships = [...root.querySelectorAll('[data-relationship-index]')].map((row, index) => ({
      ...(previous[index] || {}),
      from: row.querySelector('[data-relationship-field="from"]').value,
      relation: row.querySelector('[data-relationship-field="relation"]').value.trim(),
      to: row.querySelector('[data-relationship-field="to"]').value,
      on: row.querySelector('[data-relationship-field="on"]').value.trim(),
    }));
  }
  if (templateEditorState.activeTab === 'metrics') {
    const oldEntries = Object.entries(draft.metrics || {});
    const metrics = {};
    root.querySelectorAll('[data-metric-index]').forEach((row, index) => {
      const name = row.querySelector('[data-metric-field="name"]').value.trim();
      if (Object.hasOwn(metrics, name)) errors.push(duplicateEditorError(`metrics.${index}`, name));
      const previous = oldEntries[index]?.[1] || {};
      metrics[name] = {
        ...previous,
        description: row.querySelector('[data-metric-field="description"]').value.trim(),
        expression: row.querySelector('[data-metric-field="expression"]').value.trim(),
        unit: row.querySelector('[data-metric-field="unit"]').value.trim() || null,
        synonyms: splitTemplateList(row.querySelector('[data-metric-field="synonyms"]').value),
        entity: row.querySelector('[data-metric-field="entity"]').value.trim() || null,
        time_field: row.querySelector('[data-metric-field="time_field"]').value.trim() || null,
        dependencies: splitTemplateList(row.querySelector('[data-metric-field="dependencies"]').value),
      };
    });
    commitCapture = () => { draft.metrics = metrics; };
  }
  if (templateEditorState.activeTab === 'aliases') {
    const aliases = {};
    root.querySelectorAll('[data-alias-index]').forEach((row, index) => {
      const name = row.querySelector('[data-alias-field="name"]').value.trim();
      if (Object.hasOwn(aliases, name)) errors.push(duplicateEditorError(`aliases.${index}`, name));
      aliases[name] = row.querySelector('[data-alias-field="value"]').value.trim();
    });
    commitCapture = () => { draft.aliases = aliases; };
  }
  if (errors.length) {
    templateEditorState.validationErrors = errors;
    showTemplateEditorErrorsInPlace();
    return false;
  }
  commitCapture();
  return true;
}


function editorTabForError(path) {
  const topLevel = String(path || '').split('.')[0];
  return TEMPLATE_EDITOR_TABS.some(([id]) => id === topLevel) ? topLevel : 'basic';
}


async function validateTemplateEditorDraft() {
  if (templateValidationInFlight) return null;
  templateValidationInFlight = true;
  document.querySelector('#template-modal-root [data-action="validate-template"]')?.setAttribute('disabled', '');
  try {
    if (!captureTemplateEditorDraft()) return null;
    templateEditorState.validationErrors = [];
    try {
      const validation = await templateApi('/templates/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: `${templateEditorState.draft.id || 'template'}.json`,
          content: JSON.stringify(templateEditorState.draft),
        }),
      });
      templateEditorState.draft = validation.template;
      return validation;
    } catch (error) {
      templateEditorState.validationErrors = error.validationErrors.length
        ? error.validationErrors
        : [{ path: 'template', message: error.message }];
      templateEditorState.activeTab = editorTabForError(templateEditorState.validationErrors[0].path);
      renderTemplateEditor();
      return null;
    }
  } finally {
    templateValidationInFlight = false;
    document.querySelector('#template-modal-root [data-action="validate-template"]')?.removeAttribute('disabled');
  }
}


async function openTemplateEditor(templateId = null) {
  rememberTemplateDialogFocus('template-modal-root');
  const root = document.getElementById('template-modal-root');
  if (!templateId) {
    templateEditorState = {
      mode: 'create', originalId: null, origin: 'custom', customized: false,
      activeTab: 'basic', draft: emptyTemplateDraft(), validationErrors: [],
    };
    renderTemplateEditor();
    return;
  }
  root.innerHTML = templateModalHtml('编辑模板', '<div class="loading">加载中…</div>');
  try {
    const template = await templateApi(`/templates/${encodeURIComponent(templateId)}`);
    templateEditorState = {
      mode: 'edit', originalId: template.id, origin: template.origin,
      customized: template.customized, activeTab: 'basic',
      draft: editableTemplateDraft(template), validationErrors: [],
    };
    renderTemplateEditor();
  } catch (error) {
    root.innerHTML = templateModalHtml('编辑模板', `<div class="error-msg">${escapeTemplateHtml(error.message)}</div>`, '<button class="btn btn-outline" data-action="close-modal">关闭</button>', 'template-modal-small');
  }
}


async function saveTemplate() {
  if (templateSaveInFlight) return;
  templateSaveInFlight = true;
  document.querySelector('#template-modal-root [data-action="save-template"]')?.setAttribute('disabled', '');
  try {
    const validation = await validateTemplateEditorDraft();
    if (!validation) return;
    if (templateEditorState.mode === 'create' && validation.conflict) {
      templateEditorState.validationErrors = [{ path: 'id', message: '模板 ID 已存在，请更换后再创建' }];
      templateEditorState.activeTab = 'basic';
      renderTemplateEditor();
      return;
    }
    const method = templateEditorState.mode === 'edit' ? 'PUT' : 'POST';
    const url = templateEditorState.mode === 'edit'
      ? `/templates/${encodeURIComponent(templateEditorState.originalId)}`
      : '/templates';
    const saved = await templateApi(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(validation.template),
    });
    closeTemplateModal();
    closeTemplateDrawer();
    await loadTemplates();
    showTemplateToast(templateEditorState.mode === 'edit' ? '模板修改已保存' : '模板创建成功');
    openTemplateDetails(saved.id);
  } catch (error) {
    templateEditorState.validationErrors = error.validationErrors.length
      ? error.validationErrors
      : [{ path: 'template', message: error.message }];
    renderTemplateEditor();
  } finally {
    templateSaveInFlight = false;
    document.querySelector('#template-modal-root [data-action="save-template"]')?.removeAttribute('disabled');
  }
}


function openTemplateUpload() {
  rememberTemplateDialogFocus('template-modal-root');
  templateUploadPreview = null;
  const body = `
    <div class="template-upload-zone" data-upload-dropzone tabindex="0" aria-label="拖放或选择模板文件">
      <strong>将模板文件拖放到这里</strong>
      <p>支持 UTF-8 编码的 JSON、YAML、YML，最大 2 MiB</p>
      <button class="btn btn-outline" data-action="choose-upload">选择文件</button>
    </div>`;
  document.getElementById('template-modal-root').innerHTML = templateModalHtml(
    '上传行业模板',
    body,
    '<button class="btn btn-outline" data-action="close-modal">取消</button>',
    'template-modal-medium',
  );
}


function uploadPreviewHtml(result, filename) {
  const template = result.template;
  const counts = result.counts;
  const conflictHtml = result.conflict
    ? '<div class="template-validation-errors">此模板 ID 已存在。你可以进入编辑器修改 ID，不能直接创建。</div>'
    : '<div class="template-validation-ok">✓ 文件解析成功，模板结构校验通过。</div>';
  return `
    <div class="template-upload-preview">
      <h4>${escapeTemplateHtml(template.name)}</h4>
      <p class="template-card-id">${escapeTemplateHtml(template.id)} · ${escapeTemplateHtml(filename)}</p>
      <p class="template-detail-summary" style="margin-top:8px">${escapeTemplateHtml(template.description)}</p>
      <div class="template-stats">${templateStatsHtml(counts)}</div>
      ${conflictHtml}
    </div>`;
}


async function processTemplateFile(file, input = null) {
  if (!file) return;
  const extension = file.name.toLocaleLowerCase().split('.').pop();
  if (!['json', 'yaml', 'yml'].includes(extension)) {
    showTemplateToast('仅支持 JSON、YAML 或 YML 文件', true);
    if (input) input.value = '';
    return;
  }
  if (file.size > TEMPLATE_MAX_UPLOAD_BYTES) {
    showTemplateToast('模板文件不能超过 2 MiB', true);
    if (input) input.value = '';
    return;
  }
  const root = document.getElementById('template-modal-root');
  root.innerHTML = templateModalHtml('上传模板', '<div class="loading">正在解析和校验…</div>', '', 'template-modal-medium');
  try {
    let content;
    try {
      content = new TextDecoder('utf-8', { fatal: true }).decode(
        await file.arrayBuffer(),
      );
    } catch (decodeError) {
      throw new Error('模板文件不是有效的 UTF-8 编码', { cause: decodeError });
    }
    const result = await templateApi('/templates/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, content }),
    });
    templateUploadPreview = { result, filename: file.name };
    const footer = `
      <button class="btn btn-outline" data-action="close-modal">取消</button>
      <button class="btn btn-outline" data-action="upload-edit">进入编辑</button>
      <button class="btn btn-primary" data-action="upload-create"${result.conflict ? ' disabled' : ''}>确认创建</button>`;
    root.innerHTML = templateModalHtml('上传模板预览', uploadPreviewHtml(result, file.name), footer, 'template-modal-medium');
  } catch (error) {
    const errors = (error.validationErrors || []).map(item => `<li><span class="template-detail-code">${escapeTemplateHtml(item.path)}</span>：${escapeTemplateHtml(item.message)}</li>`).join('');
    const body = `<div class="error-msg">${escapeTemplateHtml(error.message)}</div>${errors ? `<div class="template-validation-errors"><ul>${errors}</ul></div>` : ''}`;
    root.innerHTML = templateModalHtml('模板校验失败', body, '<button class="btn btn-outline" data-action="close-modal">关闭</button>', 'template-modal-medium');
  } finally {
    if (input) input.value = '';
  }
}


async function handleTemplateFile(event) {
  const input = event.target;
  await processTemplateFile(input.files?.[0], input);
}


function handleTemplateDragOver(event) {
  const zone = event.target.closest('[data-upload-dropzone]');
  if (!zone) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'copy';
  zone.classList.add('drag-over');
}


function handleTemplateDragLeave(event) {
  const zone = event.target.closest('[data-upload-dropzone]');
  if (!zone || zone.contains(event.relatedTarget)) return;
  zone.classList.remove('drag-over');
}


function handleTemplateDrop(event) {
  const zone = event.target.closest('[data-upload-dropzone]');
  if (!zone) return;
  event.preventDefault();
  zone.classList.remove('drag-over');
  const file = event.dataTransfer.files?.[0];
  processTemplateFile(file);
}


async function createUploadedTemplate() {
  if (!templateUploadPreview || templateUploadPreview.result.conflict) return;
  const button = document.querySelector('#template-modal-root [data-action="upload-create"]');
  if (button) button.disabled = true;
  try {
    const created = await templateApi('/templates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(templateUploadPreview.result.template),
    });
    closeTemplateModal();
    await loadTemplates();
    showTemplateToast('模板上传并创建成功');
    openTemplateDetails(created.id);
  } catch (error) {
    showTemplateToast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}


function editUploadedTemplate() {
  if (!templateUploadPreview) return;
  templateEditorState = {
    mode: 'create', originalId: null, origin: 'custom', customized: false,
    activeTab: 'basic', draft: editableTemplateDraft(templateUploadPreview.result.template),
    validationErrors: templateUploadPreview.result.conflict
      ? [{ path: 'id', message: '模板 ID 已存在，请修改后再创建' }]
      : [],
  };
  renderTemplateEditor();
}


async function resetTemplate(templateId) {
  if (templateOperationInFlight) return;
  if (!window.confirm('确认恢复预置版本？当前对内置模板的修改将被清除。')) return;
  templateOperationInFlight = true;
  document.querySelectorAll('[data-action="reset"]').forEach(button => { button.disabled = true; });
  try {
    await templateApi(`/templates/${encodeURIComponent(templateId)}/reset`, { method: 'POST' });
    closeTemplateModal();
    closeTemplateDrawer();
    await loadTemplates();
    showTemplateToast('已恢复预置模板');
    openTemplateDetails(templateId);
  } catch (error) {
    showTemplateToast(error.message, true);
  } finally {
    templateOperationInFlight = false;
    document.querySelectorAll('[data-action="reset"]').forEach(button => { button.disabled = false; });
  }
}


async function deleteTemplate(templateId) {
  if (templateOperationInFlight) return;
  if (!window.confirm('确认删除此自定义模板？删除后无法恢复。')) return;
  templateOperationInFlight = true;
  document.querySelectorAll('[data-action="delete"]').forEach(button => { button.disabled = true; });
  try {
    await templateApi(`/templates/${encodeURIComponent(templateId)}`, { method: 'DELETE' });
    closeTemplateModal();
    closeTemplateDrawer();
    await loadTemplates();
    showTemplateToast('自定义模板已删除');
  } catch (error) {
    showTemplateToast(error.message, true);
  } finally {
    templateOperationInFlight = false;
    document.querySelectorAll('[data-action="delete"]').forEach(button => { button.disabled = false; });
  }
}


const TEMPLATE_APPLY_CATEGORIES = [
  ['entities', '实体'],
  ['relationships', '关系'],
  ['metrics', '指标'],
  ['aliases', '别名'],
];


function renderApplyCountCard(group, title, className) {
  return `
    <div class="template-impact-card ${className}">
      <strong>${title}</strong>
      ${TEMPLATE_APPLY_CATEGORIES.map(([category, label]) => `
        <div class="template-impact-category"><span>${label}</span><b>${Number(group[category] || 0)}</b></div>`).join('')}
    </div>`;
}


function renderApplyImpact(result) {
  const skippedItems = TEMPLATE_APPLY_CATEGORIES.flatMap(([category, label]) => (
    (result.skipped[category] || []).map(item => ({ ...item, categoryLabel: label }))
  ));
  const details = skippedItems.length
    ? `<details><summary>查看 ${skippedItems.length} 条跳过原因</summary><ul class="template-result-list">${skippedItems.map(item => `
        <li><strong>${escapeTemplateHtml(item.categoryLabel)} · ${escapeTemplateHtml(item.name)}</strong>：${escapeTemplateHtml(item.reason)}</li>`).join('')}</ul></details>`
    : '<div class="template-validation-ok">当前没有同名配置需要跳过。</div>';
  return `
    <p class="template-detail-summary">系统将以安全合并方式写入当前语义模型，不会覆盖已有实体、关系、指标或别名。</p>
    <div class="template-impact-grid">
      ${renderApplyCountCard(result.counts.added, '预计新增', 'template-impact-added')}
      ${renderApplyCountCard(result.counts.skipped, '预计跳过', 'template-impact-skipped')}
    </div>
    ${details}`;
}


function renderApplyResultGroup(result, group, title) {
  const items = TEMPLATE_APPLY_CATEGORIES.flatMap(([category, label]) => {
    if (group === 'added') {
      return (result.added[category] || []).map(name => ({ name, reason: '', categoryLabel: label }));
    }
    return (result.skipped[category] || []).map(item => ({ ...item, categoryLabel: label }));
  });
  if (!items.length) return '';
  return `
    <div class="template-result-group">
      <strong>${title}</strong>
      <ul class="template-result-list">${items.map(item => `
        <li><strong>${escapeTemplateHtml(item.categoryLabel)} · ${escapeTemplateHtml(item.name)}</strong>${item.reason ? `：${escapeTemplateHtml(item.reason)}` : ''}</li>`).join('')}</ul>
    </div>`;
}


function renderApplyResult(result) {
  return `
    <div class="template-validation-ok"><strong>✓ 行业模板已成功应用</strong></div>
    <div class="template-impact-grid">
      ${renderApplyCountCard(result.counts.added, '实际新增', 'template-impact-added')}
      ${renderApplyCountCard(result.counts.skipped, '实际跳过', 'template-impact-skipped')}
    </div>
    ${renderApplyResultGroup(result, 'added', '新增明细')}
    ${renderApplyResultGroup(result, 'skipped', '跳过明细')}`;
}


async function previewTemplateApply(templateId) {
  rememberTemplateDialogFocus('template-modal-root');
  const root = document.getElementById('template-modal-root');
  root.innerHTML = templateModalHtml('应用模板', '<div class="loading">正在计算应用影响…</div>', '', 'template-modal-medium');
  try {
    const preview = await templateApi(`/templates/${encodeURIComponent(templateId)}/apply-preview`);
    const safeId = escapeTemplateHtml(templateId);
    const footer = `
      <button class="btn btn-outline" data-action="close-modal">取消</button>
      <button class="btn btn-primary" data-action="confirm-apply" data-template-id="${safeId}">确认应用</button>`;
    root.innerHTML = templateModalHtml('确认应用行业模板？', renderApplyImpact(preview), footer, 'template-modal-medium');
  } catch (error) {
    root.innerHTML = templateModalHtml('无法预览应用影响', `<div class="error-msg">${escapeTemplateHtml(error.message)}</div>`, '<button class="btn btn-outline" data-action="close-modal">关闭</button>', 'template-modal-small');
  }
}


async function confirmTemplateApply(templateId) {
  const root = document.getElementById('template-modal-root');
  const confirmButton = root.querySelector('[data-action="confirm-apply"]');
  if (confirmButton) {
    confirmButton.disabled = true;
    confirmButton.textContent = '应用中…';
  }
  try {
    const result = await templateApi(`/templates/${encodeURIComponent(templateId)}/apply`, {
      method: 'POST',
    });
    const footer = `
      <button class="btn btn-outline" data-action="close-modal">关闭</button>
      <button class="btn btn-primary" data-action="view-graph">查看语义图谱</button>`;
    root.innerHTML = templateModalHtml('应用完成', renderApplyResult(result), footer, 'template-modal-medium');
    showTemplateToast('行业模板已应用');
  } catch (error) {
    const errorBox = root.querySelector('.template-modal-body');
    if (errorBox) {
      errorBox.insertAdjacentHTML('afterbegin', `<div class="error-msg">${escapeTemplateHtml(error.message)}</div>`);
    }
    if (confirmButton) {
      confirmButton.disabled = false;
      confirmButton.textContent = '重试应用';
    }
  }
}


function openSemanticGraphFromTemplate() {
  closeTemplateModal();
  closeTemplateDrawer();
  document.querySelector('.sidebar nav a[data-panel="graph"]')?.click();
}


function removeIndexedEntry(collection, index) {
  collection.splice(index, 1);
  return collection;
}


function mutateTemplateEditor(action, control) {
  if (!captureTemplateEditorDraft()) return;
  const draft = templateEditorState.draft;
  if (action === 'editor-tab') templateEditorState.activeTab = control.dataset.tab;
  if (action === 'add-entity') {
    const name = uniqueDraftName(Object.keys(draft.entities), 'NewEntity');
    draft.entities[name] = { description: '', properties: { id: { type: 'string' } } };
  }
  if (action === 'remove-entity') {
    const entries = Object.entries(draft.entities);
    removeIndexedEntry(entries, Number(control.dataset.index));
    draft.entities = Object.fromEntries(entries);
  }
  if (action === 'add-property') {
    const entity = Object.values(draft.entities)[Number(control.dataset.entityIndex)];
    const name = uniqueDraftName(Object.keys(entity.properties || {}), 'new_field');
    entity.properties[name] = { type: 'string' };
  }
  if (action === 'remove-property') {
    const entity = Object.values(draft.entities)[Number(control.dataset.entityIndex)];
    const entries = Object.entries(entity.properties || {});
    removeIndexedEntry(entries, Number(control.dataset.propertyIndex));
    entity.properties = Object.fromEntries(entries);
  }
  if (action === 'add-relationship') {
    const firstEntity = Object.keys(draft.entities)[0] || '';
    draft.relationships.push({ from: firstEntity, relation: '', to: firstEntity, on: '' });
  }
  if (action === 'remove-relationship') removeIndexedEntry(draft.relationships, Number(control.dataset.index));
  if (action === 'add-metric') {
    const name = uniqueDraftName(Object.keys(draft.metrics), 'new_metric');
    draft.metrics[name] = { description: '', expression: '', unit: null, synonyms: [] };
  }
  if (action === 'remove-metric') {
    const entries = Object.entries(draft.metrics);
    removeIndexedEntry(entries, Number(control.dataset.index));
    draft.metrics = Object.fromEntries(entries);
  }
  if (action === 'add-alias') {
    const name = uniqueDraftName(Object.keys(draft.aliases), '新别名');
    draft.aliases[name] = '';
  }
  if (action === 'remove-alias') {
    const entries = Object.entries(draft.aliases);
    removeIndexedEntry(entries, Number(control.dataset.index));
    draft.aliases = Object.fromEntries(entries);
  }
  templateEditorState.validationErrors = [];
  renderTemplateEditor();
}


function templateModalClick(event) {
  const control = event.target.closest('[data-action]');
  if (!control) return;
  const action = control.dataset.action;
  if (action === 'close-modal') closeTemplateModal();
  if (action === 'choose-upload') document.getElementById('template-file-input')?.click();
  if (action === 'save-template') runTemplateControlAction(control, saveTemplate);
  if (action === 'validate-template') runTemplateControlAction(control, async () => {
    const result = await validateTemplateEditorDraft();
    if (!result) return;
    renderTemplateEditor();
    showTemplateToast('模板校验通过');
  });
  if (action === 'upload-create') runTemplateControlAction(control, createUploadedTemplate);
  if (action === 'upload-edit') editUploadedTemplate();
  if (action === 'reset') runTemplateControlAction(control, () => resetTemplate(control.dataset.templateId));
  if (action === 'confirm-apply') runTemplateControlAction(control, () => confirmTemplateApply(control.dataset.templateId));
  if (action === 'view-graph') openSemanticGraphFromTemplate();
  if ([
    'editor-tab', 'add-entity', 'remove-entity', 'add-property', 'remove-property',
    'add-relationship', 'remove-relationship', 'add-metric', 'remove-metric',
    'add-alias', 'remove-alias',
  ].includes(action)) mutateTemplateEditor(action, control);
}


function rememberTemplateDialogFocus(rootId) {
  if (!templateDialogReturnFocus.has(rootId)) {
    templateDialogReturnFocus.set(rootId, document.activeElement);
  }
}


function restoreTemplateDialogFocus(rootId) {
  const target = templateDialogReturnFocus.get(rootId);
  templateDialogReturnFocus.delete(rootId);
  window.requestAnimationFrame(() => {
    if (target instanceof HTMLElement && target.isConnected) {
      target.focus();
    } else if (latestTemplateDialog()) {
      focusLatestTemplateDialog();
    }
  });
}


function latestTemplateDialog() {
  const dialogs = [...document.querySelectorAll(
    '#template-drawer-root [role="dialog"], #template-modal-root [role="dialog"]',
  )];
  return dialogs.at(-1) || null;
}


function focusTemplateDialog(dialog, preferredSelector = null) {
  if (!dialog) return;
  const target = (preferredSelector && dialog.querySelector(preferredSelector)) || dialog.querySelector(
    'input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled])',
  ) || dialog;
  window.requestAnimationFrame(() => target.focus());
}


function focusLatestTemplateDialog() {
  focusTemplateDialog(latestTemplateDialog());
}


function syncTemplateDialogFocus(root, mutations) {
  const dialog = root.querySelector('[role="dialog"]');
  if (!dialog) {
    templateDialogOpenRoots.delete(root.id);
    return;
  }
  const wasOpen = templateDialogOpenRoots.has(root.id);
  templateDialogOpenRoots.add(root.id);
  const dialogWasAdded = mutations.some(mutation => (
    [...mutation.addedNodes].some(node => (
      node instanceof Element
      && (node.matches('[role="dialog"]') || node.querySelector('[role="dialog"]'))
    ))
  ));
  if (!wasOpen || dialogWasAdded) {
    const preferredSelector = root.dataset.templatePreferredFocus || null;
    delete root.dataset.templatePreferredFocus;
    focusTemplateDialog(dialog, preferredSelector);
  }
}


function handleTemplateDialogKeydown(event) {
  const dialog = latestTemplateDialog();
  if (!dialog) return;

  if (event.key === 'Escape') {
    event.preventDefault();
    if (document.getElementById('template-modal-root')?.contains(dialog)) closeTemplateModal();
    else closeTemplateDrawer();
    return;
  }

  if (!(event.key === 'Tab')) return;
  const focusable = [...dialog.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter(element => element.offsetParent !== null);
  if (!focusable.length) {
    event.preventDefault();
    dialog.focus();
    return;
  }

  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}


document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('template-grid')?.addEventListener('click', templateGridClick);
  const drawerRoot = document.getElementById('template-drawer-root');
  const modalRoot = document.getElementById('template-modal-root');
  drawerRoot?.addEventListener('click', templateDrawerClick);
  modalRoot?.addEventListener('click', templateModalClick);
  modalRoot?.addEventListener('dragover', handleTemplateDragOver);
  modalRoot?.addEventListener('dragleave', handleTemplateDragLeave);
  modalRoot?.addEventListener('drop', handleTemplateDrop);
  document.addEventListener('keydown', handleTemplateDialogKeydown);
  if (drawerRoot) {
    new MutationObserver(mutations => syncTemplateDialogFocus(drawerRoot, mutations))
      .observe(drawerRoot, { childList: true });
  }
  if (modalRoot) {
    new MutationObserver(mutations => syncTemplateDialogFocus(modalRoot, mutations))
      .observe(modalRoot, { childList: true });
  }
});
