import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { loadSummary } from './api.js';
import { state, entities } from './state.js';
import { renderMapView } from './render-map.js';
import { renderStructureView } from './render-structure.js';
import { renderGraphView } from './graph-joint.js';

await initLayout('data_schema.main');
const context = await getContext();
state.workspaceId = currentWorkspaceId(context);

if (!state.workspaceId) {
  document.querySelector('.content').innerHTML = '<div class="card">Выберите или создайте workspace.</div>';
} else {
  await renderAll({ reload: true });
  bindEvents();
}

export async function renderAll({ reload = false } = {}) {
  if (reload || !state.summary) {
    state.summary = await loadSummary(state.workspaceId);
    if (!state.selectedEntityId) state.selectedEntityId = entities()[0]?.id || null;
  }
  renderTabs();
  renderMapView();
  renderStructureView();
  if (state.activeTab === 'graph') await renderGraphView();
}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeTab = button.dataset.tab;
      renderAll();
    });
  });
  document.querySelectorAll('[data-start-entity-create]').forEach(button => {
    button.addEventListener('click', () => {
      state.createEntityMode = true;
      state.selectedFieldId = null;
      state.activeTab = 'structure';
      state.activeEditorTab = 'fields';
      renderAll();
    });
  });
}

function renderTabs() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.classList.toggle('btn-primary', button.dataset.tab === state.activeTab);
  });
  document.querySelectorAll('[data-view]').forEach(view => {
    view.classList.toggle('hidden', view.dataset.view !== state.activeTab);
  });
}
