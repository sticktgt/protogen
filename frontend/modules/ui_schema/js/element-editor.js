import { APP_SCOPE, appSchema, findAppElement, findElement, selectedPage, state } from './state.js';
import { renderElementFieldsTab } from './element-fields-tab.js';
import { renderRequirementsTab } from './element-requirements-tab.js';
import { renderRelationsTab } from './element-relations-tab.js';
import { renderCodeTab } from './element-code-tab.js';
import { renderAddChildPanel } from './element-add-panel.js';
import { renderCreatePageEditor, renderPageEditor } from './page-editor.js';
import { renderAppRootEditor } from './app-root-editor.js';
import { escapeHtml } from './html-utils.js';

const tabs = [
  ['info', '✏️', 'Поля'],
  ['requirements', '📌', 'Требования'],
  ['relations', '🔗', 'Связи'],
  ['code', '🧩', 'Код']
];

export function renderElementEditor() {
  const container = document.querySelector('[data-element-editor]');
  const addPanel = document.querySelector('[data-element-add-panel]');
  if (!container) return;

  if (state.createPageMode) {
    renderCreatePageEditor(container, addPanel);
    return;
  }

  if (state.selectedPageId === APP_SCOPE) {
    renderAppEditor(container, addPanel);
    return;
  }

  if (!state.selectedElementId) {
    renderPageEditor(container, addPanel);
    return;
  }

  const page = selectedPage();
  const element = findElement(page, state.selectedElementId);
  if (!page || !element) {
    container.innerHTML = '<div class="empty-state">Выберите страницу или элемент.</div>';
    if (addPanel) addPanel.innerHTML = '';
    return;
  }

  renderElementShell(container, element);
  renderElementTabContent(page, element, false);
  renderAddChildPanel(addPanel, page, element);
}

function renderAppEditor(container, addPanel) {
  if (!state.selectedElementId) {
    renderAppRootEditor(container, addPanel);
    return;
  }

  const element = findAppElement(state.selectedElementId);
  if (!element) {
    container.innerHTML = '<div class="empty-state">Выберите корневой элемент.</div>';
    if (addPanel) addPanel.innerHTML = '';
    return;
  }

  renderElementShell(container, element);
  renderElementTabContent(null, element, true);
  renderAddChildPanel(addPanel, { id: APP_SCOPE, title: appSchema().title }, element);
}

function renderElementShell(container, element) {
  container.innerHTML = `
    <div class="element-editor-header">
      <div>
        <div class="element-editor-title">${escapeHtml(element.label || element.id)}</div>
        <div class="item-meta">${escapeHtml(element.id)} · ${escapeHtml(element.type || '')}</div>
      </div>
    </div>
    <div class="element-editor-tabs">
      ${tabs.map(([id, icon, title]) => tabButton(id, icon, title)).join('')}
    </div>
    <div data-element-tab-content></div>
  `;

  container.querySelectorAll('[data-element-editor-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.elementEditorTab = button.dataset.elementEditorTab;
      state.showElementCreateForm = false;
      state.showRequirementLinkForm = false;
      state.showUiLinkForm = false;
      renderElementEditor();
    });
  });
}

function tabButton(tabId, icon, title) {
  const active = state.elementEditorTab === tabId ? ' active' : '';
  return `<button class="element-editor-tab${active}" type="button" data-element-editor-tab="${tabId}"><span>${icon}</span><span>${title}</span></button>`;
}

function renderElementTabContent(page, element, appMode) {
  const container = document.querySelector('[data-element-tab-content]');
  if (!container) return;
  if (state.elementEditorTab === 'requirements') {
    renderRequirementsTab(container, element);
  } else if (state.elementEditorTab === 'relations') {
    renderRelationsTab(container, page, element, appMode);
  } else if (state.elementEditorTab === 'code') {
    renderCodeTab(container, element);
  } else {
    renderElementFieldsTab(container, page, element, appMode);
  }
}
