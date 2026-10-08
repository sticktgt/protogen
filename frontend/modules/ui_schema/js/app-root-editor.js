import { updateApp } from './api.js';
import { renderAll } from './main.js';
import { APP_SCOPE, appSchema, state } from './state.js';
import { addTopLevelElementPanel } from './element-add-panel.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { renderScopeChangesOverview, renderSelectedChangeDetails } from './preview-diff.js';
import { showToast } from '/base/js/ui.js';

export function renderAppRootEditor(container, addPanel) {
  const app = appSchema();
  container.innerHTML = `
    <div class="element-editor-header">
      <div>
        <div class="element-editor-title">🧭 ${escapeHtml(app.title || 'Приложение')}</div>
        <div class="item-meta">${escapeHtml(app.id || 'app')} · приложение</div>
      </div>
    </div>
    ${renderSelectedChangeDetails('application', 'app')}
    ${renderScopeChangesOverview(APP_SCOPE)}
    <form class="schema-form element-field-form" data-app-root-form>
      <div class="form-row">
        <label>ID</label>
        <input value="${escapeAttr(app.id || 'app')}" disabled>
      </div>
      <div class="form-row">
        <label>Название</label>
        <input name="title" value="${escapeAttr(app.title || '')}">
      </div>
      <div class="form-row form-row-wide">
        <label>Описание</label>
        <textarea name="description" rows="3">${escapeHtml(app.description || '')}</textarea>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Сохранить приложение</button>
      </div>
    </form>
  `;
  container.querySelector('[data-app-root-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await updateApp(state.workspaceId, {
      title: form.get('title'),
      description: form.get('description')
    });
    showToast('Описание приложения сохранено');
    await renderAll({ reload: true });
  });
  addTopLevelElementPanel(addPanel, { id: app.id || 'app', title: app.title || 'Приложение' });
}
