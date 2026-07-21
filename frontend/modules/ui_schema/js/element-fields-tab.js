import { deleteAppElement, deleteElement, updateAppElement, updateElement } from './api.js';
import { renderAll } from './main.js';
import { appElementTypes, elementTypeIcon, elementTypeLabel, pageElementTypes, state } from './state.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

export function renderElementFieldsTab(container, page, element, appMode = false) {
  const hasChildren = (element.children || []).length > 0;
  container.innerHTML = `
    <form data-element-edit-form class="schema-form element-field-form">
      <div class="form-row">
        <label>ID</label>
        <input value="${escapeAttr(element.id)}" disabled>
      </div>
      <div class="form-row">
        <label>Тип</label>
        <select name="type" ${appMode ? 'disabled' : ''}>${typeOptions(element.type, appMode)}</select>
      </div>
      <div class="form-row">
        <label>Название</label>
        <input name="label" value="${escapeAttr(element.label || '')}">
      </div>
      <div class="form-row form-row-wide">
        <label>Описание</label>
        <textarea name="description" rows="3">${escapeHtml(element.description || '')}</textarea>
      </div>
      <div class="form-row form-row-wide">
        <label>Назначение</label>
        <textarea name="purpose" rows="2">${escapeHtml(element.purpose || '')}</textarea>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Сохранить элемент</button>
        <button class="btn btn-danger" type="button" data-delete-element ${hasChildren ? 'disabled' : ''}>Удалить элемент</button>
      </div>
      ${hasChildren ? '<div class="form-hint">Групповой элемент с вложенными элементами удалить нельзя. Сначала удалите вложенные элементы.</div>' : ''}
    </form>
  `;

  container.querySelector('[data-element-edit-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      type: form.get('type') || element.type,
      label: form.get('label'),
      description: form.get('description'),
      purpose: form.get('purpose')
    };
    if (appMode) {
      await updateAppElement(state.workspaceId, element.id, payload);
    } else {
      await updateElement(state.workspaceId, page.id, element.id, payload);
    }
    showToast('Элемент сохранен');
    await renderAll({ reload: true });
  });

  container.querySelector('[data-delete-element]')?.addEventListener('click', async () => {
    if ((element.children || []).length > 0) return;
    if (appMode) {
      await deleteAppElement(state.workspaceId, element.id);
    } else {
      await deleteElement(state.workspaceId, page.id, element.id);
    }
    state.selectedElementId = null;
    showToast('Элемент удален');
    await renderAll({ reload: true });
  });
}

function typeOptions(selectedType, appMode) {
  const types = appMode ? appElementTypes : pageElementTypes;
  return types.map(type => `<option value="${type}" ${type === selectedType ? 'selected' : ''}>${elementTypeIcon(type)} ${elementTypeLabel(type)}</option>`).join('');
}
