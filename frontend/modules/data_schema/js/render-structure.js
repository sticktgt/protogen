import { state, entities, entityDetails, selectEntity } from './state.js';
import { escapeHtml } from './html-utils.js';
import { renderEntityEditor, renderEntityCreateForm } from './entity-editor.js';
import { renderFieldEditor } from './field-editor.js';
import { renderAll } from './main.js';

export function renderStructureView() {
  renderEntitySelect();
  bindEntityFilter();
  renderEntityTree();
  renderEditor();
}

function renderEntitySelect() {
  const select = document.querySelector('[data-entity-select]');
  if (!select) return;
  select.innerHTML = entities().map(item => `
    <option value="${escapeHtml(item.id)}" ${item.id === state.selectedEntityId ? 'selected' : ''}>${escapeHtml(item.details?.title || item.title)}</option>
  `).join('');
  select.onchange = () => {
    selectEntity(select.value);
    state.activeEditorTab = 'fields';
    renderAll();
  };
}

function bindEntityFilter() {
  const input = document.querySelector('[data-entity-filter]');
  if (!input) return;
  input.value = state.structureEntityFilter || '';
  input.oninput = () => {
    state.structureEntityFilter = input.value;
    renderEntityTree();
    input.focus();
  };
}

function filteredEntities() {
  const query = state.structureEntityFilter.trim().toLowerCase();
  if (!query) return entities();
  return entities().filter(item => {
    const entity = item.details || item;
    return [entity.title, entity.id].some(value => String(value || '').toLowerCase().includes(query));
  });
}

function renderEntityTree() {
  const container = document.querySelector('[data-entity-tree]');
  if (!container) return;
  const items = filteredEntities();
  if (!items.length) {
    container.innerHTML = '<div class="empty-state compact-empty">Сущности по фильтру не найдены.</div>';
    return;
  }
  container.innerHTML = items.map(item => renderEntityNode(item.details || item)).join('');
  container.querySelectorAll('[data-select-entity]').forEach(node => {
    node.addEventListener('click', () => {
      selectEntity(node.dataset.selectEntity);
      state.activeEditorTab = 'fields';
      renderAll();
    });
  });
}

function renderEntityNode(entity) {
  const entityActive = state.selectedEntityId === entity.id;
  const fieldCount = entity.fields?.length || 0;
  return `
    <div class="tree-item ${entityActive ? 'active' : ''}" data-select-entity="${escapeHtml(entity.id)}">
      <div>
        <strong>${escapeHtml(entity.title)}</strong>
        <div class="entity-id">${escapeHtml(entity.id)}</div>
      </div>
      <span class="badge">${fieldCount} полей</span>
    </div>
  `;
}

function renderEditor() {
  const container = document.querySelector('[data-editor]');
  if (!container) return;
  if (state.createEntityMode) {
    renderEntityCreateForm(container);
    return;
  }
  if (!state.selectedEntityId) {
    container.innerHTML = '<div class="empty-state">Выберите сущность или создайте новую.</div>';
    return;
  }
  if (state.selectedFieldId) {
    renderFieldEditor(container);
    return;
  }
  if (!entityDetails()) {
    container.innerHTML = '<div class="empty-state">Сущность не найдена.</div>';
    return;
  }
  renderEntityEditor(container);
}
