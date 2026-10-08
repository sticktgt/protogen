import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { loadModuleConfig, loadSummary } from './api.js';
import { configureAgentDefaults, configureElementTypes, state, pages, requirements } from './state.js';
import { renderMapView } from './render-map.js';
import { renderStructureView } from './render-structure.js';
import { initializeAgentView, loadAgentPanelState, renderAgentView } from './agent-view.js';

await initLayout('ui_schema.main');
const context = await getContext();
state.workspaceId = currentWorkspaceId(context);
const urlParams = new URLSearchParams(window.location.search);
state.previewRunId = urlParams.get('preview_run_id');
state.previewActive = false;
state.readOnly = false;
const requestedTab = urlParams.get('tab');
if (['map', 'structure', 'agent'].includes(requestedTab)) state.activeTab = requestedTab;
const requestedPageId = urlParams.get('select_page_id');
const requestedElementId = urlParams.get('select_element_id');
const requestedDeletedType = urlParams.get('deleted_type');
const requestedDeletedId = urlParams.get('deleted_id');
if (requestedPageId) state.selectedPageId = requestedPageId;
if (requestedElementId) state.selectedElementId = requestedElementId;
if (requestedDeletedType && requestedDeletedId) {
  state.selectedDeletedChange = { objectType: requestedDeletedType, objectId: requestedDeletedId };
}

initializeAgentView({
  onSchemaReload: async () => {
    await renderAll({ reload: true });
  }
});

try {
  const moduleConfig = await loadModuleConfig();
  configureElementTypes(moduleConfig);
  configureAgentDefaults(moduleConfig);

  if (!state.workspaceId) {
    document.querySelector('.content').innerHTML = '<div class="card">Выберите или создайте workspace.</div>';
  } else {
    await renderAll({ reload: true });
    await loadAgentPanelState();
    renderAll();
    bindEvents();
  }
} catch (error) {
  console.error(error);
  document.querySelector('.content').innerHTML = '<div class="card">Не удалось загрузить конфигурацию модуля UI Schema.</div>';
}

export async function renderAll({ reload = false } = {}) {
  if (reload || !state.summary) {
    state.summary = await loadSummary(state.workspaceId, state.previewRunId);
    state.previewActive = Boolean(state.previewRunId);
    state.readOnly = state.previewActive;
    if (!state.selectedPageId || (!pages().some(item => item.id === state.selectedPageId) && state.selectedPageId !== '__app__')) {
      state.selectedPageId = pages()[0]?.id || null;
    }
    if (!state.selectedRequirementId) state.selectedRequirementId = requirements()[0]?.id || null;
  }
  renderTabs();
  renderMapView();
  renderStructureView();
  renderAgentView();
  applyReadOnlyState();
}

function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeTab = button.dataset.tab;
      renderAll();
    });
  });
  document.querySelector('[data-close-preview]')?.addEventListener('click', () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('preview_run_id');
    url.searchParams.set('tab', 'agent');
    window.location.href = url.toString();
  });
}

function renderTabs() {
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.classList.toggle('btn-primary', button.dataset.tab === state.activeTab);
  });
  document.querySelectorAll('[data-view]').forEach(view => {
    view.classList.toggle('hidden', view.dataset.view !== state.activeTab);
  });
  const previewBanner = document.querySelector('[data-preview-banner]');
  previewBanner?.classList.toggle('hidden', !state.previewActive);
  previewBanner?.querySelector('[data-close-preview]')?.classList.toggle('hidden', !state.previewActive);
  const lockBanner = document.querySelector('[data-lock-banner]');
  lockBanner?.classList.toggle('hidden', !state.writeLocked || state.previewActive);
}

function applyReadOnlyState() {
  const readOnly = state.readOnly || state.writeLocked;
  const createPage = document.querySelector('[data-start-page-create]');
  if (createPage) createPage.classList.toggle('hidden', readOnly);
  if (!readOnly) return;

  const addPanel = document.querySelector('[data-element-add-panel]');
  if (addPanel) addPanel.innerHTML = '';

  const editor = document.querySelector('[data-element-editor]');
  if (!editor) return;
  editor.querySelectorAll('input, textarea, select').forEach(control => {
    control.disabled = true;
  });
  const allowedButtons = [
    '[data-element-editor-tab]',
    '[data-page-editor-tab]',
    '[data-open-requirement]',
    '[data-open-ui-link-target]',
    '[data-open-ui-link-source]',
    '[data-select-related-element]',
    '[data-select-app-root]',
    '[data-select-page-root]',
    '[data-open-code]'
  ].join(',');
  editor.querySelectorAll('button').forEach(button => {
    if (!button.matches(allowedButtons)) button.disabled = true;
  });
}
