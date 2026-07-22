import { state } from './state.js';
import { renderAll } from './main.js';
import { ensureUiSchemaLoaded } from './external-links-tab.js';

const tabs = [
  ['fields', 'Поля'],
  ['relations', 'Связи'],
  ['requirements', 'Требования'],
  ['ui', 'UI'],
  ['api', 'API'],
  ['code', 'Код']
];

export function renderTabs() {
  return `<div class="editor-tabs">${tabs.map(([id, title]) => `
    <button class="btn btn-sm ${state.activeEditorTab === id ? 'btn-primary' : ''}" type="button" data-editor-tab="${id}">${title}</button>
  `).join('')}</div>`;
}

export function bindTabs(container) {
  container.querySelectorAll('[data-editor-tab]').forEach(button => {
    button.addEventListener('click', async () => {
      state.activeEditorTab = button.dataset.editorTab;
      if (state.activeEditorTab === 'ui') {
        await ensureUiSchemaLoaded();
      }
      await renderAll();
    });
  });
}
