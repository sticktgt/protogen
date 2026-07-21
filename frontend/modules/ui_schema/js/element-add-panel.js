import { addAppElement, addElement } from './api.js';
import { renderAll } from './main.js';
import {
  APP_SCOPE,
  allowedChildTypes,
  elementTypeIcon,
  elementTypeLabel,
  isAppScope,
  isGroupElement,
  state
} from './state.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

export function addTopLevelElementPanel(container, page) {
  if (!container) return;
  if (isAppScope()) {
    renderElementCreatePanel(container, { id: APP_SCOPE, title: 'Приложение' }, null, 'Приложение');
    return;
  }
  renderElementCreatePanel(container, page, null, `Страница: ${page.title || page.id}`);
}

export function renderAddChildPanel(container, page, element) {
  if (!container) return;
  if (state.elementEditorTab !== 'info') {
    container.innerHTML = '';
    return;
  }
  if (!element) {
    if (isAppScope()) {
      renderElementCreatePanel(container, page, null, 'Приложение');
    } else {
      container.innerHTML = '';
    }
    return;
  }
  if (!isGroupElement(element) || allowedChildTypes(element).length === 0) {
    container.innerHTML = '';
    return;
  }
  renderElementCreatePanel(container, page, element, `Родитель: ${element.label || element.id}`);
}

function renderElementCreatePanel(container, page, parent, contextLabel) {
  const allowedTypes = allowedChildTypes(parent);
  if (!allowedTypes.length) {
    container.innerHTML = '';
    return;
  }
  if (!state.showElementCreateForm) {
    container.innerHTML = `
      <hr>
      <button class="btn btn-primary btn-sm" type="button" data-show-element-create>${parent ? 'Добавить вложенный элемент' : (isAppScope() ? 'Добавить главное меню' : 'Добавить элемент на страницу')}</button>
    `;
    container.querySelector('[data-show-element-create]')?.addEventListener('click', () => {
      state.showElementCreateForm = true;
      renderAll();
    });
    return;
  }

  const placeholder = parent ? `${parent.id}.new_item` : `${page.id}.new_item`;
  container.innerHTML = `
    <hr>
    <div class="card-title">${parent ? 'Добавить вложенный элемент' : (isAppScope() ? 'Добавить главное меню' : 'Добавить элемент на страницу')}</div>
    <div class="item-meta add-context">${escapeHtml(contextLabel)}</div>
    <form class="schema-form" data-element-create-form>
      <div class="form-row">
        <label>ID</label>
        <input name="id" placeholder="${escapeAttr(placeholder)}">
      </div>
      <div class="form-row">
        <label>Тип</label>
        <select name="type" data-element-type-select>${typeOptions(allowedTypes)}</select>
      </div>
      <div class="form-row">
        <label>Название</label>
        <input name="label" placeholder="Новый элемент" required>
      </div>
      <div class="form-row form-row-wide">
        <label>Описание</label>
        <textarea name="description" rows="2"></textarea>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Добавить</button>
        <button class="btn" type="button" data-cancel-element-create>Отмена</button>
      </div>
    </form>
  `;

  container.querySelector('[data-element-create-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      parent_id: parent?.id || null,
      id: form.get('id') || null,
      type: form.get('type'),
      label: form.get('label'),
      description: form.get('description')
    };
    const result = isAppScope()
      ? await addAppElement(state.workspaceId, payload)
      : await addElement(state.workspaceId, page.id, payload);
    state.selectedElementId = result.element.id;
    state.elementEditorTab = 'info';
    state.showElementCreateForm = false;
    showToast('Вложенный элемент добавлен');
    await renderAll({ reload: true });
  });

  container.querySelector('[data-cancel-element-create]')?.addEventListener('click', () => {
    state.showElementCreateForm = false;
    renderAll();
  });
}

function typeOptions(types) {
  return types.map(type => `<option value="${type}">${elementTypeIcon(type)} ${elementTypeLabel(type)}</option>`).join('');
}
