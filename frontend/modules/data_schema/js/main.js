import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { loadModuleConfig, loadSummary } from './api.js';
import { configureAgentDefaults, state, entities } from './state.js';
import { renderMapView } from './render-map.js';
import { renderStructureView } from './render-structure.js';
import { renderGraphView } from './graph-joint.js';
import { initializeAgentView, loadAgentPanelState, renderAgentView } from './agent-view.js';

await initLayout('data_schema.main');
const context = await getContext();
state.workspaceId = currentWorkspaceId(context);
const urlParams = new URLSearchParams(window.location.search);
state.previewRunId = urlParams.get('preview_run_id');
const requestedTab = urlParams.get('tab');
if (['graph', 'map', 'structure', 'agent'].includes(requestedTab)) state.activeTab = requestedTab;
const requestedEntityId = urlParams.get('select_entity_id');
const requestedFieldId = urlParams.get('select_field_id');
const requestedRelationId = urlParams.get('select_relation_id');
if (requestedEntityId) state.selectedEntityId = requestedEntityId;
if (requestedFieldId) state.selectedFieldId = requestedFieldId;
if (requestedRelationId) state.graphSelectedRelationId = requestedRelationId;

initializeAgentView({
  onDataSchemaReload: async () => {
    await renderAll({ reload: true });
  }
});

try {
  const moduleConfig = await loadModuleConfig();
  configureAgentDefaults(moduleConfig);
  if (!state.workspaceId) {
    document.querySelector('.content').innerHTML = '<div class="card">Выберите или создайте workspace.</div>';
  } else {
    await renderAll({ reload: true });
    await loadAgentPanelState();
    await renderAll();
    bindEvents();
  }
} catch (error) {
  console.error(error);
  document.querySelector('.content').innerHTML = '<div class="card">Не удалось загрузить модуль Data Schema.</div>';
}

export async function renderAll({ reload = false } = {}) {
  if (reload || !state.summary) {
    state.summary = await loadSummary(state.workspaceId, state.previewRunId);
    state.previewActive = Boolean(state.previewRunId);
    state.readOnly = state.previewActive;
    const configuredSourcePath = state.summary?.requirements_source?.path;
    if (!state.previewActive && !state.agentLoaded && typeof configuredSourcePath === 'string' && configuredSourcePath) {
      state.agentRequirementsPath = configuredSourcePath;
    }
    if (!state.selectedEntityId || !entities().some(item => item.id === state.selectedEntityId)) {
      state.selectedEntityId = entities()[0]?.id || null;
      state.selectedFieldId = null;
    }
  }
  renderTabs();
  renderMapView();
  renderStructureView();
  if (state.activeTab === 'graph') await renderGraphView();
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
  document.querySelectorAll('[data-start-entity-create]').forEach(button => {
    button.addEventListener('click', () => {
      if (state.readOnly || state.writeLocked) return;
      state.createEntityMode = true;
      state.selectedFieldId = null;
      state.activeTab = 'structure';
      state.activeEditorTab = 'fields';
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
  document.querySelector('[data-preview-banner]')?.classList.toggle('hidden', !state.previewActive);
  document.querySelector('[data-lock-banner]')?.classList.toggle('hidden', !state.writeLocked || state.previewActive);
}

function applyReadOnlyState() {
  const readOnly = state.readOnly || state.writeLocked;
  document.querySelectorAll('[data-start-entity-create]').forEach(button => {
    button.classList.toggle('hidden', readOnly);
  });
  if (!readOnly) return;
  const editor = document.querySelector('[data-editor]');
  editor?.querySelectorAll('input, textarea, select').forEach(control => { control.disabled = true; });
  editor?.querySelectorAll('button').forEach(button => {
    const navigationOnly = button.matches('[data-editor-tab], [data-select-related], [data-open-code]');
    if (!navigationOnly) button.disabled = true;
  });
}
