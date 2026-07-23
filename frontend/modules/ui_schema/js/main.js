import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { loadModuleConfig, loadSummary } from './api.js';
import { configureElementTypes, state, pages, requirements } from './state.js';
import { renderMapView } from './render-map.js';
import { renderStructureView } from './render-structure.js';

await initLayout('ui_schema.main');
const context = await getContext();
state.workspaceId = currentWorkspaceId(context);

try {
  const moduleConfig = await loadModuleConfig();
  configureElementTypes(moduleConfig);

  if (!state.workspaceId) {
    document.querySelector('.content').innerHTML = '<div class="card">Выберите или создайте workspace.</div>';
  } else {
    await renderAll({ reload: true });
    bindEvents();
  }
} catch (error) {
  console.error(error);
  document.querySelector('.content').innerHTML = '<div class="card">Не удалось загрузить конфигурацию модуля UI Schema.</div>';
}

export async function renderAll({ reload = false } = {}) {
  if (reload || !state.summary) {
    state.summary = await loadSummary(state.workspaceId);
    if (!state.selectedPageId) state.selectedPageId = pages()[0]?.id || null;
    if (!state.selectedRequirementId) state.selectedRequirementId = requirements()[0]?.id || null;
  }
  renderTabs();
  renderMapView();
  renderStructureView();
}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeTab = button.dataset.tab;
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
