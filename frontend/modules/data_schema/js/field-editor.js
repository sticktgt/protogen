import { deleteField, updateField } from './api.js';
import { state, dictionaries, entityDetails, selectedField } from './state.js';
import { escapeHtml, formBool, formValue, toast } from './html-utils.js';
import { renderTypeBadge, renderTypeOptions } from './data-types.js';
import { renderAll } from './main.js';
import {
  bindSharedForms,
  renderCodeTab,
  renderExternalLinksTab,
  renderRelationsTab,
  renderRequirementTab,
  renderTabs
} from './shared-tabs.js';

export function renderFieldEditor(container) {
  const entity = entityDetails();
  const field = selectedField();
  container.innerHTML = `
    <div class="editor-header">
      <div>
        <div class="editor-title">${escapeHtml(field.title)}</div>
        <div class="editor-subtitle">field · ${escapeHtml(entity.id)}.${escapeHtml(field.id)} · ${renderTypeBadge(field.type)}</div>
      </div>
    </div>
    ${renderTabs()}
    <div data-editor-tab-content>${renderFieldTab(field)}</div>
  `;
  bindFieldForms(container, entity, field);
  bindSharedForms(container);
}

function renderFieldTab(field) {
  if (state.activeEditorTab === 'requirements') return renderRequirementTab();
  if (state.activeEditorTab === 'relations') return renderRelationsTab();
  if (state.activeEditorTab === 'ui') return renderExternalLinksTab('ui');
  if (state.activeEditorTab === 'api') return renderExternalLinksTab('api');
  if (state.activeEditorTab === 'code') return renderCodeTab();
  return `
    <form data-update-field class="compact-form field-edit-form">
      <div class="form-row"><label>Название</label><input name="title" value="${escapeHtml(field.title)}"></div>
      <div class="form-row"><label>Тип</label><select name="type">${renderTypeOptions(field.type)}</select></div>
      <div class="form-row"><label>Словарь</label><select name="dictionary_id"><option value="">—</option>${dictionaryOptions(field.dictionary_id)}</select></div>
      <div class="form-row checkbox-row"><label><input type="checkbox" name="required" ${field.required ? 'checked' : ''}> Обязательное</label></div>
      <div class="form-row form-row-wide"><label>Описание</label><textarea name="description">${escapeHtml(field.description)}</textarea></div>
      <div class="form-actions compact-form-actions form-actions-column">
        <button class="btn btn-primary" type="submit">Сохранить поле</button>
        <button class="btn btn-danger btn-sm" type="button" data-delete-field>Удалить поле</button>
      </div>
    </form>
  `;
}

function dictionaryOptions(selectedId) {
  return dictionaries().map(item => `
    <option value="${escapeHtml(item.id)}" ${item.id === selectedId ? 'selected' : ''}>${escapeHtml(item.title || item.id)}</option>
  `).join('');
}

function bindFieldForms(container, entity, field) {
  container.querySelector('[data-update-field]')?.addEventListener('submit', async event => {
    event.preventDefault();
    await updateField(state.workspaceId, entity.id, field.id, {
      title: formValue(event.target, 'title'),
      type: formValue(event.target, 'type'),
      required: formBool(event.target, 'required'),
      dictionary_id: formValue(event.target, 'dictionary_id') || null,
      description: formValue(event.target, 'description')
    });
    toast('Поле сохранено');
    await renderAll({ reload: true });
  });
  container.querySelector('[data-delete-field]')?.addEventListener('click', async () => {
    if (!confirm('Удалить поле?')) return;
    await deleteField(state.workspaceId, entity.id, field.id);
    state.selectedFieldId = null;
    toast('Поле удалено');
    await renderAll({ reload: true });
  });
}
