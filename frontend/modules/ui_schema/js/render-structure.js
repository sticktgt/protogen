import {
  APP_SCOPE,
  appSchema,
  elementTypeIcon,
  elementTypeLabel,
  flattenAppElements,
  flattenElements,
  pages,
  selectedPage,
  state
} from './state.js';
import { renderAll } from './main.js';
import { renderElementEditor } from './element-editor.js';
import { escapeAttr, escapeHtml } from './html-utils.js';

export function renderStructureView() {
  renderPageSelect();
  renderElementTree();
  renderElementEditor();
}

function renderPageSelect() {
  const select = document.querySelector('[data-structure-page-select]');
  if (!select) return;
  const appSelected = state.selectedPageId === APP_SCOPE ? 'selected' : '';
  const pageOptions = pages().map(page => `
    <option value="${escapeAttr(page.id)}" ${page.id === state.selectedPageId ? 'selected' : ''}>${escapeHtml(page.details?.title || page.title || page.id)}</option>
  `).join('');
  select.innerHTML = `<option value="${APP_SCOPE}" ${appSelected}>🧭 Приложение / корневые элементы</option>${pageOptions}`;
  select.disabled = state.createPageMode;
  select.onchange = () => {
    state.selectedPageId = select.value;
    state.selectedElementId = null;
    state.elementEditorTab = 'info';
    state.createPageMode = false;
    state.showElementCreateForm = false;
    state.showRequirementLinkForm = false;
    state.showUiLinkForm = false;
    renderAll();
  };
}

function renderElementTree() {
  const container = document.querySelector('[data-element-tree]');
  if (!container) return;
  if (state.createPageMode) {
    container.innerHTML = '<div class="empty-state">Создается новая страница.</div>';
    return;
  }
  if (state.selectedPageId === APP_SCOPE) {
    renderAppTree(container);
    return;
  }
  renderPageTree(container);
}

function renderAppTree(container) {
  const app = appSchema();
  const flat = flattenAppElements();
  const rootRow = `
    <div class="element-row page-root-row${!state.selectedElementId ? ' active' : ''}" data-select-app-root>
      <span>🧭 ${escapeHtml(app.title || 'Приложение')}</span>
      <span class="element-kind">app</span>
    </div>
  `;
  const rows = flat.map(element => `
    <div class="element-row${element.id === state.selectedElementId ? ' active' : ''}" data-depth="${element.depth}" data-select-element="${escapeAttr(element.id)}">
      <span>${escapeHtml(elementTypeIcon(element.type))} ${escapeHtml(element.label || element.id)}</span>
      <span class="element-kind">${escapeHtml(elementTypeLabel(element.type))}</span>
    </div>
  `).join('');
  container.innerHTML = rootRow + (rows || '<div class="empty-state compact">Корневых элементов нет.</div>');
  container.querySelector('[data-select-app-root]')?.addEventListener('click', () => {
    state.selectedElementId = null;
    state.elementEditorTab = 'info';
    state.showElementCreateForm = false;
    state.showRequirementLinkForm = false;
    state.showUiLinkForm = false;
    renderAll();
  });
  bindElementRows(container);
}

function renderPageTree(container) {
  const page = selectedPage();
  if (!page) {
    container.innerHTML = '<div class="empty-state">Страница не выбрана.</div>';
    return;
  }
  const flat = flattenElements(page);
  const rootRow = `
    <div class="element-row page-root-row${!state.selectedElementId ? ' active' : ''}" data-select-page-root>
      <span>📄 ${escapeHtml(page.title || page.id)}</span>
      <span class="element-kind">страница</span>
    </div>
  `;
  const rows = flat.map(element => `
    <div class="element-row${element.id === state.selectedElementId ? ' active' : ''}" data-depth="${element.depth}" data-select-element="${escapeAttr(element.id)}">
      <span>${escapeHtml(elementTypeIcon(element.type))} ${escapeHtml(element.label || element.id)}</span>
      <span class="element-kind">${escapeHtml(elementTypeLabel(element.type))}</span>
    </div>
  `).join('');
  container.innerHTML = rootRow + (rows || '<div class="empty-state compact">На странице нет элементов.</div>');

  container.querySelector('[data-select-page-root]')?.addEventListener('click', () => {
    state.selectedElementId = null;
    state.createPageMode = false;
    state.elementEditorTab = 'info';
    state.showElementCreateForm = false;
    state.showRequirementLinkForm = false;
    state.showUiLinkForm = false;
    renderAll();
  });
  bindElementRows(container);
}

function bindElementRows(container) {
  container.querySelectorAll('[data-select-element]').forEach(item => {
    item.addEventListener('click', () => {
      state.selectedElementId = item.dataset.selectElement;
      state.createPageMode = false;
      state.elementEditorTab = 'info';
      state.showElementCreateForm = false;
      state.showRequirementLinkForm = false;
      state.showUiLinkForm = false;
      renderAll();
    });
  });
}
