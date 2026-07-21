import { createPage, deletePage, updatePage } from './api.js';
import { renderAll } from './main.js';
import { flattenElements, selectedPage, state } from './state.js';
import { addTopLevelElementPanel } from './element-add-panel.js';
import { renderRequirementsTab } from './element-requirements-tab.js';
import { renderRelationsTab } from './element-relations-tab.js';
import { renderCodeTab } from './element-code-tab.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

const tabs = [
  ['info', '✏️', 'Поля'],
  ['requirements', '📌', 'Требования'],
  ['relations', '🔗', 'Связи'],
  ['code', '🧩', 'Код']
];

export function renderCreatePageEditor(container, addPanel) {
  if (addPanel) addPanel.innerHTML = '';
  container.innerHTML = `
    <div class="element-editor-title">Новая страница</div>
    <form class="schema-form element-field-form" data-create-page-form>
      <div class="form-row">
        <label>ID</label>
        <input name="id" placeholder="cards.block" required>
      </div>
      <div class="form-row">
        <label>Название</label>
        <input name="title" placeholder="Блокировка карты" required>
      </div>
      <div class="form-row form-row-wide">
        <label>Описание</label>
        <textarea name="description" rows="3" placeholder="Назначение страницы"></textarea>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Создать страницу</button>
        <button class="btn" type="button" data-cancel-page-create>Отмена</button>
      </div>
    </form>
  `;

  container.querySelector('[data-create-page-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      id: form.get('id'),
      title: form.get('title'),
      description: form.get('description')
    };
    await createPage(state.workspaceId, payload);
    state.selectedPageId = payload.id;
    state.selectedElementId = null;
    state.createPageMode = false;
    state.elementEditorTab = 'info';
    showToast('Страница создана');
    await renderAll({ reload: true });
  });

  container.querySelector('[data-cancel-page-create]')?.addEventListener('click', () => {
    state.createPageMode = false;
    renderAll();
  });
}

export function renderPageEditor(container, addPanel) {
  const page = selectedPage();
  if (!page) {
    container.innerHTML = '<div class="empty-state">Страница не выбрана.</div>';
    if (addPanel) addPanel.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="element-editor-header">
      <div>
        <div class="element-editor-title">📄 ${escapeHtml(page.title || page.id)}</div>
        <div class="item-meta">${escapeHtml(page.id)} · страница</div>
      </div>
    </div>
    <div class="element-editor-tabs">
      ${tabs.map(([id, icon, title]) => tabButton(id, icon, title)).join('')}
    </div>
    <div data-page-tab-content></div>
  `;

  container.querySelectorAll('[data-page-editor-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.elementEditorTab = button.dataset.pageEditorTab;
      state.showElementCreateForm = false;
      state.showRequirementLinkForm = false;
      state.showUiLinkForm = false;
      renderAll();
    });
  });

  renderPageTab(container, addPanel, page);
}

function tabButton(tabId, icon, title) {
  const active = state.elementEditorTab === tabId ? ' active' : '';
  return `<button class="element-editor-tab${active}" type="button" data-page-editor-tab="${tabId}"><span>${icon}</span><span>${title}</span></button>`;
}

function renderPageTab(container, addPanel, page) {
  const tab = container.querySelector('[data-page-tab-content]');
  if (!tab) return;
  if (state.elementEditorTab === 'requirements') {
    if (addPanel) addPanel.innerHTML = '';
    renderRequirementsTab(tab, pageTarget(page), 'page');
  } else if (state.elementEditorTab === 'relations') {
    if (addPanel) addPanel.innerHTML = '';
    renderRelationsTab(tab, page, pageTarget(page), false, 'page');
  } else if (state.elementEditorTab === 'code') {
    if (addPanel) addPanel.innerHTML = '';
    renderCodeTab(tab, pageTarget(page), 'page');
  } else {
    renderPageFieldsTab(tab, page);
    addTopLevelElementPanel(addPanel, page);
  }
}

function pageTarget(page) {
  return {
    id: page.id,
    type: 'page',
    label: page.title || page.id,
    title: page.title || page.id,
    description: page.description || '',
    children: page.elements || []
  };
}

function renderPageFieldsTab(container, page) {
  const hasElements = flattenElements(page).length > 0;
  container.innerHTML = `
    <form class="schema-form element-field-form" data-page-edit-form>
      <div class="form-row">
        <label>ID</label>
        <input value="${escapeAttr(page.id)}" disabled>
      </div>
      <div class="form-row">
        <label>Название</label>
        <input name="title" value="${escapeAttr(page.title || '')}">
      </div>
      <div class="form-row form-row-wide">
        <label>Описание</label>
        <textarea name="description" rows="3">${escapeHtml(page.description || '')}</textarea>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Сохранить страницу</button>
        <button class="btn btn-danger" type="button" data-delete-page ${hasElements ? 'disabled' : ''}>Удалить страницу</button>
      </div>
      ${hasElements ? '<div class="form-hint">Страницу с вложенными элементами удалить нельзя. Сначала удалите все элементы страницы.</div>' : ''}
    </form>
  `;
  bindPageFields(container, page);
}

function bindPageFields(container, page) {
  container.querySelector('[data-page-edit-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await updatePage(state.workspaceId, page.id, {
      title: form.get('title'),
      description: form.get('description')
    });
    showToast('Страница сохранена');
    await renderAll({ reload: true });
  });

  container.querySelector('[data-delete-page]')?.addEventListener('click', async () => {
    if (flattenElements(page).length > 0) return;
    await deletePage(state.workspaceId, page.id);
    state.selectedPageId = null;
    state.selectedElementId = null;
    showToast('Страница удалена');
    await renderAll({ reload: true });
  });
}
