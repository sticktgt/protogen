import { createEntity, deleteEntity, updateEntity, addField } from './api.js';
import { state, entityDetails, dictionaries } from './state.js';
import { escapeHtml, formBool, formValue, toast } from './html-utils.js';
import { DATA_TYPE_IDS, renderTypeBadge, renderTypeOptions } from './data-types.js';
import { renderAll } from './main.js';
import {
  bindSharedForms,
  renderCodeTab,
  renderExternalLinksTab,
  renderRelationsTab,
  renderRequirementTab,
  renderTabs
} from './shared-tabs.js';

export function renderEntityCreateForm(container) {
  container.innerHTML = `
    <div class="editor-header">
      <div>
        <div class="editor-title">Новая сущность</div>
        <div class="editor-subtitle">Логическая сущность предметной области.</div>
      </div>
    </div>
    <form data-create-entity class="form-stack narrow-form">
      <div class="form-row"><label>Название</label><input name="title" placeholder="Счет"></div>
      <div class="form-row"><label>Описание</label><textarea name="description"></textarea></div>
      <div class="form-actions"><button class="btn btn-primary" type="submit">Создать</button></div>
    </form>
  `;
  container.querySelector('[data-create-entity]').addEventListener('submit', async event => {
    event.preventDefault();
    const response = await createEntity(state.workspaceId, {
      title: formValue(event.target, 'title'),
      description: formValue(event.target, 'description')
    });
    state.selectedEntityId = response.entity.id;
    state.createEntityMode = false;
    toast('Сущность создана');
    await renderAll({ reload: true });
  });
}

export function renderEntityEditor(container) {
  const entity = entityDetails();
  container.innerHTML = `
    <div class="editor-header">
      <div>
        <div class="editor-title">${escapeHtml(entity.title)}</div>
        <div class="editor-subtitle">entity · ${escapeHtml(entity.id)}</div>
      </div>
    </div>
    ${renderTabs()}
    <div data-editor-tab-content>${renderEntityTab(entity)}</div>
  `;
  bindEntityForms(container, entity);
  bindSharedForms(container);
}

function renderEntityTab(entity) {
  if (state.activeEditorTab === 'requirements') return renderRequirementTab();
  if (state.activeEditorTab === 'relations') return renderRelationsTab();
  if (state.activeEditorTab === 'ui') return renderExternalLinksTab('ui');
  if (state.activeEditorTab === 'api') return renderExternalLinksTab('api');
  if (state.activeEditorTab === 'code') return renderCodeTab();
  return renderEntityFieldsTab(entity);
}

function renderEntityFieldsTab(entity) {
  return `
    <form data-update-entity class="editor-section compact-form entity-main-form">
      <div class="form-row"><label>Название</label><input name="title" value="${escapeHtml(entity.title)}"></div>
      <div class="form-row"><label>Описание</label><textarea name="description">${escapeHtml(entity.description)}</textarea></div>
      <div class="form-actions form-actions-column">
        <button class="btn btn-primary" type="submit">Сохранить сущность</button>
        <button class="btn btn-danger btn-sm" type="button" data-delete-entity>Удалить сущность</button>
      </div>
    </form>

    <section class="editor-section">
      <h3 class="section-title">Добавить поле</h3>
      <form data-add-field class="compact-form add-field-form">
        <div class="form-row"><label>Название</label><input name="title" placeholder="Баланс"></div>
        <div class="form-row"><label>Тип</label><select name="type">${renderTypeOptions(DATA_TYPE_IDS[0])}</select></div>
        <div class="form-row"><label>Словарь</label><select name="dictionary_id"><option value="">—</option>${dictionaryOptions()}</select></div>
        <div class="form-row checkbox-row"><label><input type="checkbox" name="required"> Обязательное</label></div>
        <div class="form-row form-row-wide"><label>Описание</label><textarea name="description"></textarea></div>
        <div class="form-actions compact-form-actions"><button class="btn btn-primary" type="submit">Добавить поле</button></div>
      </form>
    </section>

    <section class="editor-section">
      <h3 class="section-title">Поля сущности</h3>
      <div class="entity-field-table">${(entity.fields || []).map(renderFieldRow).join('') || '<div class="empty-state">Полей пока нет.</div>'}</div>
    </section>
  `;
}

function renderFieldRow(field) {
  return `
    <div class="table-row field-table-row">
      <div class="table-row-main">
        <strong>${escapeHtml(field.title)}</strong> ${field.required ? '<span class="required-mark">*</span>' : ''}
        <div class="muted">${escapeHtml(field.id)} · ${renderTypeBadge(field.type)}</div>
      </div>
      <button class="btn btn-sm" type="button" data-open-field="${escapeHtml(field.id)}">Открыть</button>
    </div>
  `;
}

function dictionaryOptions() {
  return dictionaries().map(item => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title || item.id)}</option>`).join('');
}

function bindEntityForms(container, entity) {
  container.querySelector('[data-update-entity]')?.addEventListener('submit', async event => {
    event.preventDefault();
    await updateEntity(state.workspaceId, entity.id, {
      title: formValue(event.target, 'title'),
      description: formValue(event.target, 'description')
    });
    toast('Сущность сохранена');
    await renderAll({ reload: true });
  });
  container.querySelector('[data-add-field]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const response = await addField(state.workspaceId, entity.id, {
      title: formValue(event.target, 'title'),
      type: formValue(event.target, 'type'),
      required: formBool(event.target, 'required'),
      dictionary_id: formValue(event.target, 'dictionary_id') || null,
      description: formValue(event.target, 'description')
    });
    state.selectedFieldId = response.field.id;
    toast('Поле добавлено');
    await renderAll({ reload: true });
  });
  container.querySelectorAll('[data-open-field]').forEach(button => button.addEventListener('click', () => {
    state.selectedFieldId = button.dataset.openField;
    state.activeEditorTab = 'fields';
    renderAll();
  }));
  container.querySelector('[data-delete-entity]')?.addEventListener('click', async () => {
    if (!confirm('Удалить сущность?')) return;
    await deleteEntity(state.workspaceId, entity.id);
    state.selectedEntityId = null;
    toast('Сущность удалена');
    await renderAll({ reload: true });
  });
}
